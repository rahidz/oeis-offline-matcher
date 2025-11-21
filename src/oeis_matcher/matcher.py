from __future__ import annotations

from typing import Iterable, List, Optional

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
    all_pos = all(d > 0 for d in diffs)
    all_neg = all(d < 0 for d in diffs)
    all_nonneg = all(d >= 0 for d in diffs)
    all_nonpos = all(d <= 0 for d in diffs)
    if all_pos:
        return "pos"
    if all_neg:
        return "neg"
    if all_nonneg:
        return "nonneg"
    if all_nonpos:
        return "nonpos"
    return "mixed"


def candidate_sequences(
    db_path,
    query: SequenceQuery,
    *,
    use_prefix_index: bool = True,
    loosen_nonzero: bool = False,
) -> Iterable[SequenceRecord]:
    """
    Select an iterator over sequences using prefix index when possible,
    otherwise filter by invariants to shrink search space.
    """
    terms = query.terms
    if any(t is None for t in terms):
        # Wildcards present: fall back to full scan to avoid over-filtering.
        return iter_sequences(db_path)
    if use_prefix_index and (not query.allow_subsequence) and len(terms) >= 5:
        return iter_sequences_by_prefix(db_path, terms)

    sp = _sign_pattern(terms)
    fd = _first_diff_sign(terms)
    nz = sum(1 for t in terms if t != 0)
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
    )


def match_exact(
    query: SequenceQuery,
    sequences: Iterable[SequenceRecord],
    limit: Optional[int] = None,
    snippet_len: Optional[int] = None,
) -> List[Match]:
    """
    Find prefix (and optionally subsequence) matches.
    """
    results: List[Match] = []
    qterms = query.terms
    if len(qterms) < query.min_match_length:
        return results

    for seq in sequences:
        if _is_prefix(qterms, seq.terms):
            results.append(
                Match(
                    id=seq.id,
                    name=seq.name,
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
