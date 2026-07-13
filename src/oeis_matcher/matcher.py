from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Iterable, List, Optional
import time
from .config import load_config
from .similarity import growth_rate

from .models import Match, SequenceQuery, SequenceRecord
from .storage import iter_sequences, iter_sequences_by_prefix, iter_sequences_filtered


def _is_prefix(query_terms: List[int], seq_terms: List[int]) -> bool:
    qlen = len(query_terms)
    if qlen > len(seq_terms):
        return False
    for i in range(qlen):
        qt = query_terms[i]
        if qt is None:
            continue
        if seq_terms[i] != qt:
            return False
    return True


def _kmp_offset(pattern: List[int | None], text: List[int]) -> int:
    """
    KMP search for integer lists. Returns first offset or -1.
    Supports None as wildcard in pattern.
    """
    if any(p is None for p in pattern):
        # Simpler scan when wildcards present
        m, n = len(pattern), len(text)
        if m == 0 or m > n:
            return -1
        for i in range(n - m + 1):
            if all(_eq(pattern[j], text[i + j]) for j in range(m)):
                return i
        return -1

    m, n = len(pattern), len(text)
    if m == 0 or m > n:
        return -1

    # build lps (longest prefix-suffix)
    lps = [0] * m
    k = 0
    for i in range(1, m):
        while k > 0 and not _eq(pattern[k], pattern[i]):
            k = lps[k - 1]
        if _eq(pattern[k], pattern[i]):
            k += 1
            lps[i] = k

    q = 0
    for i in range(n):
        while q > 0 and not _eq(pattern[q], text[i]):
            q = lps[q - 1]
        if _eq(pattern[q], text[i]):
            q += 1
            if q == m:
                return i - m + 1
        # else continue
    return -1


def _eq(pat_val: int | None, text_val: int) -> bool:
    return pat_val is None or pat_val == text_val


def _sign_pattern(values: List[int]) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "empty"
    all_nonneg = all(v >= 0 for v in values)
    all_nonpos = all(v <= 0 for v in values)
    if all_nonneg:
        return "nonneg"
    if all_nonpos:
        return "nonpos"
    alt = all(
        values[i] == 0
        or values[i + 1] == 0
        or (values[i] > 0) != (values[i + 1] > 0)
        for i in range(len(values) - 1)
    )
    if alt:
        return "alternating"
    return "mixed"


def _first_diff_sign(values: List[int]) -> str:
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return "na"
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    zero = len(diffs) - pos - neg
    if pos == len(diffs):
        return "pos"
    if neg == len(diffs):
        return "neg"
    if pos > 0 and neg == 0:
        return "nonneg"
    if neg > 0 and pos == 0:
        return "nonpos"
    if zero == len(diffs):
        return "flat"
    return "mixed"


def candidate_sequences(
    db_path,
    query: SequenceQuery,
    *,
    use_prefix_index: bool = True,
    loosen_nonzero: bool = False,
    variance_band: float | None = None,
    growth_band: float | None = None,
    order_by_length_distance_to: int | None = None,
    limit: int | None = None,
) -> Iterable[SequenceRecord]:
    """
    Select an iterator over sequences using prefix index when possible,
    otherwise filter by invariants to shrink search space.
    """
    terms = query.terms
    if any(t is None for t in terms):
        # Wildcards present: fall back to full scan to avoid over-filtering.
        return iter_sequences(db_path)
    if use_prefix_index and (not query.allow_subsequence) and len(terms) >= 4:
        seqs = iter_sequences_by_prefix(db_path, terms)
        if limit is not None:
            from itertools import islice

            return islice(seqs, int(limit))
        return seqs

    cfg = load_config()
    # Subsequence searches should not filter on absolute nonzero counts, since
    # the query length can be much shorter than the stored sequence; otherwise
    # long all-nonzero sequences (the vast majority of OEIS) are wrongly
    # excluded. Treat allow_subsequence as an automatic request to loosen.
    if query.allow_subsequence:
        loosen_nonzero = True

    if variance_band is None:
        variance_band = float(cfg["limits"].get("variance_band", 50.0))
    if growth_band is None:
        growth_band = float(cfg["limits"].get("growth_band", 4.0))

    sp = _sign_pattern(terms)
    fd = _first_diff_sign(terms)
    # The global first-difference sign of a full sequence can differ from the
    # local behavior of a matching subsequence (e.g., early plateaus or sign
    # changes). Skip this filter for subsequence searches to avoid false
    # negatives like A063886/A182027-style offsets.
    if query.allow_subsequence:
        fd = None
    # "Loosened" candidate selection is used for combo candidate buckets and other
    # exploratory searches. In these contexts, filtering on the global first-diff
    # sign often causes false negatives (e.g., Lucas vs Fibonacci in a shifted
    # self-pair identity), so disable it when loosened.
    if loosen_nonzero:
        fd = None
    nz = sum(1 for t in terms if t != 0)
    # variance bands (guard against zero/near-zero variance)
    def _var(vals):
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return None
        mean = sum(vals) / len(vals)
        return sum((v - mean) ** 2 for v in vals) / len(vals)

    var_q = _var(terms)
    diff_var_q = _var([terms[i + 1] - terms[i] for i in range(len(terms) - 1)]) if len(terms) > 1 else None
    growth_q = growth_rate([t for t in terms if t is not None])
    var_min = var_max = None
    diff_var_min = diff_var_max = None
    growth_min = growth_max = None
    if var_q and var_q > 0 and var_q <= 1000:
        var_min = var_q / variance_band
        var_max = var_q * variance_band
    if diff_var_q and diff_var_q > 0 and diff_var_q <= 1000:
        diff_var_min = diff_var_q / variance_band
        diff_var_max = diff_var_q * variance_band
    if growth_q and growth_q > 0 and growth_band:
        growth_min = growth_q / growth_band
        growth_max = growth_q * growth_band
    # When running "loosened" searches (subsequence, combo candidate pools, etc.),
    # avoid applying *lower bounds* on these coarse invariants.
    #
    # Rationale:
    # - Many useful building-block sequences have smaller variance/diff-variance/growth
    #   than the query (e.g., linear sequences inside a quadratic combo).
    # - growth_rate in particular is length-dependent for short queries: long stored
    #   sequences can have much smaller growth_rate even when they share the same
    #   qualitative growth.
    #
    # Keeping only the upper bounds still provides some pruning without the sharp
    # false-negative behavior.
    if loosen_nonzero:
        var_min = None
        diff_var_min = None
        growth_min = None
    # nonzero band: allow +/- 50% to avoid over-filtering on short queries
    if loosen_nonzero:
        nz_min = 0
        nz_max = None
    else:
        band = max(1, int(max(1, len(terms)) * 0.5))
        nz_min = max(0, nz - band)
        nz_max = nz + band
    return iter_sequences_filtered(
        db_path,
        sign_pattern=sp,
        first_diff_sign=fd,
        nonzero_min=nz_min,
        nonzero_max=nz_max,
        min_length=query.min_match_length,
        var_min=var_min,
        var_max=var_max,
        diff_var_min=diff_var_min,
        diff_var_max=diff_var_max,
        growth_min=growth_min,
        growth_max=growth_max,
        order_by_length_distance_to=order_by_length_distance_to,
        limit=limit,
    )


def match_exact(
    query: SequenceQuery,
    sequences: Iterable[SequenceRecord],
    limit: Optional[int] = None,
    snippet_len: Optional[int] = None,
    max_time_s: float | None = None,
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
) -> List[Match]:
    """
    Find prefix (and optionally subsequence) matches.
    """
    results: List[Match] = []
    qterms = query.terms
    if len(qterms) < query.min_match_length:
        return results
    deadline: float | None = deadline_s
    if deadline is None and max_time_s is not None:
        try:
            cap = float(max_time_s)
        except (TypeError, ValueError):
            cap = None
        if cap is not None:
            if cap <= 0:
                return results
            deadline = time_fn() + cap

    for seq in sequences:
        if deadline is not None and time_fn() >= deadline:
            break
        if _is_prefix(qterms, seq.terms):
            results.append(
                Match(
                    id=seq.id,
                    name=seq.name,
                    keywords=seq.keywords,
                    seq_offset=seq.offset,
                    formula=seq.formula,
                    has_formula=seq.has_formula,
                    match_type="prefix",
                    offset=0,
                    length=len(qterms),
                    snippet=seq.terms[:snippet_len] if snippet_len else None,
                    score=len(qterms),
                )
            )
        elif query.allow_subsequence:
            off = _kmp_offset(qterms, seq.terms)
            if off != -1:
                results.append(
                    Match(
                        id=seq.id,
                        name=seq.name,
                        keywords=seq.keywords,
                        seq_offset=seq.offset,
                        formula=seq.formula,
                        has_formula=seq.has_formula,
                        match_type="subsequence",
                        offset=off,
                        length=len(qterms),
                        snippet=seq.terms[:snippet_len] if snippet_len else None,
                        score=len(qterms) - 0.5,
                )
            )
        if limit and len(results) >= limit:
            break

    # sort: prefix before subsequence, then longer sequences first
    results.sort(key=lambda m: (0 if m.match_type == "prefix" else 1, -m.length, m.offset))
    if limit:
        results = results[:limit]
    return results


def match_exact_prefix(query: SequenceQuery, db_path) -> List[Match]:
    """Convenience wrapper for prefix-only matches."""
    q = SequenceQuery(terms=query.terms, min_match_length=query.min_match_length, allow_subsequence=False)
    seq_iter = candidate_sequences(db_path, q)
    return match_exact(q, seq_iter)


def match_subsequence(query: SequenceQuery, db_path) -> List[Match]:
    """Convenience wrapper for subsequence matches."""
    q = SequenceQuery(terms=query.terms, min_match_length=query.min_match_length, allow_subsequence=True)
    seq_iter = candidate_sequences(db_path, q)
    return match_exact(q, seq_iter)


def _db_has_column(conn: sqlite3.Connection, column: str) -> bool:
    cur = conn.execute("PRAGMA table_info(sequences)")
    return any(row[1] == column for row in cur.fetchall())


def _parse_terms_prefix(terms_text: str | None, n: int | None) -> list[int] | None:
    if n is None:
        return None
    if not terms_text:
        return []
    if n <= 0:
        return []
    parts = terms_text.split(",", n)
    out: list[int] = []
    for p in parts[:n]:
        try:
            out.append(int(p))
        except ValueError:
            break
    return out


def _row_to_match(
    row: sqlite3.Row,
    *,
    match_type: str,
    offset: int,
    length: int,
    snippet_len: int | None,
    score: float,
    has_kw: bool,
    has_off: bool,
    has_formula_flag: bool,
    has_formula_text: bool,
) -> Match:
    kw = None
    if has_kw and row["keywords"]:
        kw = str(row["keywords"]).split(",")
    seq_off = None
    if has_off and row["offset0"] is not None:
        seq_off = (
            int(row["offset0"]),
            int(row["offset1"]) if ("offset1" in row.keys() and row["offset1"] is not None) else None,
        )
    formula_val = row["formula"] if has_formula_text else None
    has_formula_val = None
    if has_formula_flag and "has_formula" in row.keys() and row["has_formula"] is not None:
        has_formula_val = bool(row["has_formula"])
    elif formula_val:
        has_formula_val = True
    snippet = _parse_terms_prefix(row["terms"], snippet_len)
    return Match(
        id=row["id"],
        name=row["name"],
        keywords=kw,
        seq_offset=seq_off,
        formula=formula_val,
        has_formula=has_formula_val,
        match_type=match_type,
        offset=int(offset),
        length=int(length),
        snippet=snippet,
        score=float(score),
    )


class DBExactMatcher:
    """
    Reusable exact prefix/subsequence matcher backed by a single SQLite connection.

    This is the same logic as `match_exact_db`, but avoids reconnecting and
    re-checking schema columns for every call (useful for transform searches).
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._has_kw = _db_has_column(conn, "keywords")
        self._has_off = _db_has_column(conn, "offset0")
        self._has_formula_flag = _db_has_column(conn, "has_formula")
        self._has_formula_text = _db_has_column(conn, "formula")

        select_fields = ["id", "terms", "length", "name"]
        if self._has_formula_text:
            select_fields.append("formula")
        if self._has_kw:
            select_fields.append("keywords")
        if self._has_off:
            select_fields.extend(["offset0", "offset1"])
        if self._has_formula_flag:
            select_fields.append("has_formula")
        self._select = ", ".join(select_fields)

    def match(
        self,
        query: SequenceQuery,
        *,
        limit: int | None = None,
        snippet_len: int | None = None,
        max_time_s: float | None = None,
        deadline_s: float | None = None,
        time_fn: Callable[[], float] = time.perf_counter,
    ) -> list[Match]:
        qterms = query.terms
        qlen = len(qterms)
        if qlen < query.min_match_length:
            return []
        if any(t is None for t in qterms):
            raise ValueError("DBExactMatcher does not support wildcards (None terms)")
        deadline: float | None = deadline_s
        if deadline is None and max_time_s is not None:
            try:
                cap = float(max_time_s)
            except (TypeError, ValueError):
                cap = None
            if cap is not None:
                if cap <= 0:
                    return []
                deadline = time_fn() + cap

        pattern = ",".join(str(int(t)) for t in qterms)
        results: list[Match] = []

        def _maybe_limit(sql: str) -> str:
            return (sql + " LIMIT ?") if limit is not None else sql

        def _run_query(sql: str, params: list[object]) -> list[sqlite3.Row]:
            if deadline is None:
                return self._conn.execute(sql, params).fetchall()

            def _progress() -> int:
                return 1 if time_fn() >= deadline else 0

            self._conn.set_progress_handler(_progress, 2000)
            try:
                return self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError as exc:
                if "interrupted" in str(exc).lower():
                    return []
                raise
            finally:
                self._conn.set_progress_handler(None, 0)

        # Prefix matches
        if deadline is not None and time_fn() >= deadline:
            return []
        prefix_where: list[str] = ["length >= ?"]
        prefix_params: list[object] = [qlen]
        if qlen >= 5:
            prefix5 = ",".join(str(int(t)) for t in qterms[:5])
            prefix_where.append("prefix5 = ?")
            prefix_params.append(prefix5)
        else:
            # Prevent false positives like query "1" matching prefix "10,..."
            start = pattern + ","
            end = pattern + ",\uffff"
            prefix_where.append("(prefix5 = ? OR (prefix5 >= ? AND prefix5 < ?))")
            prefix_params.extend([pattern, start, end])
        prefix_where.append("(terms = ? OR terms LIKE ?)")
        prefix_params.extend([pattern, pattern + ",%"])

        prefix_sql = _maybe_limit(f"SELECT {self._select} FROM sequences WHERE " + " AND ".join(prefix_where))
        prefix_rows = _run_query(prefix_sql, prefix_params + ([limit] if limit is not None else []))
        for row in prefix_rows:
            if deadline is not None and time_fn() >= deadline:
                break
            results.append(
                _row_to_match(
                    row,
                    match_type="prefix",
                    offset=0,
                    length=qlen,
                    snippet_len=snippet_len,
                    score=float(qlen),
                    has_kw=self._has_kw,
                    has_off=self._has_off,
                    has_formula_flag=self._has_formula_flag,
                    has_formula_text=self._has_formula_text,
                )
            )

        if (not query.allow_subsequence) or (limit is not None and len(results) >= limit):
            return results[:limit] if limit is not None else results
        if deadline is not None and time_fn() >= deadline:
            results.sort(key=lambda m: (0 if m.match_type == "prefix" else 1, -m.length, m.offset))
            return results[:limit] if limit is not None else results

        remaining = None if limit is None else max(0, limit - len(results))
        if remaining == 0:
            return results[:limit] if limit is not None else results

        # Subsequence matches (exclude ids already returned as prefix)
        subseq_where: list[str] = [
            "length >= ?",
            "instr(',' || terms || ',', ',' || ? || ',') > 0",
        ]
        subseq_params: list[object] = [qlen, pattern]
        prefix_ids = [m.id for m in results if m.match_type == "prefix"]
        if prefix_ids:
            placeholders = ",".join("?" for _ in prefix_ids)
            subseq_where.append(f"id NOT IN ({placeholders})")
            subseq_params.extend(prefix_ids)

        subseq_sql = _maybe_limit(f"SELECT {self._select} FROM sequences WHERE " + " AND ".join(subseq_where))
        if remaining is not None:
            subseq_params2 = subseq_params + [remaining]
        else:
            subseq_params2 = subseq_params
        subseq_rows = _run_query(subseq_sql, subseq_params2)
        for row in subseq_rows:
            if deadline is not None and time_fn() >= deadline:
                break
            terms_text = row["terms"] or ""
            hay = "," + terms_text + ","
            needle = "," + pattern + ","
            pos = hay.find(needle)
            if pos == -1:
                continue
            # With a leading comma, the number of commas before the match equals the 0-based term offset.
            offset = hay[:pos].count(",")
            results.append(
                _row_to_match(
                    row,
                    match_type="subsequence",
                    offset=offset,
                    length=qlen,
                    snippet_len=snippet_len,
                    score=float(qlen) - 0.5,
                    has_kw=self._has_kw,
                    has_off=self._has_off,
                    has_formula_flag=self._has_formula_flag,
                    has_formula_text=self._has_formula_text,
                )
            )

        results.sort(key=lambda m: (0 if m.match_type == "prefix" else 1, -m.length, m.offset))
        return results[:limit] if limit is not None else results


def match_exact_db(
    query: SequenceQuery,
    db_path: str | Path,
    *,
    limit: int | None = None,
    snippet_len: int | None = None,
    max_time_s: float | None = None,
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
) -> list[Match]:
    """
    Exact prefix/subsequence matching using SQLite string predicates.

    This avoids heuristic candidate filtering for correctness, and avoids
    parsing every stored sequence into integer lists (faster for subsequence
    matches on large snapshots).
    """
    qterms = query.terms
    qlen = len(qterms)
    if qlen < query.min_match_length:
        return []
    if any(t is None for t in qterms):
        # Wildcards: fall back to the original matcher.
        return match_exact(
            query,
            iter_sequences(Path(db_path)),
            limit=limit,
            snippet_len=snippet_len,
            max_time_s=max_time_s,
            deadline_s=deadline_s,
            time_fn=time_fn,
        )

    with sqlite3.connect(str(Path(db_path))) as conn:
        return DBExactMatcher(conn).match(
            query,
            limit=limit,
            snippet_len=snippet_len,
            max_time_s=max_time_s,
            deadline_s=deadline_s,
            time_fn=time_fn,
        )
