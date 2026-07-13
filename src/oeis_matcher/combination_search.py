from __future__ import annotations

import time
from fractions import Fraction
from dataclasses import dataclass
from itertools import combinations, combinations_with_replacement, product
import heapq
import math
import sqlite3
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .models import CombinationMatch, SequenceQuery, SequenceRecord
from .transforms import diff_transform, partial_sum_transform


PrefixLocations = int | list[int]


def _add_prefix_location(index: dict[str, PrefixLocations], key: str, location: int) -> None:
    current = index.get(key)
    if current is None:
        index[key] = location
    elif isinstance(current, int):
        index[key] = [current, location]
    else:
        current.append(location)


def _prefix_locations(index: dict[str, PrefixLocations], key: str) -> tuple[int, ...] | list[int]:
    current = index.get(key)
    if current is None:
        return ()
    return (current,) if isinstance(current, int) else current


@dataclass
class PrefixIndex:
    """
    In-memory index over the first `prefix_len` terms of every sequence.

    Used for "expanded" combination searches that can't rely on the usual
    candidate filters (e.g., when components differ wildly from the query).
    """

    prefix_len: int
    ids: list[str]
    id_nums: list[int]
    lengths: list[int]
    # Prefixes are stored as comma-joined text (e.g. "0,1,1,2,3") so we can
    # build the mapping quickly without parsing every prefix into integers.
    # Numerical parsing is done lazily for the small subset of prefixes we
    # actually inspect during a time-capped expanded search.
    prefixes: list[str]
    by_prefix: dict[str, PrefixLocations]
    complete: bool = False
    last_id: str | None = None


_PREFIX_INDEX_CACHE: dict[tuple[str, int], PrefixIndex] = {}


def _prefix_col_name(prefix_len: int, shift: int) -> str:
    """
    Return the SQLite column name for the `prefix_len`-term prefix at `shift`.

    Current storage schema uses:
      - prefix5      : terms[0:5]
      - prefix5_k    : terms[k:k+5] for k>=1 (optional, created via optimize-db --add-prefix-shifts)
    """
    if int(prefix_len) != 5:
        raise ValueError("Only prefix_len=5 is supported by the current DB schema.")
    shift = int(shift)
    if shift < 0:
        raise ValueError("prefix shift must be >= 0")
    return "prefix5" if shift == 0 else f"prefix5_{shift}"


@dataclass
class ShiftedPrefixIndex:
    """
    Like PrefixIndex, but supports multiple fixed forward shifts (k<=5).

    This shares the base `ids/id_nums/lengths` arrays across shifts so that
    expanded shifted searches don't need to build multiple full PrefixIndex
    objects (which can be memory-heavy on a full OEIS snapshot).
    """

    prefix_len: int
    max_shift: int
    shifts: tuple[int, ...]
    ids: list[str]
    id_nums: list[int]
    lengths: list[int]
    prefixes_by_shift: dict[int, list[str]]
    by_prefix_by_shift: dict[int, dict[str, PrefixLocations]]
    complete: bool = False
    last_id: str | None = None


_SHIFTED_PREFIX_INDEX_CACHE: dict[tuple[str, int, int], ShiftedPrefixIndex] = {}


def _get_shifted_prefix_index(
    db_path: Path,
    prefix_len: int,
    max_shift: int,
    *,
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
) -> ShiftedPrefixIndex:
    """
    Build (or incrementally extend) a DB-wide shifted prefix index.

    The returned index may be partially built when `deadline_s` is provided
    and the deadline is reached. Callers should treat `index.complete == False`
    as "best effort" and either stop or fall back to non-expanded methods.
    """
    prefix_len = int(prefix_len)
    max_shift = max(0, int(max_shift))
    key = (str(Path(db_path).resolve()), prefix_len, max_shift)
    cached = _SHIFTED_PREFIX_INDEX_CACHE.get(key)
    if cached is not None:
        if cached.complete or deadline_s is None:
            return cached
        if time_fn() >= deadline_s:
            return cached
        index = cached
    else:
        # Detect which shift columns exist (older DBs won't have prefix5_k).
        with sqlite3.connect(db_path) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(sequences)").fetchall()}
        shifts_avail: list[int] = []
        for s in range(0, max_shift + 1):
            col = _prefix_col_name(prefix_len, s)
            if col in cols:
                shifts_avail.append(s)
        if 0 not in shifts_avail:
            shifts_avail = [0]

        index = ShiftedPrefixIndex(
            prefix_len=prefix_len,
            max_shift=max_shift,
            shifts=tuple(shifts_avail),
            ids=[],
            id_nums=[],
            lengths=[],
            prefixes_by_shift={s: [] for s in shifts_avail},
            by_prefix_by_shift={s: {} for s in shifts_avail},
            complete=False,
            last_id=None,
        )
        _SHIFTED_PREFIX_INDEX_CACHE[key] = index

    if index.complete:
        return index

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        # Select only the columns we actually have.
        prefix_cols = [_prefix_col_name(prefix_len, s) for s in index.shifts]
        select_cols = ["id", "length", *prefix_cols]
        params: list[object] = [int(prefix_len)]
        sql = f"SELECT {', '.join(select_cols)} FROM sequences WHERE length >= ?"
        if index.last_id is not None:
            sql += " AND id > ?"
            params.append(str(index.last_id))
        sql += " ORDER BY id"

        for row in conn.execute(sql, params):
            if deadline_s is not None and time_fn() >= deadline_s:
                return index
            seq_id = row["id"]
            index.last_id = seq_id

            idx = len(index.ids)
            index.ids.append(seq_id)
            try:
                index.id_nums.append(int(str(seq_id)[1:]))
            except Exception:
                index.id_nums.append(-1)
            index.lengths.append(int(row["length"]))

            for s in index.shifts:
                col = _prefix_col_name(prefix_len, s)
                key_txt = row[col] if col in row.keys() else None
                if not key_txt:
                    index.prefixes_by_shift[s].append("")
                    continue
                index.prefixes_by_shift[s].append(key_txt)
                _add_prefix_location(index.by_prefix_by_shift[s], key_txt, idx)

    index.complete = True
    return index


def _get_prefix_index(
    db_path: Path,
    prefix_len: int,
    *,
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
) -> PrefixIndex:
    key = (str(Path(db_path).resolve()), int(prefix_len))
    cached = _PREFIX_INDEX_CACHE.get(key)
    if cached is not None:
        if cached.complete or deadline_s is None:
            return cached
        if time_fn() >= deadline_s:
            return cached
        index = cached
    else:
        index = PrefixIndex(
            prefix_len=int(prefix_len),
            ids=[],
            id_nums=[],
            lengths=[],
            prefixes=[],
            by_prefix={},
            complete=False,
            last_id=None,
        )
        _PREFIX_INDEX_CACHE[key] = index

    if index.complete:
        return index

    def _prefix_key(prefix5: str, n: int) -> str | None:
        """
        Return the first n terms of a comma-joined prefix5 string, as a string key.

        Fast path for n==5 (the common expanded-search case): returns prefix5
        as-is.
        """
        if not prefix5:
            return None
        n = int(n)
        if n <= 0:
            return None
        # Most expanded searches use the full 5-term key. Avoid splitting and int parsing
        # for every sequence: store text keys and parse only when needed later.
        if n == 5:
            # prefix5 must contain at least 5 terms => at least 4 commas.
            if prefix5.count(",") < 4:
                return None
            return prefix5
        # General (rare): truncate to first n terms without a full split().
        commas = prefix5.count(",")
        if commas < (n - 1):
            return None
        if commas == (n - 1):
            return prefix5
        cut_pos = -1
        # Cut before the n-th comma, i.e. after n terms.
        for _ in range(n):
            cut_pos = prefix5.find(",", cut_pos + 1)
            if cut_pos == -1:
                return prefix5
        return prefix5[:cut_pos]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        params: list = [int(prefix_len)]
        sql = "SELECT id, length, prefix5 FROM sequences WHERE prefix5 IS NOT NULL AND length >= ?"
        if index.last_id is not None:
            sql += " AND id > ?"
            params.append(str(index.last_id))
        sql += " ORDER BY id"
        for row in conn.execute(sql, params):
            if deadline_s is not None and time_fn() >= deadline_s:
                return index
            seq_id = row["id"]
            # Always advance the cursor even if this row has malformed prefix text,
            # so incremental builds don't get stuck repeatedly re-reading a bad row.
            index.last_id = seq_id
            pref_txt = row["prefix5"]
            key_txt = _prefix_key(pref_txt, prefix_len)
            if key_txt is None:
                continue
            idx = len(index.ids)
            index.ids.append(seq_id)
            try:
                index.id_nums.append(int(seq_id[1:]))
            except Exception:
                index.id_nums.append(-1)
            index.lengths.append(int(row["length"]))
            index.prefixes.append(key_txt)
            _add_prefix_location(index.by_prefix, key_txt, idx)

    index.complete = True
    return index


def _has_column(conn: sqlite3.Connection, column: str) -> bool:
    cur = conn.execute("PRAGMA table_info(sequences)")
    return any(row[1] == column for row in cur.fetchall())


class _SequenceFetcher:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._cache: dict[str, SequenceRecord | None] = {}
        self._has_kw = _has_column(self._conn, "keywords")
        self._has_off = _has_column(self._conn, "offset0")
        self._has_formula_flag = _has_column(self._conn, "has_formula")
        self._has_formula_text = _has_column(self._conn, "formula")

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
        self._sql = f"SELECT {self._select} FROM sequences WHERE id = ?"

    def close(self) -> None:
        self._conn.close()

    def get(self, seq_id: str) -> SequenceRecord | None:
        if seq_id in self._cache:
            return self._cache[seq_id]
        row = self._conn.execute(self._sql, (seq_id,)).fetchone()
        if not row:
            self._cache[seq_id] = None
            return None
        terms = [int(x) for x in row["terms"].split(",")] if row["terms"] else []
        offset = None
        if self._has_off and row["offset0"] is not None:
            offset = (int(row["offset0"]), int(row["offset1"]) if "offset1" in row.keys() else None)
        formula_val = row["formula"] if self._has_formula_text else None
        has_formula_val = None
        if self._has_formula_flag and "has_formula" in row.keys() and row["has_formula"] is not None:
            has_formula_val = bool(row["has_formula"])
        elif formula_val:
            has_formula_val = True
        rec = SequenceRecord(
            id=row["id"],
            terms=terms,
            length=int(row["length"]),
            name=row["name"],
            formula=formula_val,
            keywords=row["keywords"].split(",") if self._has_kw and row["keywords"] else None,
            offset=offset,
            has_formula=has_formula_val,
        )
        self._cache[seq_id] = rec
        return rec


def _shift_str(k: int) -> str:
    if k == 0:
        return "n"
    sign = "+" if k > 0 else "-"
    return f"n{sign}{abs(k)}"


def _format_modclass_expr(modulus: int, ids: Sequence[str], shifts: Sequence[int], t_names: Sequence[str]) -> str:
    """
    Format a mod-class decomposition like:
      a(2n) = Axxxxxx(n+1); a(2n+1) = Ayyyyyy(n)

    Notes:
    - Ordering matters: `ids[i]` is residue class i (r=i).
    - `shifts[i]` is a forward shift on the *component* sequence index, i.e. A(n+shift).
    """
    m = int(modulus)
    parts: list[str] = []

    def _tn(tn: str, id_: str, shift: int) -> str:
        if tn == "id":
            return f"{id_}({_shift_str(shift)})"
        return f"{tn}({id_}({_shift_str(shift)}) )".replace(") )", ")")

    for r, (id_, s, tn) in enumerate(zip(ids, shifts, t_names)):
        lhs = f"a({m}n)" if r == 0 else f"a({m}n+{r})"
        parts.append(f"{lhs} = {_tn(tn, id_, int(s))}")
    return "; ".join(parts)


def _format_modclass_latex(modulus: int, ids: Sequence[str], shifts: Sequence[int], t_names: Sequence[str]) -> str:
    m = int(modulus)

    def shift_to_tex(k: int) -> str:
        if k == 0:
            return "n"
        sign = "+" if k > 0 else "-"
        return f"n{sign}{abs(k)}"

    def t_tex(name: str, id_: str, s: int) -> str:
        base = f"\\mathrm{{{id_}}}({shift_to_tex(s)})"
        if name == "id":
            return base
        if name == "diff":
            return f"\\Delta\\,{base}"
        if name == "partial_sum":
            return f"\\mathrm{{psum}}\\,{base}"
        return f"\\mathrm{{{name}}}\\,{base}"

    parts: list[str] = []
    for r, (id_, s, tn) in enumerate(zip(ids, shifts, t_names)):
        lhs = f"a_{{{m}n}}" if r == 0 else f"a_{{{m}n+{r}}}"
        parts.append(f"{lhs} = {t_tex(tn, id_, int(s))}")
    return "; ".join(parts)


@dataclass(frozen=True)
class ComponentTransform:
    name: str
    func: Callable[[list[int]], list[int]]
    weight: float = 0.0


class _TransformedSequenceCache:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], list[int]] = {}

    def get(self, record: SequenceRecord, transform: ComponentTransform) -> list[int]:
        key = (record.id, transform.name)
        if key not in self._values:
            self._values[key] = transform.func(record.terms)
        return self._values[key]


def _default_component_transforms() -> list[ComponentTransform]:
    return [
        ComponentTransform("id", lambda seq: seq, weight=0.0),
        ComponentTransform("diff", diff_transform().func, weight=1.2),
        ComponentTransform("partial_sum", partial_sum_transform().func, weight=1.1),
    ]


def resolve_component_transforms(names: Sequence[str] | None) -> list[ComponentTransform]:
    catalog = {t.name: t for t in _default_component_transforms()}
    if not names:
        return [catalog["id"]]
    resolved: list[ComponentTransform] = []
    for n in names:
        t = catalog.get(n)
        if t:
            resolved.append(t)
    return resolved or [catalog["id"]]


def _num_abs(val) -> float:
    try:
        return float(abs(val))
    except Exception:
        return abs(val)


def _dedup_records_by_id(candidates: Sequence[SequenceRecord] | Iterable[SequenceRecord]) -> list[SequenceRecord]:
    """
    De-duplicate candidate records by id while preserving the input order.

    This is important because upstream candidate selection (e.g. `get_candidate_bucket`)
    intentionally orders records to put seeded / high-value sequences early. Many combo
    searches are bounded by max_time/max_checks, so preserving that order makes results
    more stable and more likely to surface "canonical" explanations quickly.
    """
    seen: set[str] = set()
    out: list[SequenceRecord] = []
    for rec in candidates:
        if rec.id in seen:
            continue
        seen.add(rec.id)
        out.append(rec)
    return out


def _shift_values(max_shift: int, max_shift_back: int) -> list[int]:
    """
    Deterministic shift enumeration order that prefers "simple" alignments first.

    Instead of iterating from negative to positive (range(-back, fwd)), we start
    with 0, then alternate small positive/negative shifts:
      0, +1, -1, +2, -2, ...

    This improves time-to-first-hit under time/check caps because the simplest
    decompositions usually use no shift (or very small shifts).
    """
    max_shift = max(0, int(max_shift))
    max_shift_back = max(0, int(max_shift_back))
    out: list[int] = [0]
    for k in range(1, max(max_shift, max_shift_back) + 1):
        if k <= max_shift:
            out.append(k)
        if k <= max_shift_back:
            out.append(-k)
    return out


def _combo_complexity(coeffs: Sequence, shifts: Sequence[int], t_weights: Sequence[float] | None = None) -> float:
    """
    Penalize larger coefficients, shifts, extra components, and per-component transforms.
    """
    comp = sum(_num_abs(c) for c in coeffs) + 0.5 * sum(abs(s) for s in shifts)
    extra_components = max(0, len(coeffs) - 2)
    comp += 0.5 * extra_components
    if t_weights:
        comp += sum(t_weights)
    return comp


def _popularity_bonus(records: Sequence[SequenceRecord]) -> float:
    weights = {"core": 1.0, "nice": 0.6, "easy": 0.3, "hard": 0.2, "nonn": 0.1}
    bonus = 0.0
    for rec in records:
        if not rec.keywords:
            continue
        bonus += sum(weights[k] for k in rec.keywords if k in weights)
    return bonus


def _combo_score(length: int, coeffs: Sequence[int], shifts: Sequence[int], t_weights: Sequence[float] | None = None, pop_bonus: float = 0.0) -> float:
    comp = _combo_complexity(coeffs, shifts, t_weights)
    return length / (1.0 + comp) * (1.0 + 0.1 * pop_bonus)


def _fmt_coeff(c) -> str:
    if isinstance(c, Fraction) and c.denominator != 1:
        return f"{c.numerator}/{c.denominator}"
    return str(int(c)) if float(c).is_integer() else str(c)


def _format_expr(ids: Sequence[str], coeffs: Sequence, shifts: Sequence[int], t_names: Sequence[str]) -> str:
    def _tn(tn: str, id_: str, shift: int) -> str:
        if tn == "id":
            return f"{id_}({_shift_str(shift)})"
        return f"{tn}({id_}({_shift_str(shift)}) )".replace(") )", ")")

    parts = [f"{_fmt_coeff(c)}*{_tn(tn, id_, s)}" for id_, c, s, tn in zip(ids, coeffs, shifts, t_names)]
    return "a(n) = " + " + ".join(parts)


def _format_latex(ids: Sequence[str], coeffs: Sequence, shifts: Sequence[int], t_names: Sequence[str]) -> str:
    def shift_to_tex(k: int) -> str:
        if k == 0:
            return "n"
        sign = "+" if k > 0 else "-"
        return f"n{sign}{abs(k)}"

    def t_tex(name: str, id_: str, s: int) -> str:
        base = f"\\mathrm{{{id_}}}({shift_to_tex(s)})"
        if name == "id":
            return base
        if name == "diff":
            return f"\\Delta\\,{base}"
        if name == "partial_sum":
            return f"\\mathrm{{psum}}\\,{base}"
        return f"\\mathrm{{{name}}}\\,{base}"

    def coeff_tex(c) -> str:
        if isinstance(c, Fraction) and c.denominator != 1:
            return f"\\tfrac{{{c.numerator}}}{{{c.denominator}}}"
        return str(int(c)) if float(c).is_integer() else str(c)

    parts = [f"{coeff_tex(c)}\\,{t_tex(tn, id_, s)}" for id_, c, s, tn in zip(ids, coeffs, shifts, t_names)]
    return "a_{{n}} = " + " + ".join(parts)


def _canonicalize_components(
    *,
    ids: Sequence[str],
    names: Sequence[str | None],
    coeffs: Sequence,
    shifts: Sequence[int],
    t_names: Sequence[str],
    component_terms: Sequence[Sequence[int]] | None,
) -> tuple[tuple[str, ...], tuple[str | None, ...], tuple, tuple[int, ...], tuple[str, ...], tuple[Sequence[int], ...] | None]:
    """
    Canonicalize component ordering by OEIS id.

    Combination searches are commutative in the *components* (pairs/triples), but
    enumeration order depends on the candidate pool order. Canonicalizing keeps
    outputs deterministic and makes tests/JSON output stable.
    """
    n = len(ids)
    order = list(range(n))
    order.sort(key=lambda i: ids[i])
    if order == list(range(n)):
        return (
            tuple(ids),
            tuple(names),
            tuple(coeffs),
            tuple(int(s) for s in shifts),
            tuple(t_names),
            tuple(component_terms) if component_terms is not None else None,
        )

    ids2 = tuple(ids[i] for i in order)
    names2 = tuple(names[i] for i in order)
    coeffs2 = tuple(coeffs[i] for i in order)
    shifts2 = tuple(int(shifts[i]) for i in order)
    t_names2 = tuple(t_names[i] for i in order)
    terms2 = tuple(component_terms[i] for i in order) if component_terms is not None else None
    return (ids2, names2, coeffs2, shifts2, t_names2, terms2)


def _build_linear_match(
    records: Sequence[SequenceRecord],
    coeffs: Sequence,
    shifts: Sequence[int],
    transform_names: Sequence[str],
    transform_weights: Sequence[float],
    aligned_terms: Sequence[Sequence[int]],
    target_terms: Sequence[int],
    *,
    length: int,
    snippet_len: int | None,
    min_score: float | None,
    max_complexity: float | None,
) -> CombinationMatch | None:
    if max_complexity is not None and _combo_complexity(coeffs, shifts, t_weights=transform_weights) > max_complexity:
        return None
    score = _combo_score(
        length,
        coeffs,
        shifts,
        t_weights=transform_weights,
        pop_bonus=_popularity_bonus(records),
    )
    if min_score is not None and score < min_score:
        return None

    component_terms = combined_terms = None
    if snippet_len is not None:
        size = min(snippet_len, length)
        component_terms = tuple(list(terms[:size]) for terms in aligned_terms)
        combined_terms = list(target_terms[:size])
    ids, names, coeffs, shifts, transform_names, component_terms = _canonicalize_components(
        ids=tuple(record.id for record in records),
        names=tuple(record.name for record in records),
        coeffs=coeffs,
        shifts=shifts,
        t_names=transform_names,
        component_terms=component_terms,
    )
    return CombinationMatch(
        ids=ids,
        names=names,
        coeffs=coeffs,
        shifts=shifts,
        length=length,
        score=score,
        expression=_format_expr(ids, coeffs, shifts, transform_names),
        latex_expression=_format_latex(ids, coeffs, shifts, transform_names),
        component_transforms=transform_names,
        component_terms=component_terms,
        combined_terms=combined_terms,
    )


def _format_pointwise_expr(op: str, ids: Sequence[str], shifts: Sequence[int], t_names: Sequence[str]) -> str:
    def _tn(tn: str, id_: str, shift: int) -> str:
        if tn == "id":
            return f"{id_}({_shift_str(shift)})"
        return f"{tn}({id_}({_shift_str(shift)}) )".replace(") )", ")")

    s1 = _tn(t_names[0], ids[0], shifts[0])
    s2 = _tn(t_names[1], ids[1], shifts[1])
    if op == "mul":
        body = f"{s1}*{s2}"
    elif op == "gcd":
        body = f"gcd({s1}, {s2})"
    elif op == "lcm":
        body = f"lcm({s1}, {s2})"
    else:
        body = f"{s1}?{op}?{s2}"
    return "a(n) = " + body


def _format_pointwise_latex(op: str, ids: Sequence[str], shifts: Sequence[int], t_names: Sequence[str]) -> str:
    def shift_to_tex(k: int) -> str:
        if k == 0:
            return "n"
        sign = "+" if k > 0 else "-"
        return f"n{sign}{abs(k)}"

    def t_tex(name: str, id_: str, s: int) -> str:
        base = f"\\mathrm{{{id_}}}({shift_to_tex(s)})"
        if name == "id":
            return base
        if name == "diff":
            return f"\\Delta\\,{base}"
        if name == "partial_sum":
            return f"\\mathrm{{psum}}\\,{base}"
        return f"\\mathrm{{{name}}}\\,{base}"

    s1 = t_tex(t_names[0], ids[0], shifts[0])
    s2 = t_tex(t_names[1], ids[1], shifts[1])
    if op == "mul":
        body = f"{s1}\\,{s2}"
    elif op == "gcd":
        body = f"\\gcd({s1}, {s2})"
    elif op == "lcm":
        body = f"\\operatorname{{lcm}}({s1}, {s2})"
    else:
        body = f"{s1}?{op}?{s2}"
    return "a_{n} = " + body


def _format_convolution_expr(op: str, ids: Sequence[str], t_names: Sequence[str]) -> str:
    def _tn(tn: str, id_: str) -> str:
        if tn == "id":
            return id_
        if tn == "diff":
            return f"diff({id_})"
        if tn == "partial_sum":
            return f"partial_sum({id_})"
        return f"{tn}({id_})"

    s1 = _tn(t_names[0], ids[0])
    s2 = _tn(t_names[1], ids[1])
    if op == "cauchy":
        return f"a(n) = ({s1} * {s2})_n"
    if op == "dirichlet":
        return f"a(n) = ({s1} ⋆ {s2})(n)"
    return f"a(n) = ({op} convolution of {s1} and {s2})"


def _format_convolution_latex(op: str, ids: Sequence[str], t_names: Sequence[str]) -> str:
    def _tn(tn: str, id_: str) -> str:
        base = f"\\mathrm{{{id_}}}"
        if tn == "id":
            return base
        if tn == "diff":
            return f"\\Delta\\,{base}"
        if tn == "partial_sum":
            return f"\\mathrm{{psum}}\\,{base}"
        return f"\\mathrm{{{tn}}}({base})"

    s1 = _tn(t_names[0], ids[0])
    s2 = _tn(t_names[1], ids[1])
    if op == "cauchy":
        return f"a_{{n}} = ({s1} * {s2})_n"
    if op == "dirichlet":
        return f"a_{{n}} = ({s1} \\star {s2})(n)"
    return f"a_{{n}} = ({op}({s1},{s2}))"


def _to_fraction(val) -> Fraction:
    if isinstance(val, Fraction):
        return val
    if isinstance(val, int):
        return Fraction(val, 1)
    try:
        return Fraction(val).limit_denominator(10_000)
    except Exception:
        return Fraction(int(val), 1)


def _normalize_linear_coeffs(coeffs: Sequence) -> tuple[int, ...]:
    fracs = [_to_fraction(c) for c in coeffs]
    if not fracs:
        return tuple()
    denom_lcm = 1
    for f in fracs:
        denom_lcm = math.lcm(denom_lcm, int(f.denominator))
    ints = [int(f.numerator * (denom_lcm // int(f.denominator))) for f in fracs]
    g = 0
    for v in ints:
        g = math.gcd(g, abs(int(v)))
    if g > 1:
        ints = [int(v // g) for v in ints]
    first_nonzero = next((v for v in ints if v != 0), 0)
    if first_nonzero < 0:
        ints = [-int(v) for v in ints]
    return tuple(int(v) for v in ints)


def _infer_family_from_expression(expr: str) -> str:
    e = (expr or "").lower()
    if "gcd(" in e or "lcm(" in e:
        return "pointwise"
    if " = (" in e and (" ⋆ " in e or ")_n" in e):
        return "convolution"
    if "a(" in e and "n+" in e and ";" in e:
        return "modclass"
    if "a(" in e and "n)" in e and ";" in e:
        return "modclass"
    return "linear"


def _combination_symbolic_key(m: CombinationMatch, *, family_hint: str | None = None) -> tuple:
    family = family_hint or _infer_family_from_expression(m.expression or "")
    t_names = m.component_transforms or tuple("id" for _ in m.ids)
    comps = list(zip(m.ids, (int(s) for s in m.shifts), t_names))

    if family in {"linear", "linear2", "linear3"}:
        norm = _normalize_linear_coeffs(m.coeffs)
        with_coeffs = [(c[0], int(c[1]), c[2], int(k)) for c, k in zip(comps, norm)]
        with_coeffs.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        return ("linear", tuple(with_coeffs))

    if family == "pointwise":
        # For ranking diversity we intentionally de-dup pointwise hits at the
        # component-family level (id + transform), not by shift/op variants.
        # Otherwise high-scoring gcd/lcm shift variants can flood out distinct
        # component pairs.
        comps_s = tuple(sorted((c[0], c[2]) for c in comps))
        return ("pointwise", comps_s)

    if family == "convolution":
        expr = m.expression or ""
        op = "dirichlet" if ("⋆" in expr or "star" in expr.lower()) else "cauchy"
        comps_s = tuple(sorted((c[0], int(c[1]), c[2]) for c in comps))
        return ("convolution", op, comps_s)

    if family == "modclass":
        # Mod-class is order-sensitive by residue class.
        return (
            "modclass",
            tuple((c[0], int(c[1]), c[2]) for c in comps),
        )

    # Fallback: expression text + components.
    return (
        family,
        (m.expression or "").replace(" ", ""),
        tuple((c[0], int(c[1]), c[2]) for c in comps),
    )


def _rational_solution_is_pathological(
    coeffs: Sequence[Fraction],
    components: Sequence[Sequence[int]],
    target: Sequence[int],
    *,
    max_abs_numerator: int = 200,
    max_denominator: int = 64,
    max_l1_coeff: float = 64.0,
    max_cancel_ratio: float = 40.0,
) -> bool:
    """
    Guardrails for exact-rational solves to suppress hard-to-interpret fits.

    We already verify exact equality term-by-term. This helper additionally filters
    solutions with very complex coefficients or extreme cancellation.
    """
    nz = [c for c in coeffs if c != 0]
    if not nz:
        return True
    if any(abs(int(c.numerator)) > max_abs_numerator for c in nz):
        return True
    if any(int(c.denominator) > max_denominator for c in nz):
        return True
    l1 = sum(abs(float(c)) for c in nz)
    if l1 > max_l1_coeff:
        return True

    if not target:
        return True
    worst_ratio = 0.0
    for i, want in enumerate(target):
        contrib = 0.0
        for c, seq in zip(coeffs, components):
            if i >= len(seq):
                return True
            contrib += abs(float(c * seq[i]))
        denom = abs(float(want)) + 1.0
        worst_ratio = max(worst_ratio, contrib / denom)
        if worst_ratio > max_cancel_ratio:
            return True
    return False


def merge_combination_families(
    families: dict[str, Sequence[CombinationMatch]],
    *,
    limit: int | None = None,
    per_family_quota: int = 1,
) -> list[tuple[str, CombinationMatch]]:
    """
    Merge multiple explanation families with fair representation and
    cross-family symbolic deduplication.
    """
    staged: dict[str, list[CombinationMatch]] = {}
    for fam, raw in families.items():
        if not raw:
            continue
        arr = sorted(
            list(raw),
            key=lambda m: (
                -(m.score if m.score is not None else 0.0),
                _combo_complexity(m.coeffs, m.shifts),
                -m.length,
                m.ids,
            ),
        )
        # De-dup within family first.
        uniq: list[CombinationMatch] = []
        seen_local: set[tuple] = set()
        for m in arr:
            key = _combination_symbolic_key(m, family_hint=fam)
            if key in seen_local:
                continue
            seen_local.add(key)
            uniq.append(m)
        if uniq:
            staged[fam] = uniq

    if not staged:
        return []

    total = sum(len(v) for v in staged.values())
    out_limit = total if (limit is None or int(limit) <= 0) else min(int(limit), total)
    quota = max(0, int(per_family_quota))

    ptr: dict[str, int] = {fam: 0 for fam in staged}
    selected_per_family: dict[str, int] = {fam: 0 for fam in staged}
    chosen: list[tuple[str, CombinationMatch]] = []
    seen_global: set[tuple] = set()

    # Phase 1: quota-based round-robin so each family competes fairly.
    if quota > 0:
        while len(chosen) < out_limit:
            made_progress = False
            fam_order = sorted(
                (f for f in staged.keys() if selected_per_family[f] < quota),
                key=lambda f: -(staged[f][ptr[f]].score if ptr[f] < len(staged[f]) and staged[f][ptr[f]].score is not None else 0.0),
            )
            if not fam_order:
                break
            for fam in fam_order:
                if len(chosen) >= out_limit:
                    break
                if selected_per_family[fam] >= quota:
                    continue
                arr = staged[fam]
                i = ptr[fam]
                pick: CombinationMatch | None = None
                while i < len(arr):
                    cand = arr[i]
                    key = _combination_symbolic_key(cand, family_hint=fam)
                    i += 1
                    if key in seen_global:
                        continue
                    pick = cand
                    seen_global.add(key)
                    break
                ptr[fam] = i
                if pick is None:
                    continue
                chosen.append((fam, pick))
                selected_per_family[fam] += 1
                made_progress = True
            if not made_progress:
                break

    # Phase 2: fill remaining slots by global score.
    if len(chosen) < out_limit:
        leftovers: list[tuple[str, CombinationMatch]] = []
        for fam, arr in staged.items():
            i = ptr[fam]
            while i < len(arr):
                leftovers.append((fam, arr[i]))
                i += 1
        leftovers.sort(
            key=lambda fm: (
                -(fm[1].score if fm[1].score is not None else 0.0),
                _combo_complexity(fm[1].coeffs, fm[1].shifts),
                -fm[1].length,
                fm[0],
                fm[1].ids,
            )
        )
        for fam, m in leftovers:
            if len(chosen) >= out_limit:
                break
            key = _combination_symbolic_key(m, family_hint=fam)
            if key in seen_global:
                continue
            seen_global.add(key)
            chosen.append((fam, m))

    return chosen


def _sorted_and_trim(
    results: list[CombinationMatch],
    limit: int | None,
    *,
    dedupe_family: bool = True,
    family: str | None = None,
) -> list[CombinationMatch]:
    def _family_key(m: CombinationMatch) -> tuple:
        fam = family or _infer_family_from_expression(m.expression or "")
        return _combination_symbolic_key(m, family_hint=fam)

    results.sort(
        key=lambda m: (
            -m.score,
            _combo_complexity(m.coeffs, m.shifts),
            -(m.latex_expression is not None),
            -m.length,
            m.ids,
        )
    )
    if not dedupe_family:
        return results[:limit] if limit else results

    deduped: list[CombinationMatch] = []
    seen: set[tuple] = set()
    for m in results:
        key = _family_key(m)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
        if limit and len(deduped) >= limit:
            break
    return deduped[:limit] if limit else deduped


def _aligned_span(
    query_len: int,
    seq_lens: Sequence[int],
    shifts: Sequence[int],
    *,
    min_match_length: int,
) -> tuple[int, int] | None:
    """
    Compute the aligned overlap between the query and shifted sequences.

    Returns (q_start, match_len) or None.

    Performance note:
    This returns indices only (no list slicing). Inner combo loops should
    avoid allocating new lists per alignment; only slice when emitting a hit.
    """
    if query_len <= 0:
        return None

    if all(s >= 0 for s in shifts):
        if any(L - s < query_len for L, s in zip(seq_lens, shifts)):
            return None
        return 0, query_len

    # Negative shift(s): allow partial overlap, bounded by min_match_length.
    n_min = max(0, *[-s for s in shifts if s < 0])
    n_max = min(query_len, *[L - s for L, s in zip(seq_lens, shifts)])
    length = n_max - n_min
    if length < min_match_length or length <= 0:
        return None
    return n_min, length


def _solve_rational_coeffs(slice1: Sequence[int], slice2: Sequence[int], target: Sequence[int], *, coeff_bound: int = 100) -> tuple[Fraction, Fraction] | None:
    """
    Solve for coefficients a,b over Q such that a*slice1 + b*slice2 == target.
    Returns (a,b) as Fractions or None if no exact solution.
    """
    n = len(target)
    if n < 2:
        return None
    s1 = list(slice1)
    s2 = list(slice2)
    t = list(target)

    # Try consecutive pairs to find invertible 2x2
    for i in range(n - 1):
        a1, b1, y1 = s1[i], s2[i], t[i]
        a2, b2, y2 = s1[i + 1], s2[i + 1], t[i + 1]
        det = a1 * b2 - a2 * b1
        if det == 0:
            continue
        a = Fraction(y1 * b2 - y2 * b1, det)
        b = Fraction(a1 * y2 - a2 * y1, det)
        if any(abs(x.numerator) > coeff_bound or x.denominator > coeff_bound for x in (a, b)):
            continue
        if all(Fraction(y) == a * Fraction(x) + b * Fraction(z) for x, z, y in zip(s1, s2, t)):
            return a, b
    return None


def _solve_rational_coeffs_triple(a_col: Sequence[int], b_col: Sequence[int], c_col: Sequence[int], target: Sequence[int], *, coeff_bound: int = 100) -> tuple[Fraction, Fraction, Fraction] | None:
    """
    Solve for (a,b,c) over Q such that a*a_col + b*b_col + c*c_col == target.
    Uses 3x3 determinants from first independent rows; verifies full match.
    """
    n = len(target)
    if n < 3:
        return None
    rows = list(zip(a_col, b_col, c_col, target))
    for i in range(n - 2):
        a1, b1, c1, y1 = rows[i]
        a2, b2, c2, y2 = rows[i + 1]
        a3, b3, c3, y3 = rows[i + 2]
        # determinant
        det = (
            a1 * (b2 * c3 - b3 * c2)
            - b1 * (a2 * c3 - a3 * c2)
            + c1 * (a2 * b3 - a3 * b2)
        )
        if det == 0:
            continue
        det_a = (
            y1 * (b2 * c3 - b3 * c2)
            - b1 * (y2 * c3 - y3 * c2)
            + c1 * (y2 * b3 - y3 * b2)
        )
        det_b = (
            a1 * (y2 * c3 - y3 * c2)
            - y1 * (a2 * c3 - a3 * c2)
            + c1 * (a2 * y3 - a3 * y2)
        )
        det_c = (
            a1 * (b2 * y3 - b3 * y2)
            - b1 * (a2 * y3 - a3 * y2)
            + y1 * (a2 * b3 - a3 * b2)
        )
        a = Fraction(det_a, det)
        b = Fraction(det_b, det)
        c = Fraction(det_c, det)
        if any(abs(x.numerator) > coeff_bound or x.denominator > coeff_bound for x in (a, b, c)):
            continue
        if all(Fraction(y) == a * Fraction(x1) + b * Fraction(x2) + c * Fraction(x3) for x1, x2, x3, y in rows):
            return a, b, c
    return None


def search_two_sequence_combinations(
    query: SequenceQuery,
    candidates: Sequence[SequenceRecord] | Iterable[SequenceRecord],
    *,
    coeffs: Sequence[int] = (-3, -2, -1, 1, 2, 3),
    max_shift: int = 0,
    max_shift_back: int = 0,
    limit: int = 20,
    max_candidates: int | None = None,
    max_checks: int | None = None,
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    max_combinations: int | None = None,
    component_transforms: Sequence[ComponentTransform] | None = None,
    snippet_len: int | None = None,
    use_rational: bool = False,
    min_score: float | None = None,
    max_complexity: float | None = None,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """
    Brute-force search for integer linear combinations of two sequences that equal the query prefix.
    Supports forward drops and optional backward shifts (negative indices) up to max_shift_back.
    `max_checks` bounds the number of coefficient/shift evaluations to keep latency predictable.
    """
    q = query.terms
    qlen = len(q)
    if qlen < query.min_match_length or qlen == 0:
        return []
    if any(t is None for t in q):
        return []

    coeff_list = list(coeffs)
    coeff_len = len(coeff_list)
    coeff_set = set(coeff_list)
    coeff_index: dict[int, int] = {}
    for i, c in enumerate(coeff_list):
        # Keep the first occurrence if duplicates are present.
        coeff_index.setdefault(int(c), i)
    if not coeff_list and not use_rational:
        return []

    records = _dedup_records_by_id(candidates)
    if max_candidates is not None:
        records = records[:max_candidates]

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()
    checks = 0
    t_start = time_fn()

    shift_vals = _shift_values(max_shift, max_shift_back)
    transforms = list(component_transforms or [t for t in _default_component_transforms() if t.name == "id"])
    transformed = _TransformedSequenceCache()

    if snippet_len is None:
        snippet_len = len(query.terms)

    pair_space = coeff_len * coeff_len if coeff_len else 0

    # Allow using the same OEIS sequence more than once. This enables "self-shift"
    # identities like:
    #   Lucas(n) = Fibonacci(n-1) + Fibonacci(n+1)
    #
    # We still keep enumeration deterministic and avoid symmetric duplicates for
    # self-pairs below.
    for rec1, rec2 in combinations_with_replacement(records, 2):
        for t1 in transforms:
            seq1 = transformed.get(rec1, t1)
            for s1 in shift_vals:
                # If any shift is negative we allow partial overlap; otherwise require full-length match.
                for t2 in transforms:
                    seq2 = transformed.get(rec2, t2)
                    for s2 in shift_vals:
                        if rec1.id == rec2.id:
                            # Skip identical duplicate components; they only create coefficient-sum variants.
                            if t1.name == t2.name and s1 == s2:
                                continue
                            # Avoid symmetric duplicates for self-pairs (same underlying sequence).
                            if (t1.name, s1) > (t2.name, s2):
                                continue
                        if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                            return _sorted_and_trim(results, limit)
                        span = _aligned_span(
                            len(query.terms),
                            (len(seq1), len(seq2)),
                            (s1, s2),
                            min_match_length=query.min_match_length,
                        )
                        if span is None:
                            continue
                        q_start, match_len = span
                        s1_start = q_start + s1
                        s2_start = q_start + s2
                        if use_rational:
                            q_slice = query.terms[q_start : q_start + match_len]
                            slice1 = seq1[s1_start : s1_start + match_len]
                            slice2 = seq2[s2_start : s2_start + match_len]
                            sol = _solve_rational_coeffs(slice1, slice2, q_slice)
                            if sol is None:
                                continue
                            a, b = sol
                            if _rational_solution_is_pathological((a, b), (slice1, slice2), q_slice):
                                continue
                            checks += 1
                            if max_checks is not None and checks > max_checks:
                                return _sorted_and_trim(results, limit)
                            if max_combinations is not None and checks > max_combinations:
                                return _sorted_and_trim(results, limit)

                            key = (rec1.id, rec2.id, t1.name, t2.name, a, b, s1, s2)
                            if key in seen:
                                continue
                            seen.add(key)
                            m = _build_linear_match(
                                (rec1, rec2),
                                coeffs=(a, b),
                                shifts=(s1, s2),
                                transform_names=(t1.name, t2.name),
                                transform_weights=(t1.weight, t2.weight),
                                aligned_terms=(slice1, slice2),
                                target_terms=q_slice,
                                length=match_len,
                                snippet_len=snippet_len,
                                min_score=min_score,
                                max_complexity=max_complexity,
                            )
                            if m is None:
                                continue
                            results.append(m)
                            if on_match is not None:
                                on_match(m)
                            continue
                        else:
                            # Fast path: solve for (a,b) from two rows when the columns are linearly independent.
                            # Fall back to brute force only in degenerate cases (det==0 for all row pairs).
                            sol_int: tuple[int, int] | None = None
                            det_found = False
                            for i in range(match_len - 1):
                                a1 = seq1[s1_start + i]
                                b1 = seq2[s2_start + i]
                                y1 = query.terms[q_start + i]
                                a2 = seq1[s1_start + i + 1]
                                b2 = seq2[s2_start + i + 1]
                                y2 = query.terms[q_start + i + 1]
                                det = a1 * b2 - a2 * b1
                                if det == 0:
                                    continue
                                det_found = True
                                num_a = y1 * b2 - y2 * b1
                                num_b = a1 * y2 - a2 * y1
                                if (num_a % det) != 0 or (num_b % det) != 0:
                                    sol_int = None
                                else:
                                    sol_int = (num_a // det, num_b // det)
                                break

                            if det_found:
                                # Simulate brute-force check accounting so `max_checks` / `max_combinations`
                                # still behave deterministically w.r.t. coefficient ordering.
                                if pair_space <= 0:
                                    continue

                                # No integer solution (unique solution is non-integer) -> no match for any coeff pair.
                                if sol_int is None:
                                    if max_checks is not None and (checks + pair_space) > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and (checks + pair_space) > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    checks += pair_space
                                    continue

                                a, b = sol_int
                                if a == 0 and b == 0:
                                    if max_checks is not None and (checks + pair_space) > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and (checks + pair_space) > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    checks += pair_space
                                    continue
                                if a not in coeff_set or b not in coeff_set:
                                    if max_checks is not None and (checks + pair_space) > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and (checks + pair_space) > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    checks += pair_space
                                    continue

                                idx_a = coeff_index.get(int(a))
                                idx_b = coeff_index.get(int(b))
                                if idx_a is None or idx_b is None or coeff_len <= 0:
                                    if max_checks is not None and (checks + pair_space) > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and (checks + pair_space) > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    checks += pair_space
                                    continue

                                pos = idx_a * coeff_len + idx_b + 1  # 1-based position in nested loops
                                if max_checks is not None and (checks + pos) > max_checks:
                                    return _sorted_and_trim(results, limit)
                                if max_combinations is not None and (checks + pos) > max_combinations:
                                    return _sorted_and_trim(results, limit)

                                q0 = query.terms[q_start]
                                if a * seq1[s1_start] + b * seq2[s2_start] != q0:
                                    # Would have exhausted all coefficient pairs without a hit.
                                    if max_checks is not None and (checks + pair_space) > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and (checks + pair_space) > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    checks += pair_space
                                    continue
                                if match_len > 1:
                                    q1 = query.terms[q_start + 1]
                                    if a * seq1[s1_start + 1] + b * seq2[s2_start + 1] != q1:
                                        if max_checks is not None and (checks + pair_space) > max_checks:
                                            return _sorted_and_trim(results, limit)
                                        if max_combinations is not None and (checks + pair_space) > max_combinations:
                                            return _sorted_and_trim(results, limit)
                                        checks += pair_space
                                        continue
                                if match_len > 2:
                                    q_last = query.terms[q_start + match_len - 1]
                                    if a * seq1[s1_start + match_len - 1] + b * seq2[s2_start + match_len - 1] != q_last:
                                        if max_checks is not None and (checks + pair_space) > max_checks:
                                            return _sorted_and_trim(results, limit)
                                        if max_combinations is not None and (checks + pair_space) > max_combinations:
                                            return _sorted_and_trim(results, limit)
                                        checks += pair_space
                                        continue

                                ok = True
                                for j in range(match_len):
                                    if a * seq1[s1_start + j] + b * seq2[s2_start + j] != query.terms[q_start + j]:
                                        ok = False
                                        break
                                if not ok:
                                    if max_checks is not None and (checks + pair_space) > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and (checks + pair_space) > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    checks += pair_space
                                    continue

                                # Count checks up to the matching coefficient pair.
                                checks += pos

                                key = (rec1.id, rec2.id, t1.name, t2.name, a, b, s1, s2)
                                if key in seen:
                                    continue
                                seen.add(key)
                                m = _build_linear_match(
                                    (rec1, rec2),
                                    coeffs=(a, b),
                                    shifts=(s1, s2),
                                    transform_names=(t1.name, t2.name),
                                    transform_weights=(t1.weight, t2.weight),
                                    aligned_terms=(
                                        seq1[s1_start : s1_start + match_len],
                                        seq2[s2_start : s2_start + match_len],
                                    ),
                                    target_terms=query.terms[q_start : q_start + match_len],
                                    length=match_len,
                                    snippet_len=snippet_len,
                                    min_score=min_score,
                                    max_complexity=max_complexity,
                                )
                                if m is None:
                                    continue
                                results.append(m)
                                if on_match is not None:
                                    on_match(m)
                                continue

                            # Degenerate case (det==0 for all row pairs): brute force.
                            for a in coeff_list:
                                for b in coeff_list:
                                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                        return _sorted_and_trim(results, limit)
                                    checks += 1
                                    if max_checks is not None and checks > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and checks > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    if a == 0 and b == 0:
                                        continue
                                    q0 = query.terms[q_start]
                                    if a * seq1[s1_start] + b * seq2[s2_start] != q0:
                                        continue
                                    if match_len > 1:
                                        q1 = query.terms[q_start + 1]
                                        if a * seq1[s1_start + 1] + b * seq2[s2_start + 1] != q1:
                                            continue
                                    if match_len > 2:
                                        q_last = query.terms[q_start + match_len - 1]
                                        if a * seq1[s1_start + match_len - 1] + b * seq2[s2_start + match_len - 1] != q_last:
                                            continue

                                    ok = True
                                    for j in range(match_len):
                                        if a * seq1[s1_start + j] + b * seq2[s2_start + j] != query.terms[q_start + j]:
                                            ok = False
                                            break
                                    if not ok:
                                        continue

                                    key = (rec1.id, rec2.id, t1.name, t2.name, a, b, s1, s2)
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    m = _build_linear_match(
                                        (rec1, rec2),
                                        coeffs=(a, b),
                                        shifts=(s1, s2),
                                        transform_names=(t1.name, t2.name),
                                        transform_weights=(t1.weight, t2.weight),
                                        aligned_terms=(
                                            seq1[s1_start : s1_start + match_len],
                                            seq2[s2_start : s2_start + match_len],
                                        ),
                                        target_terms=query.terms[q_start : q_start + match_len],
                                        length=match_len,
                                        snippet_len=snippet_len,
                                        min_score=min_score,
                                        max_complexity=max_complexity,
                                    )
                                    if m is None:
                                        continue
                                    results.append(m)
                                    if on_match is not None:
                                        on_match(m)

    return _sorted_and_trim(results, limit)


def _apply_pointwise_op(op: str, a: int, b: int) -> int:
    if op == "mul":
        return a * b
    if op == "gcd":
        return math.gcd(a, b)
    if op == "lcm":
        g = math.gcd(a, b)
        if g == 0:
            return 0
        return abs(a // g * b)
    return 0


def _cauchy_convolution(seq1: Sequence[int], seq2: Sequence[int], length: int) -> list[int]:
    """Cauchy convolution c_n = sum_{k=0..n} a_k b_{n-k} for n=0..length-1."""
    out: list[int] = []
    L1, L2 = len(seq1), len(seq2)
    for n in range(length):
        s = 0
        for k in range(n + 1):
            if k < L1 and n - k < L2:
                s += seq1[k] * seq2[n - k]
        out.append(s)
    return out


def _dirichlet_convolution(seq1: Sequence[int], seq2: Sequence[int], length: int) -> list[int]:
    """Dirichlet convolution on 1-based indices: c(n) = sum_{d|n} a(d) b(n/d).

    seq[i] is interpreted as a(i+1). Returned list has length `length`, representing c(1)..c(length).
    """
    out: list[int] = []
    L1, L2 = len(seq1), len(seq2)
    for n in range(1, length + 1):
        s = 0
        for d in range(1, n + 1):
            if n % d != 0:
                continue
            i = d - 1
            j = n // d - 1
            if i < L1 and j < L2:
                s += seq1[i] * seq2[j]
        out.append(s)
    return out


def _cauchy_convolution_matches(seq1: Sequence[int], seq2: Sequence[int], target: Sequence[int]) -> bool:
    """Return True iff Cauchy convolution of seq1 and seq2 equals target."""
    L1, L2 = len(seq1), len(seq2)
    if L1 == 0 or L2 == 0:
        return all(int(t) == 0 for t in target)

    for n, want in enumerate(target):
        # Only k in [0..n] contribute, plus bounds from seq lengths.
        # We intersect:
        #   0 <= k <= L1-1
        #   0 <= n-k <= L2-1  ->  n-(L2-1) <= k <= n
        kmin = max(0, n - (L2 - 1))
        kmax = min(n, L1 - 1)
        if kmax < kmin:
            if want != 0:
                return False
            continue
        s = 0
        for k in range(kmin, kmax + 1):
            s += seq1[k] * seq2[n - k]
        if s != want:
            return False
    return True


def _dirichlet_convolution_matches(seq1: Sequence[int], seq2: Sequence[int], target: Sequence[int]) -> bool:
    """Return True iff Dirichlet convolution of seq1 and seq2 equals target."""
    L1, L2 = len(seq1), len(seq2)
    if L1 == 0 or L2 == 0:
        return all(int(t) == 0 for t in target)

    for n, want in enumerate(target, start=1):
        s = 0
        r = math.isqrt(n)
        for d in range(1, r + 1):
            if n % d != 0:
                continue
            e = n // d

            # term for divisor d: A(d)*B(e)
            i = d - 1
            j = e - 1
            if i < L1 and j < L2:
                s += seq1[i] * seq2[j]

            if e != d:
                # corresponding divisor e: A(e)*B(d)
                i2 = e - 1
                j2 = d - 1
                if i2 < L1 and j2 < L2:
                    s += seq1[i2] * seq2[j2]
        if s != want:
            return False
    return True


def search_pointwise_two_sequence_combinations(
    query: SequenceQuery,
    candidates: Sequence[SequenceRecord] | Iterable[SequenceRecord],
    *,
    ops: Sequence[str] = ("mul", "gcd", "lcm"),
    max_shift: int = 0,
    max_shift_back: int = 0,
    limit: int = 20,
    max_candidates: int | None = None,
    max_checks: int | None = None,
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    component_transforms: Sequence[ComponentTransform] | None = None,
    snippet_len: int | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """Search pointwise combinations like a(n)=op(S1,S2): mul/gcd/lcm on aligned terms."""
    q = query.terms
    qlen = len(q)
    if qlen < query.min_match_length or qlen == 0:
        return []
    if any(t is None for t in q):
        return []

    ops = [o for o in ops if o in {"mul", "gcd", "lcm"}]
    if not ops:
        return []

    records = _dedup_records_by_id(candidates)
    if max_candidates is not None:
        records = records[:max_candidates]

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()
    checks = 0
    t_start = time_fn()

    shift_vals = range(-max_shift_back, max_shift + 1)
    transforms = list(component_transforms or [t for t in _default_component_transforms() if t.name == "id"])
    transformed = _TransformedSequenceCache()

    if snippet_len is None:
        snippet_len = len(query.terms)

    for rec1, rec2 in combinations_with_replacement(records, 2):
        same_rec = rec1.id == rec2.id
        for t1 in transforms:
            seq1 = transformed.get(rec1, t1)
            for s1 in shift_vals:
                for t2 in transforms:
                    seq2 = transformed.get(rec2, t2)
                    for s2 in shift_vals:
                        if same_rec:
                            # Avoid symmetric duplicates for self-pairs, where multiplication/gcd/lcm are commutative.
                            key1 = (t1.weight, t1.name, s1)
                            key2 = (t2.weight, t2.name, s2)
                            if key1 > key2:
                                continue
                        if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                            return _sorted_and_trim(results, limit)
                        span = _aligned_span(
                            len(query.terms),
                            (len(seq1), len(seq2)),
                            (s1, s2),
                            min_match_length=query.min_match_length,
                        )
                        if span is None:
                            continue
                        q_start, match_len = span
                        s1_start = q_start + s1
                        s2_start = q_start + s2
                        for op in ops:
                            # Trivial identities: gcd(a,a)=a and lcm(a,a)=a.
                            # Prefer exact matches for those.
                            if same_rec and op in {"gcd", "lcm"}:
                                continue
                            checks += 1
                            if max_checks is not None and checks > max_checks:
                                return _sorted_and_trim(results, limit)
                            if (
                                match_len
                                and _apply_pointwise_op(op, seq1[s1_start], seq2[s2_start]) != query.terms[q_start]
                            ):
                                continue
                            if (
                                match_len > 1
                                and _apply_pointwise_op(op, seq1[s1_start + 1], seq2[s2_start + 1])
                                != query.terms[q_start + 1]
                            ):
                                continue
                            if (
                                match_len > 2
                                and _apply_pointwise_op(
                                    op, seq1[s1_start + match_len - 1], seq2[s2_start + match_len - 1]
                                )
                                != query.terms[q_start + match_len - 1]
                            ):
                                continue
                            ok = True
                            for j in range(match_len):
                                if (
                                    _apply_pointwise_op(op, seq1[s1_start + j], seq2[s2_start + j])
                                    != query.terms[q_start + j]
                                ):
                                    ok = False
                                    break
                            if not ok:
                                continue
                            # Trivial identity/annihilator cases:
                            # - mul by all-ones leaves the other operand unchanged
                            # - lcm with all-ones leaves the other operand unchanged
                            # - mul by all-zeros forces the output to all-zeros
                            #
                            # Keep them, but strongly down-rank identity hits so more
                            # explanatory decompositions (e.g. n*(n+1)) remain visible
                            # within small `limit` values.
                            def _is_const(seq: list[int], start: int, length: int, val: int) -> bool:
                                for jj in range(length):
                                    if seq[start + jj] != val:
                                        return False
                                return True

                            is_ones_1 = _is_const(seq1, s1_start, match_len, 1)
                            is_ones_2 = _is_const(seq2, s2_start, match_len, 1)
                            is_zero_1 = _is_const(seq1, s1_start, match_len, 0)
                            is_zero_2 = _is_const(seq2, s2_start, match_len, 0)

                            key = (op, rec1.id, rec2.id, t1.name, t2.name, s1, s2)
                            if key in seen:
                                continue
                            seen.add(key)
                            pop_bonus = _popularity_bonus((rec1, rec2))
                            t_weights = (t1.weight, t2.weight)
                            coeffs = (1, 1)
                            shifts = (s1, s2)
                            comp_val = _combo_complexity(coeffs, shifts, t_weights=t_weights)
                            if max_complexity is not None and comp_val > max_complexity:
                                continue
                            score = _combo_score(match_len, coeffs, shifts, t_weights=t_weights, pop_bonus=pop_bonus)
                            if op in {"mul", "lcm"} and (is_ones_1 or is_ones_2):
                                score *= 0.55
                            if op == "mul" and (is_zero_1 or is_zero_2):
                                # If the query isn't all-zeros, this would be a contradiction anyway,
                                # but keep it as a cheap guard against redundant/degenerate hits.
                                if any(query.terms[q_start + jj] != 0 for jj in range(match_len)):
                                    continue
                                score *= 0.5
                            if min_score is not None and score < min_score:
                                continue
                            if snippet_len is None:
                                comp_terms = None
                                combined_terms = None
                            else:
                                snip = min(snippet_len, match_len)
                                comp_terms = (
                                    seq1[s1_start : s1_start + snip],
                                    seq2[s2_start : s2_start + snip],
                                )
                                combined_terms = query.terms[q_start : q_start + snip]

                            ids_c, names_c, coeffs_c, shifts_c, tnames_c, comp_terms_c = _canonicalize_components(
                                ids=(rec1.id, rec2.id),
                                names=(rec1.name, rec2.name),
                                coeffs=coeffs,
                                shifts=shifts,
                                t_names=(t1.name, t2.name),
                                component_terms=comp_terms,
                            )
                            expr = _format_pointwise_expr(op, ids_c, shifts_c, tnames_c)
                            latex = _format_pointwise_latex(op, ids_c, shifts_c, tnames_c)

                            results.append(
                                (m := CombinationMatch(
                                    ids=ids_c,
                                    names=names_c,
                                    coeffs=coeffs_c,
                                    shifts=shifts_c,
                                    length=match_len,
                                    score=score,
                                    expression=expr,
                                    latex_expression=latex,
                                    component_transforms=tnames_c,
                                    component_terms=comp_terms_c,
                                    combined_terms=combined_terms,
                                )
                            )
                            )
                            if on_match is not None:
                                on_match(m)

    return _sorted_and_trim(results, limit)


def search_pointwise_two_sequence_combinations_expanded(
    query: SequenceQuery,
    db_path: Path,
    *,
    ops: Sequence[str] = ("mul",),
    max_shift: int = 0,
    limit: int = 20,
    scan_strides: Sequence[int] = (100, 50, 20, 10, 5, 2, 1),
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    snippet_len: int | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    dedupe_family: bool = True,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """
    Expanded DB-wide pointwise search for combinations like:
      a(n) = Axxxxxx(n+k1) * Ayyyyyy(n+k2)

    Current scope/limits:
    - only supports op=mul (gcd/lcm are not invertible in the same way),
    - only supports per-component transform=id,
    - only supports forward shifts in [0..max_shift] (k <= 5 recommended).

    Uses a shifted prefix index (prefix5, prefix5_1..prefix5_k) to avoid scanning
    all (A,B) pairs. Instead, it:
      - anchors on A, derives the required B prefix by exact division,
      - looks up candidate Bs via the DB-wide prefix index,
      - verifies the full query length.
    """
    q = query.terms
    qlen = len(q)
    if qlen < max(query.min_match_length, 5) or qlen == 0:
        return []
    if any(t is None for t in q):
        return []

    ops = [o for o in ops if o == "mul"]
    if not ops:
        return []

    max_shift = max(0, int(max_shift))
    if max_shift <= 0:
        shifts = (0,)
    else:
        shifts = tuple(range(0, max_shift + 1))

    t_start = time_fn()
    if max_time_s is not None and max_time_s <= 0:
        return []
    deadline_s = (t_start + float(max_time_s)) if max_time_s is not None else None

    prefix_len = 5
    index = _get_shifted_prefix_index(Path(db_path), prefix_len, max_shift, deadline_s=deadline_s, time_fn=time_fn)
    if deadline_s is not None and time_fn() >= deadline_s:
        return []

    # Only consider shifts that are actually available in the DB schema/index.
    shifts = tuple(s for s in shifts if s in index.shifts)
    if not shifts:
        return []

    q_prefix = tuple(int(q[i]) for i in range(prefix_len))

    stride_order = [int(s) for s in scan_strides if int(s) > 0]
    if 1 not in stride_order:
        stride_order.append(1)

    scan_cache: dict[int, list[int]] = {}

    def _scan_indices(stride: int) -> list[int]:
        cached = scan_cache.get(stride)
        if cached is not None:
            return cached
        out: list[int] = []
        for i, (num, length) in enumerate(zip(index.id_nums, index.lengths)):
            if length < qlen:
                continue
            if num != -1 and stride != 1 and (num % stride) != 0:
                continue
            out.append(i)
        scan_cache[stride] = out
        return out

    # Same progressive scan order idea as the expanded linear-combo solvers:
    scan_order: list[int] = []
    seen_idx: set[int] = set()
    for stride in stride_order:
        for idx in _scan_indices(stride):
            if idx in seen_idx:
                continue
            seen_idx.add(idx)
            scan_order.append(idx)

    if snippet_len is None:
        snippet_len = len(query.terms)

    fetcher = _SequenceFetcher(Path(db_path))
    results: list[CombinationMatch] = []
    seen: set[tuple] = set()

    try:
        for idx1 in scan_order:
            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                break
            id1 = index.ids[idx1]
            len1 = index.lengths[idx1]

            rec1: SequenceRecord | None = None
            bad_rec1 = False

            for s1 in shifts:
                if bad_rec1:
                    break
                if len1 < qlen + s1:
                    continue
                key_txt = index.prefixes_by_shift[s1][idx1]
                if not key_txt:
                    continue
                pref1 = _parse_prefix_key(key_txt, prefix_len)
                if pref1 is None:
                    continue

                # Derive the needed B prefix by division. If A has a zero where
                # the query also has a zero, B is unconstrained there, so we
                # can't form a key => skip this anchor/shift.
                needed_vals: list[int] = []
                ambiguous = False
                for qv, av in zip(q_prefix, pref1):
                    if av == 0:
                        if qv != 0:
                            ambiguous = True
                            break
                        ambiguous = True
                        break
                    if qv % av != 0:
                        ambiguous = True
                        break
                    needed_vals.append(qv // av)
                if ambiguous:
                    continue
                needed_key = ",".join(str(v) for v in needed_vals)

                # Fetch rec1 lazily only once we have a plausible prefix hit.
                if rec1 is None:
                    rec1 = fetcher.get(id1)
                    if not rec1 or len(rec1.terms) < (qlen + s1):
                        bad_rec1 = True
                        break

                for s2 in shifts:
                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                        return _sorted_and_trim(results, limit, dedupe_family=dedupe_family)
                    idxs2 = _prefix_locations(index.by_prefix_by_shift[s2], needed_key)
                    if not idxs2:
                        continue
                    for idx2 in idxs2:
                        if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                            return _sorted_and_trim(results, limit, dedupe_family=dedupe_family)
                        id2 = index.ids[idx2]
                        len2 = index.lengths[idx2]
                        if len2 < qlen + s2:
                            continue

                        rec2 = fetcher.get(id2)
                        if not rec2 or len(rec2.terms) < (qlen + s2):
                            continue

                        # Verify full match quickly (first/last guards).
                        if qlen:
                            if rec1.terms[s1] * rec2.terms[s2] != q[0]:
                                continue
                            if qlen > 1 and (rec1.terms[s1 + 1] * rec2.terms[s2 + 1] != q[1]):
                                continue
                            if qlen > 2 and (rec1.terms[s1 + qlen - 1] * rec2.terms[s2 + qlen - 1] != q[-1]):
                                continue
                        ok = True
                        for j in range(qlen):
                            if rec1.terms[s1 + j] * rec2.terms[s2 + j] != q[j]:
                                ok = False
                                break
                        if not ok:
                            continue

                        if snippet_len is None:
                            comp_terms_in = None
                            combined_terms = None
                        else:
                            snip = min(int(snippet_len), qlen)
                            comp_terms_in = (
                                rec1.terms[s1 : s1 + snip],
                                rec2.terms[s2 : s2 + snip],
                            )
                            combined_terms = q[:snip]

                        ids_c, names_c, coeffs_c, shifts_c, tnames_c, comp_terms_c = _canonicalize_components(
                            ids=(rec1.id, rec2.id),
                            names=(rec1.name, rec2.name),
                            coeffs=(1, 1),
                            shifts=(s1, s2),
                            t_names=("id", "id"),
                            component_terms=comp_terms_in,
                        )
                        # Canonicalize + dedupe after verifying, so we don't miss
                        # cases where only one anchor orientation is "solvable"
                        # due to zeros in the prefix.
                        key = ("mul", ids_c, shifts_c, tnames_c)
                        if key in seen:
                            continue
                        seen.add(key)

                        t_weights = (0.0, 0.0)
                        comp_val = _combo_complexity(coeffs_c, shifts_c, t_weights=t_weights)
                        if max_complexity is not None and comp_val > max_complexity:
                            continue
                        pop_bonus = _popularity_bonus((rec1, rec2))
                        score = _combo_score(qlen, coeffs_c, shifts_c, t_weights=t_weights, pop_bonus=pop_bonus)
                        if min_score is not None and score < min_score:
                            continue

                        expr = _format_pointwise_expr("mul", ids_c, shifts_c, tnames_c)
                        latex = _format_pointwise_latex("mul", ids_c, shifts_c, tnames_c)

                        results.append(
                            (m := CombinationMatch(
                                ids=ids_c,
                                names=names_c,
                                coeffs=coeffs_c,
                                shifts=shifts_c,
                                length=qlen,
                                score=score,
                                expression=expr,
                                latex_expression=latex,
                                component_transforms=tnames_c,
                                component_terms=comp_terms_c,
                                combined_terms=combined_terms,
                            ))
                        )
                        if on_match is not None:
                            on_match(m)
                        if limit and len(results) >= int(limit):
                            return _sorted_and_trim(results, limit, dedupe_family=dedupe_family)

        return _sorted_and_trim(results, limit, dedupe_family=dedupe_family)
    finally:
        fetcher.close()


def search_convolution_two_sequence_combinations(
    query: SequenceQuery,
    candidates: Sequence[SequenceRecord] | Iterable[SequenceRecord],
    *,
    ops: Sequence[str] = ("cauchy", "dirichlet"),
    max_length: int = 32,
    limit: int = 20,
    max_candidates: int | None = None,
    max_checks: int | None = None,
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    component_transforms: Sequence[ComponentTransform] | None = None,
    snippet_len: int | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """Search Cauchy/Dirichlet convolutions a(n) of two sequences.

    For Cauchy, c_n = sum_{k=0..n} A_k B_{n-k} (0-based indices).
    For Dirichlet, c(n) = sum_{d|n} A(d) B(n/d) using 1-based n with seq[i]=A(i+1).
    Strong caps: disabled for long queries via `max_length`, and bounded by max_candidates/max_checks/max_time_s.
    """
    q = query.terms
    qlen = len(q)
    if qlen < query.min_match_length or qlen == 0:
        return []
    if any(t is None for t in q):
        return []
    if qlen > max_length:
        return []

    ops = [o for o in ops if o in {"cauchy", "dirichlet"}]
    if not ops:
        return []

    records = _dedup_records_by_id(candidates)
    if max_candidates is not None:
        records = records[:max_candidates]

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()
    checks = 0
    t_start = time_fn()

    transforms = list(component_transforms or [t for t in _default_component_transforms() if t.name == "id"])
    transformed = _TransformedSequenceCache()

    if snippet_len is None:
        snippet_len = len(query.terms)

    for rec1, rec2 in combinations_with_replacement(records, 2):
        same_rec = rec1.id == rec2.id
        for t1 in transforms:
            seq1 = transformed.get(rec1, t1)
            for t2 in transforms:
                if same_rec:
                    # Avoid symmetric duplicates for self-pairs (A * B == B * A).
                    key1 = (t1.weight, t1.name)
                    key2 = (t2.weight, t2.name)
                    if key1 > key2:
                        continue
                seq2 = transformed.get(rec2, t2)
                for op in ops:
                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                        return _sorted_and_trim(results, limit)
                    checks += 1
                    if max_checks is not None and checks > max_checks:
                        return _sorted_and_trim(results, limit)
                    if op == "cauchy":
                        ok = _cauchy_convolution_matches(seq1, seq2, q)
                    else:
                        ok = _dirichlet_convolution_matches(seq1, seq2, q)
                    if not ok:
                        continue
                    key = (op, rec1.id, rec2.id, t1.name, t2.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    pop_bonus = _popularity_bonus((rec1, rec2))
                    t_weights = (t1.weight, t2.weight)
                    coeffs = (1, 1)
                    shifts = (0, 0)
                    comp_val = _combo_complexity(coeffs, shifts, t_weights=t_weights)
                    if max_complexity is not None and comp_val > max_complexity:
                        continue
                    score = _combo_score(qlen, coeffs, shifts, t_weights=t_weights, pop_bonus=pop_bonus)
                    if min_score is not None and score < min_score:
                        continue
                    if snippet_len is None:
                        comp_terms = None
                        combined_terms = None
                    else:
                        snip = min(snippet_len, qlen)
                        comp_terms = (seq1[:snip], seq2[:snip])
                        combined_terms = q[:snip]

                    ids_c, names_c, coeffs_c, shifts_c, tnames_c, comp_terms_c = _canonicalize_components(
                        ids=(rec1.id, rec2.id),
                        names=(rec1.name, rec2.name),
                        coeffs=coeffs,
                        shifts=shifts,
                        t_names=(t1.name, t2.name),
                        component_terms=comp_terms,
                    )
                    expr = _format_convolution_expr(op, ids_c, tnames_c)
                    latex = _format_convolution_latex(op, ids_c, tnames_c)

                    results.append(
                        (m := CombinationMatch(
                            ids=ids_c,
                            names=names_c,
                            coeffs=coeffs_c,
                            shifts=shifts_c,
                            length=qlen,
                            score=score,
                            expression=expr,
                            latex_expression=latex,
                            component_transforms=tnames_c,
                            component_terms=comp_terms_c,
                            combined_terms=combined_terms,
                        )
                    )
                    )
                    if on_match is not None:
                        on_match(m)

    return _sorted_and_trim(results, limit)


def search_three_sequence_combinations(
    query: SequenceQuery,
    candidates: Sequence[SequenceRecord] | Iterable[SequenceRecord],
    *,
    coeffs: Sequence[int] = (-2, -1, 1, 2),
    max_shift: int = 0,
    max_shift_back: int = 0,
    limit: int = 10,
    max_candidates: int | None = 20,
    max_checks: int | None = 300_000,
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    max_combinations: int | None = None,
    component_transforms: Sequence[ComponentTransform] | None = None,
    snippet_len: int | None = None,
    use_rational: bool = False,
    allow_self_reference: bool = False,
    min_score: float | None = None,
    max_complexity: float | None = None,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """
    Brute-force search for integer linear combinations of three sequences equal to the query prefix.
    Much heavier than the two-sequence search; defaults are stricter.
    """
    q = query.terms
    qlen = len(q)
    if qlen < query.min_match_length or qlen == 0:
        return []
    if any(t is None for t in q):
        return []

    coeff_list = list(coeffs)
    coeff_set = set(coeff_list)
    if not coeff_list and not use_rational:
        return []

    records = _dedup_records_by_id(candidates)
    if max_candidates is not None:
        records = records[:max_candidates]

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()
    checks = 0
    t_start = time_fn()

    shift_vals = _shift_values(max_shift, max_shift_back)
    transforms = list(component_transforms or [t for t in _default_component_transforms() if t.name == "id"])
    transformed = _TransformedSequenceCache()

    if snippet_len is None:
        snippet_len = len(query.terms)

    # Fast path: the most common and most useful triple identities are pure
    # shift=0, transform=id matches. When users enable extra component
    # transforms/shifts (e.g. `--preset max`), the full brute-force triple
    # enumeration can take a long time before the first hit.
    #
    # This stage tries to find any "plain" triple matches first using a prefix
    # hash over candidates (like the expanded DB-wide solver does), then falls
    # back to the general triple search for the remaining cases.
    #
    # Scope:
    # - shift=0 only,
    # - component transform=id only,
    # - uses a short prefix key (up to 5 terms),
    # - still verifies the full aligned prefix length (match_len).
    #
    # It is intentionally conservative and bounded by the same max_time/max_checks
    # guards as the slow path.
    # Keep this early stage small: it should find easy wins quickly, not spend
    # minutes exploring coefficient grids when no plain triple exists.
    if max_time_s is None:
        fast_cap_s = 1.0
    else:
        fast_cap_s = max(0.0, min(2.0, 0.2 * float(max_time_s)))

    id_t = next((t for t in transforms if t.name == "id"), None)
    if id_t is not None and fast_cap_s > 0 and qlen >= query.min_match_length and qlen >= 3:
        prefix_len = min(5, qlen)
        if prefix_len >= 3:
            q_prefix = tuple(int(q[i]) for i in range(prefix_len))
            by_prefix: dict[tuple[int, ...], list[int]] = {}
            prefixes: list[tuple[int, ...] | None] = [None] * len(records)
            eligible: list[int] = []
            for idx, rec in enumerate(records):
                if len(rec.terms) < prefix_len:
                    continue
                pref = tuple(int(rec.terms[i]) for i in range(prefix_len))
                prefixes[idx] = pref
                by_prefix.setdefault(pref, []).append(idx)
                eligible.append(idx)

            # Prefer small coefficients first (this is "time-to-first-hit", not
            # exhaustiveness — the slow path still covers the full set).
            coeff_order = sorted({int(c) for c in coeff_list}, key=lambda c: (abs(c), c))
            fast_coeffs = coeff_order[: min(len(coeff_order), 6)]
            fast_coeff_nonzero = [c for c in fast_coeffs if c != 0]
            fast_deadline_s = t_start + float(fast_cap_s)

            if fast_coeffs and fast_coeff_nonzero and eligible:
                # Enumerate i<j<k (indices into `records`) so we can pre-seed `seen`
                # in the same shape as the slow path and avoid re-discovering the
                # same (id,id,id,0,0,0) triples later.
                for pos_i, idx1 in enumerate(eligible):
                    if time_fn() >= fast_deadline_s:
                        break
                    pref1 = prefixes[idx1]
                    if pref1 is None:
                        continue
                    rec1 = records[idx1]
                    s1 = rec1.terms
                    for idx2 in eligible[pos_i + 1 :]:
                        if time_fn() >= fast_deadline_s:
                            break
                        pref2 = prefixes[idx2]
                        if pref2 is None:
                            continue
                        rec2 = records[idx2]
                        s2 = rec2.terms

                        for a in fast_coeffs:
                            for b in fast_coeffs:
                                if a == 0 and b == 0:
                                    continue
                                # Compute residual prefix for the third component:
                                #   residual = q_prefix - a*pref1 - b*pref2
                                residual = [qv - a * x - b * y for qv, x, y in zip(q_prefix, pref1, pref2)]

                                for c in fast_coeff_nonzero:
                                    if time_fn() >= fast_deadline_s:
                                        break
                                    comp_val = _combo_complexity((a, b, c), (0, 0, 0), t_weights=(0.0, 0.0, 0.0))
                                    if max_complexity is not None and comp_val > max_complexity:
                                        continue

                                    needed: list[int] = []
                                    ok_div = True
                                    for r in residual:
                                        if r % c != 0:
                                            ok_div = False
                                            break
                                        needed.append(r // c)
                                    if not ok_div:
                                        continue
                                    idxs3 = by_prefix.get(tuple(needed))
                                    if not idxs3:
                                        continue

                                    for idx3 in idxs3:
                                        # Enforce idx1<idx2<idx3 to avoid generating
                                        # the same triple multiple ways.
                                        if idx3 <= idx2:
                                            continue
                                        if time_fn() >= fast_deadline_s:
                                            break

                                        checks += 1
                                        if max_checks is not None and checks > max_checks:
                                            return _sorted_and_trim(results, limit)
                                        if max_combinations is not None and checks > max_combinations:
                                            return _sorted_and_trim(results, limit)

                                        rec3 = records[idx3]
                                        s3 = rec3.terms
                                        match_len = min(qlen, len(s1), len(s2), len(s3))
                                        if match_len < query.min_match_length:
                                            continue

                                        # Quick guards before full verification.
                                        if a * s1[0] + b * s2[0] + c * s3[0] != q[0]:
                                            continue
                                        if match_len > 1 and (a * s1[1] + b * s2[1] + c * s3[1] != q[1]):
                                            continue
                                        if match_len > 2 and (
                                            a * s1[match_len - 1] + b * s2[match_len - 1] + c * s3[match_len - 1] != q[match_len - 1]
                                        ):
                                            continue
                                        if not all(
                                            (a * x + b * y + c * z) == qv for x, y, z, qv in zip(s1[:match_len], s2[:match_len], s3[:match_len], q[:match_len])
                                        ):
                                            continue

                                        key = (rec1.id, rec2.id, rec3.id, "id", "id", "id", a, b, c, 0, 0, 0)
                                        if key in seen:
                                            continue
                                        seen.add(key)

                                        m = _build_linear_match(
                                            (rec1, rec2, rec3),
                                            coeffs=(a, b, c),
                                            shifts=(0, 0, 0),
                                            transform_names=("id", "id", "id"),
                                            transform_weights=(0.0, 0.0, 0.0),
                                            aligned_terms=(s1, s2, s3),
                                            target_terms=q,
                                            length=match_len,
                                            snippet_len=snippet_len,
                                            min_score=min_score,
                                            max_complexity=max_complexity,
                                        )
                                        if m is None:
                                            continue
                                        results.append(m)
                                        if on_match is not None:
                                            on_match(m)
                                        if limit and len(results) >= limit:
                                            return _sorted_and_trim(results, limit)

    record_triples = (
        combinations_with_replacement(records, 3) if allow_self_reference else combinations(records, 3)
    )
    for rec1, rec2, rec3 in record_triples:
        for t1 in transforms:
            seq1 = transformed.get(rec1, t1)
            for s1 in shift_vals:
                for t2 in transforms:
                    seq2 = transformed.get(rec2, t2)
                    for s2 in shift_vals:
                        for t3 in transforms:
                            seq3 = transformed.get(rec3, t3)
                            for s3 in shift_vals:
                                # Symmetry guards for repeated component ids.
                                if rec1.id == rec2.id and (t1.name, s1) > (t2.name, s2):
                                    continue
                                if rec2.id == rec3.id and (t2.name, s2) > (t3.name, s3):
                                    continue
                                if (
                                    rec1.id == rec2.id == rec3.id
                                    and t1.name == t2.name == t3.name
                                    and s1 == s2 == s3
                                ):
                                    # Same component repeated three times only
                                    # yields merged-coefficient variants.
                                    continue
                                if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                    return _sorted_and_trim(results, limit)
                                span = _aligned_span(
                                    len(query.terms),
                                    (len(seq1), len(seq2), len(seq3)),
                                    (s1, s2, s3),
                                    min_match_length=query.min_match_length,
                                )
                                if span is None:
                                    continue
                                q_start, match_len = span
                                s1_start = q_start + s1
                                s2_start = q_start + s2
                                s3_start = q_start + s3
                                if use_rational:
                                    q_slice = query.terms[q_start : q_start + match_len]
                                    slice1 = seq1[s1_start : s1_start + match_len]
                                    slice2 = seq2[s2_start : s2_start + match_len]
                                    slice3 = seq3[s3_start : s3_start + match_len]
                                    sol3 = _solve_rational_coeffs_triple(slice1, slice2, slice3, q_slice)
                                    if sol3 is not None and _rational_solution_is_pathological(
                                        sol3, (slice1, slice2, slice3), q_slice
                                    ):
                                        sol3 = None
                                    coeff_triples = [sol3] if sol3 else []
                                    # Keep the legacy scoring/emit path below.
                                    triple_iter = coeff_triples
                                else:
                                    # Fast path: solve for (a,b,c) from 3 rows when independent; brute force only when degenerate.
                                    sol_int: tuple[int, int, int] | None = None
                                    det_found = False
                                    for i in range(match_len - 2):
                                        a1 = seq1[s1_start + i]
                                        b1 = seq2[s2_start + i]
                                        c1 = seq3[s3_start + i]
                                        y1 = query.terms[q_start + i]

                                        a2 = seq1[s1_start + i + 1]
                                        b2 = seq2[s2_start + i + 1]
                                        c2 = seq3[s3_start + i + 1]
                                        y2 = query.terms[q_start + i + 1]

                                        a3 = seq1[s1_start + i + 2]
                                        b3 = seq2[s2_start + i + 2]
                                        c3 = seq3[s3_start + i + 2]
                                        y3 = query.terms[q_start + i + 2]

                                        det = (
                                            a1 * (b2 * c3 - b3 * c2)
                                            - b1 * (a2 * c3 - a3 * c2)
                                            + c1 * (a2 * b3 - a3 * b2)
                                        )
                                        if det == 0:
                                            continue
                                        det_found = True
                                        det_a = (
                                            y1 * (b2 * c3 - b3 * c2)
                                            - b1 * (y2 * c3 - y3 * c2)
                                            + c1 * (y2 * b3 - y3 * b2)
                                        )
                                        det_b = (
                                            a1 * (y2 * c3 - y3 * c2)
                                            - y1 * (a2 * c3 - a3 * c2)
                                            + c1 * (a2 * y3 - a3 * y2)
                                        )
                                        det_c = (
                                            a1 * (b2 * y3 - b3 * y2)
                                            - b1 * (a2 * y3 - a3 * y2)
                                            + y1 * (a2 * b3 - a3 * b2)
                                        )
                                        if (det_a % det) != 0 or (det_b % det) != 0 or (det_c % det) != 0:
                                            sol_int = None
                                        else:
                                            sol_int = (det_a // det, det_b // det, det_c // det)
                                        break

                                    if det_found:
                                        checks += 1
                                        if max_checks is not None and checks > max_checks:
                                            return _sorted_and_trim(results, limit)
                                        if max_combinations is not None and checks > max_combinations:
                                            return _sorted_and_trim(results, limit)
                                        if sol_int is None:
                                            continue
                                        a, b, c = sol_int
                                        if a == 0 and b == 0 and c == 0:
                                            continue
                                        if a not in coeff_set or b not in coeff_set or c not in coeff_set:
                                            continue

                                        q0 = query.terms[q_start]
                                        if a * seq1[s1_start] + b * seq2[s2_start] + c * seq3[s3_start] != q0:
                                            continue
                                        if match_len > 1:
                                            q1 = query.terms[q_start + 1]
                                            if (
                                                a * seq1[s1_start + 1]
                                                + b * seq2[s2_start + 1]
                                                + c * seq3[s3_start + 1]
                                                != q1
                                            ):
                                                continue
                                        if match_len > 2:
                                            q_last = query.terms[q_start + match_len - 1]
                                            if (
                                                a * seq1[s1_start + match_len - 1]
                                                + b * seq2[s2_start + match_len - 1]
                                                + c * seq3[s3_start + match_len - 1]
                                                != q_last
                                            ):
                                                continue

                                        ok = True
                                        for j in range(match_len):
                                            if (
                                                a * seq1[s1_start + j]
                                                + b * seq2[s2_start + j]
                                                + c * seq3[s3_start + j]
                                                != query.terms[q_start + j]
                                            ):
                                                ok = False
                                                break
                                        if not ok:
                                            continue
                                        triple_iter = [(a, b, c)]
                                    else:
                                        # Degenerate: brute force.
                                        triple_iter = ((a, b, c) for a in coeff_list for b in coeff_list for c in coeff_list)

                                for triple in triple_iter:
                                    if triple is None:
                                        continue
                                    a, b, c = triple
                                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                        return _sorted_and_trim(results, limit)
                                    if use_rational:
                                        checks += 1
                                    else:
                                        # Degenerate brute-force path: count every evaluated triple.
                                        if not det_found:
                                            checks += 1
                                    if max_checks is not None and checks > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and checks > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    if not use_rational and not det_found and a == 0 and b == 0 and c == 0:
                                        continue
                                    if match_len:
                                        if a * seq1[s1_start] + b * seq2[s2_start] + c * seq3[s3_start] != query.terms[q_start]:
                                            continue
                                        if match_len > 1 and (
                                            a * seq1[s1_start + 1] + b * seq2[s2_start + 1] + c * seq3[s3_start + 1]
                                            != query.terms[q_start + 1]
                                        ):
                                            continue
                                        if match_len > 2 and (
                                            a * seq1[s1_start + match_len - 1]
                                            + b * seq2[s2_start + match_len - 1]
                                            + c * seq3[s3_start + match_len - 1]
                                            != query.terms[q_start + match_len - 1]
                                        ):
                                            continue
                                    ok = True
                                    for j in range(match_len):
                                        if (
                                            a * seq1[s1_start + j]
                                            + b * seq2[s2_start + j]
                                            + c * seq3[s3_start + j]
                                            != query.terms[q_start + j]
                                        ):
                                            ok = False
                                            break
                                    if not ok:
                                        continue
                                    key = (rec1.id, rec2.id, rec3.id, t1.name, t2.name, t3.name, a, b, c, s1, s2, s3)
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    coeff_tuple = (a, b, c)
                                    shift_tuple = (s1, s2, s3)
                                    m = _build_linear_match(
                                        (rec1, rec2, rec3),
                                        coeffs=coeff_tuple,
                                        shifts=shift_tuple,
                                        transform_names=(t1.name, t2.name, t3.name),
                                        transform_weights=(t1.weight, t2.weight, t3.weight),
                                        aligned_terms=(
                                            seq1[s1_start : s1_start + match_len],
                                            seq2[s2_start : s2_start + match_len],
                                            seq3[s3_start : s3_start + match_len],
                                        ),
                                        target_terms=query.terms[q_start : q_start + match_len],
                                        length=match_len,
                                        snippet_len=snippet_len,
                                        min_score=min_score,
                                        max_complexity=max_complexity,
                                    )
                                    if m is None:
                                        continue
                                    results.append(m)
                                    if on_match is not None:
                                        on_match(m)

    return _sorted_and_trim(results, limit)


def _parse_prefix_key(prefix_key: str, n: int) -> tuple[int, ...] | None:
    """
    Parse a comma-joined prefix key into integers.

    The in-memory prefix index stores keys as text for speed/memory, but some
    arithmetic needs numeric values.
    """
    if not prefix_key:
        return None
    parts = prefix_key.split(",")
    if len(parts) < n:
        return None
    try:
        return tuple(int(parts[i]) for i in range(int(n)))
    except ValueError:
        return None


def _needed_prefix_key(residual: Sequence[int], a: int, p1: Sequence[int], b: int) -> str | None:
    """
    Solve for prefix key p2 in: a*p1 + b*p2 = residual.

    Returns the comma-joined key string if each coordinate is an integer.
    """
    out: list[int] = []
    for r, x in zip(residual, p1):
        num = int(r) - int(a) * int(x)
        if b == 1:
            out.append(num)
            continue
        if b == -1:
            out.append(-num)
            continue
        if num % b != 0:
            return None
        out.append(num // b)
    return ",".join(str(v) for v in out)


def search_two_sequence_combinations_expanded(
    query: SequenceQuery,
    db_path: Path,
    *,
    coeffs: Sequence[int] = (-2, -1, 1, 2),
    limit: int = 20,
    max_shift: int = 0,
    scan_strides: Sequence[int] = (100, 50, 20, 10, 5, 2, 1),
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    snippet_len: int | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    dedupe_family: bool = True,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """
    Expanded pair search that uses the DB-wide prefix index, rather than the
    normal candidate pool. This helps find decompositions like:

      A100000 + A200000

    even when individual components don't resemble the query.

    Current scope/limits:
    - forward shifts up to `max_shift` (requires DB columns prefix5_1..prefix5_k),
    - no backward shifts,
    - per-component transform=id only,
    - uses the first 5 query terms as a key (requires len(query) >= 5),
      then verifies the full query.
    """
    q = query.terms
    qlen = len(q)
    if qlen < max(query.min_match_length, 5) or qlen == 0:
        return []
    if any(t is None for t in q):
        return []

    coeff_list = [int(c) for c in coeffs if int(c) != 0]
    if not coeff_list:
        return []

    t_start = time_fn()
    if max_time_s is not None and max_time_s <= 0:
        return []
    deadline_s = (t_start + float(max_time_s)) if max_time_s is not None else None

    prefix_len = 5
    max_shift = max(0, int(max_shift))
    index = _get_shifted_prefix_index(Path(db_path), prefix_len, max_shift, deadline_s=deadline_s, time_fn=time_fn)
    if deadline_s is not None and time_fn() >= deadline_s:
        return []
    q_prefix = tuple(int(q[i]) for i in range(prefix_len))

    coeff_order = sorted(set(coeff_list), key=lambda c: (abs(c), c))
    stride_order = [int(s) for s in scan_strides if int(s) > 0]
    if 1 not in stride_order:
        stride_order.append(1)

    scan_cache: dict[int, list[int]] = {}

    def _scan_indices(stride: int) -> list[int]:
        cached = scan_cache.get(stride)
        if cached is not None:
            return cached
        out: list[int] = []
        for i, (num, length) in enumerate(zip(index.id_nums, index.lengths)):
            if length < qlen:
                continue
            if num != -1 and stride != 1 and (num % stride) != 0:
                continue
            out.append(i)
        scan_cache[stride] = out
        return out

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()

    # Progressive scan order (avoid processing the same idx1 multiple times when
    # stride_order is e.g. 100,50,20,...,1). The priority still prefers "nice"
    # A-numbers, but each candidate anchor is evaluated at most once.
    scan_order: list[int] = []
    seen_idx1: set[int] = set()
    for stride in stride_order:
        for idx in _scan_indices(stride):
            if idx in seen_idx1:
                continue
            seen_idx1.add(idx)
            scan_order.append(idx)

    fetcher = _SequenceFetcher(Path(db_path))
    try:
        for idx1 in scan_order:
            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                break
            rec1: SequenceRecord | None = None
            bad_rec1 = False

            id1 = index.ids[idx1]
            len1 = index.lengths[idx1]

            # Shifts: only forward shifts, and only those supported by the DB schema.
            shifts = [s for s in range(0, max_shift + 1) if s in index.shifts]
            if not shifts:
                shifts = [0]

            for s1_shift in shifts:
                if bad_rec1:
                    break
                if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                    break
                if len1 < qlen + s1_shift:
                    continue
                pref1_key = index.prefixes_by_shift[s1_shift][idx1]
                if not pref1_key:
                    continue
                pref1 = _parse_prefix_key(pref1_key, prefix_len)
                if pref1 is None:
                    continue

                for a in coeff_order:
                    if bad_rec1:
                        break
                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                        break
                    for b in coeff_order:
                        if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                            break
                        for s2_shift in shifts:
                            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                break
                            comp_val = _combo_complexity((a, b), (s1_shift, s2_shift), t_weights=(0.0, 0.0))
                            if max_complexity is not None and comp_val > max_complexity:
                                continue
                            needed_key = _needed_prefix_key(q_prefix, a, pref1, b)
                            if needed_key is None:
                                continue
                            idxs2 = _prefix_locations(index.by_prefix_by_shift[s2_shift], needed_key)
                            if not idxs2:
                                continue

                            # Fetch rec1 lazily only on a potential hit.
                            if rec1 is None:
                                rec1 = fetcher.get(id1)
                                if not rec1 or len(rec1.terms) < (qlen + s1_shift):
                                    bad_rec1 = True
                                    break

                            s1_terms = rec1.terms[s1_shift : s1_shift + qlen]

                            for idx2 in idxs2:
                                if idx2 < idx1:
                                    continue
                                if idx2 == idx1:
                                    continue
                                id2 = index.ids[idx2]
                                len2 = index.lengths[idx2]
                                if len2 < qlen + s2_shift:
                                    continue

                                key = (id1, id2, a, b, s1_shift, s2_shift)
                                if key in seen:
                                    continue
                                seen.add(key)

                                rec2 = fetcher.get(id2)
                                if not rec2 or len(rec2.terms) < (qlen + s2_shift):
                                    continue

                                s2_terms = rec2.terms[s2_shift : s2_shift + qlen]
                                if qlen:
                                    if a * s1_terms[0] + b * s2_terms[0] != q[0]:
                                        continue
                                    if qlen > 1 and (a * s1_terms[1] + b * s2_terms[1] != q[1]):
                                        continue
                                    if qlen > 2 and (a * s1_terms[-1] + b * s2_terms[-1] != q[-1]):
                                        continue
                                if not all((a * x + b * y) == qv for x, y, qv in zip(s1_terms, s2_terms, q)):
                                    continue

                                coeff_tuple = (a, b)
                                shift_tuple = (s1_shift, s2_shift)
                                m = _build_linear_match(
                                    (rec1, rec2),
                                    coeffs=coeff_tuple,
                                    shifts=shift_tuple,
                                    transform_names=("id", "id"),
                                    transform_weights=(0.0, 0.0),
                                    aligned_terms=(s1_terms, s2_terms),
                                    target_terms=q,
                                    length=qlen,
                                    snippet_len=snippet_len,
                                    min_score=min_score,
                                    max_complexity=max_complexity,
                                )
                                if m is None:
                                    continue
                                results.append(m)
                                if on_match is not None:
                                    on_match(m)

                                if limit and len(results) >= limit:
                                    return _sorted_and_trim(results, limit, dedupe_family=dedupe_family)

        return _sorted_and_trim(results, limit, dedupe_family=dedupe_family)
    finally:
        fetcher.close()


def _anchor_candidates(
    index: PrefixIndex,
    q_prefix: tuple[int, ...],
    coeffs: Sequence[int],
    *,
    qlen: int,
    max_anchors: int,
    scan_order: Sequence[int] | None = None,
    max_scan: int | None = None,
) -> list[tuple[int, int, int]]:
    """
    Return up to max_anchors anchors as (best_dist, idx, best_coeff).
    `best_dist` is computed over the prefix only.
    """
    if max_anchors <= 0:
        return []

    # Scanning every sequence to rank anchors is expensive on a full OEIS snapshot.
    # Instead, prefer a stride-based scan order (same idea as the main search) and
    # rank only the first window. This preserves the "nice A-number first" bias
    # while keeping startup latency low.
    if scan_order is None:
        scan_order = list(range(len(index.ids)))
    max_scan_n = int(max_scan) if max_scan is not None else max(5000, int(max_anchors) * 25)

    heap: list[tuple[int, str, int, int]] = []
    seen_idx: set[int] = set()
    scanned = 0

    # Keep smallest distances; store id for deterministic tie-break.
    for idx in scan_order:
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        if index.lengths[idx] < qlen:
            continue
        pref = _parse_prefix_key(index.prefixes[idx], index.prefix_len)
        if pref is None:
            continue
        seq_id = index.ids[idx]

        best_dist: int | None = None
        best_c: int | None = None
        for c in coeffs:
            if c == 0:
                continue
            dist = 0
            for qv, pv in zip(q_prefix, pref):
                dist += abs(qv - c * pv)
                if best_dist is not None and dist > best_dist:
                    break
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_c = c
        if best_dist is None or best_c is None:
            continue
        item = (-best_dist, seq_id, idx, best_c)  # worst has most-negative dist
        if len(heap) < max_anchors:
            heapq.heappush(heap, item)
        else:
            if item > heap[0]:
                heapq.heapreplace(heap, item)

        scanned += 1
        if scanned >= max_scan_n:
            break

    out = [(-neg, idx, best_c) for neg, _sid, idx, best_c in heap]
    out.sort(key=lambda t: (t[0], index.ids[t[1]]))
    return out


def search_three_sequence_combinations_expanded(
    query: SequenceQuery,
    db_path: Path,
    *,
    coeffs: Sequence[int] = (-2, -1, 1, 2),
    limit: int = 10,
    max_anchors: int = 400,
    scan_strides: Sequence[int] = (100, 50, 20, 10, 5, 2, 1),
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    snippet_len: int | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """
    Expanded triple search that uses the DB-wide prefix index, rather than the
    usual candidate pool. This helps find decompositions like:

      A100000 + A200000 + A300000

    even when individual components don't resemble the query.

    Current scope/limits:
    - shift=0 only (no forward/back shifts),
    - per-component transform=id only,
    - uses the first 5 query terms as a key (requires len(query) >= 5),
      then verifies the full query.
    """
    q = query.terms
    qlen = len(q)
    if qlen < max(query.min_match_length, 5) or qlen == 0:
        return []
    if any(t is None for t in q):
        return []

    coeff_list = [int(c) for c in coeffs if int(c) != 0]
    if not coeff_list:
        return []

    t_start = time_fn()
    if max_time_s is not None and max_time_s <= 0:
        return []
    deadline_s = (t_start + float(max_time_s)) if max_time_s is not None else None

    prefix_len = 5
    index = _get_prefix_index(Path(db_path), prefix_len, deadline_s=deadline_s, time_fn=time_fn)
    if deadline_s is not None and time_fn() >= deadline_s:
        return []
    q_prefix = tuple(int(q[i]) for i in range(prefix_len))

    coeff_order = sorted(set(coeff_list), key=lambda c: (abs(c), c))
    stride_order = [int(s) for s in scan_strides if int(s) > 0]
    if 1 not in stride_order:
        stride_order.append(1)

    # Cache scan sets for progressive coverage (mod stride).
    scan_cache: dict[int, list[int]] = {}

    def _scan_indices(stride: int) -> list[int]:
        cached = scan_cache.get(stride)
        if cached is not None:
            return cached
        out: list[int] = []
        for i, (num, length) in enumerate(zip(index.id_nums, index.lengths)):
            if length < qlen:
                continue
            if num != -1 and stride != 1 and (num % stride) != 0:
                continue
            out.append(i)
        scan_cache[stride] = out
        return out

    # Progressive scan order (avoid duplicates across stride_order). This is
    # especially important for triples because the inner loop is heavy.
    scan_order: list[int] = []
    seen_idx1: set[int] = set()
    for stride in stride_order:
        for idx in _scan_indices(stride):
            if idx in seen_idx1:
                continue
            seen_idx1.add(idx)
            scan_order.append(idx)

    anchors = _anchor_candidates(
        index,
        q_prefix,
        coeff_order,
        qlen=qlen,
        max_anchors=max_anchors,
        scan_order=scan_order,
    )

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()

    fetcher = _SequenceFetcher(Path(db_path))
    try:
        prefix_int_cache: dict[int, tuple[int, ...]] = {}
        for _dist, idx3, best_c3 in anchors:
            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                break
            id3 = index.ids[idx3]
            pref3_key = index.prefixes[idx3]
            pref3 = prefix_int_cache.get(idx3)
            if pref3 is None:
                pref3 = _parse_prefix_key(pref3_key, prefix_len)
                if pref3 is None:
                    continue
                prefix_int_cache[idx3] = pref3
            rec3 = fetcher.get(id3)
            if not rec3 or len(rec3.terms) < qlen:
                continue
            s3 = rec3.terms[:qlen]

            # Try the best coefficient first for this anchor, then the rest by complexity.
            c3_order = [best_c3] + [c for c in coeff_order if c != best_c3]
            for c3 in c3_order:
                if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                    break
                residual_prefix = tuple(qv - c3 * pv for qv, pv in zip(q_prefix, pref3))

                for idx1 in scan_order:
                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                        break
                    if idx1 == idx3:
                        continue
                    id1 = index.ids[idx1]
                    pref1_key = index.prefixes[idx1]
                    pref1 = prefix_int_cache.get(idx1)
                    if pref1 is None:
                        pref1 = _parse_prefix_key(pref1_key, prefix_len)
                        if pref1 is None:
                            continue
                        prefix_int_cache[idx1] = pref1
                    rec1: SequenceRecord | None = None
                    bad_rec1 = False
                    s1: list[int] | None = None

                    for b in coeff_order:
                        if bad_rec1:
                            break
                        if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                            break
                        for a in coeff_order:
                            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                break
                            needed_key = _needed_prefix_key(residual_prefix, a, pref1, b)
                            if needed_key is None:
                                continue
                            idxs2 = _prefix_locations(index.by_prefix, needed_key)
                            if not idxs2:
                                continue
                            # Fetch rec1 lazily only on a potential hit; reuse across all (a,b).
                            if rec1 is None:
                                rec1 = fetcher.get(id1)
                                if not rec1 or len(rec1.terms) < qlen:
                                    bad_rec1 = True
                                    break
                                s1 = rec1.terms[:qlen]

                            for idx2 in idxs2:
                                if idx2 == idx1 or idx2 == idx3:
                                    continue
                                if index.lengths[idx2] < qlen:
                                    continue
                                id2 = index.ids[idx2]

                                key = (id1, id2, id3, a, b, c3)
                                if key in seen:
                                    continue
                                seen.add(key)

                                rec2 = fetcher.get(id2)
                                if not rec2 or len(rec2.terms) < qlen:
                                    continue

                                if s1 is None:
                                    continue
                                s2 = rec2.terms[:qlen]
                                if qlen:
                                    if a * s1[0] + b * s2[0] + c3 * s3[0] != q[0]:
                                        continue
                                    if qlen > 1 and (a * s1[1] + b * s2[1] + c3 * s3[1] != q[1]):
                                        continue
                                    if qlen > 2 and (a * s1[-1] + b * s2[-1] + c3 * s3[-1] != q[-1]):
                                        continue
                                if not all(
                                    (a * x + b * y + c3 * z) == qv for x, y, z, qv in zip(s1, s2, s3, q)
                                ):
                                    continue

                                coeff_tuple = (a, b, c3)
                                shift_tuple = (0, 0, 0)
                                m = _build_linear_match(
                                    (rec1, rec2, rec3),
                                    coeffs=coeff_tuple,
                                    shifts=shift_tuple,
                                    transform_names=("id", "id", "id"),
                                    transform_weights=(0.0, 0.0, 0.0),
                                    aligned_terms=(s1, s2, s3),
                                    target_terms=q,
                                    length=qlen,
                                    snippet_len=snippet_len,
                                    min_score=min_score,
                                    max_complexity=max_complexity,
                                )
                                if m is None:
                                    continue
                                results.append(m)
                                if on_match is not None:
                                    on_match(m)

                                if limit and len(results) >= limit:
                                    return _sorted_and_trim(results, limit)
        return _sorted_and_trim(results, limit)
    finally:
        fetcher.close()


def search_mod_class_combinations(
    query: SequenceQuery,
    db_path: Path,
    *,
    moduli: Sequence[int] = (2, 3),
    limit: int = 20,
    max_shift: int = 0,
    per_class_limit: int = 12,
    max_combinations: int | None = 2000,
    max_time_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    snippet_len: int | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    on_match: Callable[[CombinationMatch], None] | None = None,
) -> list[CombinationMatch]:
    """
    Search "mod-class" decompositions of the form:

      a(mn+r) = X_r(n+s_r)

    where r=0..m-1 indexes residue classes, and each X_r is an OEIS sequence id.
    The special case m=2 corresponds to an interleaving:

      a(2n)   = X_0(n+s_0)
      a(2n+1) = X_1(n+s_1)

    Current scope/limits:
    - exact matching only (no wildcards),
    - forward shifts only (s_r >= 0), up to `max_shift`,
    - per-component transform=id only (no diff/psum).
    - uses the first 5 terms of each residue-class subsequence as a key, then
      verifies the full residue-class match.
    """
    q = query.terms
    qlen = len(q)
    if qlen < max(query.min_match_length, 5) or qlen == 0:
        return []
    if any(t is None for t in q):
        return []
    if limit is not None and int(limit) <= 0:
        return []

    t_start = time_fn()
    if max_time_s is not None and max_time_s <= 0:
        return []
    deadline_s = (t_start + float(max_time_s)) if max_time_s is not None else None

    prefix_len = 5
    max_shift = max(0, int(max_shift))
    per_class_limit = max(1, int(per_class_limit))
    max_combinations_n = int(max_combinations) if max_combinations is not None else None

    lookup = sqlite3.connect(db_path)
    lookup.row_factory = sqlite3.Row
    columns = {row[1] for row in lookup.execute("PRAGMA table_info(sequences)")}
    shifts = tuple(
        shift
        for shift in range(max_shift + 1)
        if _prefix_col_name(prefix_len, shift) in columns
    ) or (0,)
    if deadline_s is not None:
        lookup.set_progress_handler(lambda: int(time_fn() >= deadline_s), 2000)
    fetcher = _SequenceFetcher(Path(db_path))
    try:
        results: list[CombinationMatch] = []
        seen: set[tuple[int, tuple[str, ...], tuple[int, ...]]] = set()

        for m in moduli:
            if deadline_s is not None and time_fn() >= deadline_s:
                break
            try:
                modulus = int(m)
            except (TypeError, ValueError):
                continue
            if modulus <= 1:
                continue
            if modulus > qlen:
                continue

            # Split query into residue classes.
            classes: list[list[int]] = []
            for r in range(modulus):
                cls = [int(q[i]) for i in range(r, qlen, modulus)]
                classes.append(cls)
            if any(len(cls) < prefix_len for cls in classes):
                continue

            # Candidate sequences for each residue class, as (OEIS id, shift).
            # Exact prefix-column lookups avoid materializing the full 400k-row
            # shifted index for a handful of residue-class keys.
            cand_by_r: list[list[tuple[str, int]]] = []
            for r, cls in enumerate(classes):
                key_txt = ",".join(str(v) for v in cls[:prefix_len])
                found: list[tuple[str, int]] = []
                for s in shifts:
                    if deadline_s is not None and time_fn() >= deadline_s:
                        break
                    col = _prefix_col_name(prefix_len, s)
                    try:
                        rows = lookup.execute(
                            f"SELECT id FROM sequences WHERE {col} = ? AND length >= ? ORDER BY id",
                            (key_txt, s + len(cls)),
                        )
                        for row in rows:
                            if deadline_s is not None and time_fn() >= deadline_s:
                                break
                            seq_id = str(row["id"])
                            rec = fetcher.get(seq_id)
                            if rec and rec.terms[s : s + len(cls)] == cls:
                                found.append((seq_id, s))
                                if len(found) >= per_class_limit:
                                    break
                    except sqlite3.OperationalError as exc:
                        if "interrupted" not in str(exc).lower():
                            raise
                        break
                    if len(found) >= per_class_limit:
                        break
                # Deterministic ordering: simplest shifts first, then low A-number.
                found.sort(key=lambda item: (abs(item[1]), item[1], item[0]))
                # De-dupe exact (id,shift) in case the same row is reachable via multiple shifts keys.
                uniq: list[tuple[str, int]] = []
                seen_pair: set[tuple[str, int]] = set()
                for seq_id, s in found:
                    k = (seq_id, int(s))
                    if k in seen_pair:
                        continue
                    seen_pair.add(k)
                    uniq.append(k)
                    if len(uniq) >= per_class_limit:
                        break
                cand_by_r.append(uniq)

            if any(not lst for lst in cand_by_r):
                continue

            # Cartesian product across residue classes.
            scanned = 0
            for combo in product(*cand_by_r):
                if deadline_s is not None and time_fn() >= deadline_s:
                    break
                scanned += 1
                if max_combinations_n is not None and scanned > max_combinations_n:
                    break

                ids = tuple(seq_id for seq_id, _s in combo)
                component_shifts = tuple(int(s) for _seq_id, s in combo)
                key = (modulus, ids, component_shifts)
                if key in seen:
                    continue
                seen.add(key)

                recs: list[SequenceRecord] = []
                names: list[str | None] = []
                ok = True
                for (seq_id, s), cls in zip(combo, classes):
                    rec = fetcher.get(seq_id)
                    if not rec or len(rec.terms) < int(s) + len(cls):
                        ok = False
                        break
                    # Safety: re-check match (classes are small; keeps logic robust to caching/mutations).
                    if rec.terms[int(s) : int(s) + len(cls)] != cls:
                        ok = False
                        break
                    recs.append(rec)
                    names.append(rec.name)
                if not ok:
                    continue

                coeff_tuple = tuple(1 for _ in ids)
                t_names = tuple("id" for _ in ids)
                t_weights = tuple(0.0 for _ in ids)
                comp_val = _combo_complexity(coeff_tuple, component_shifts, t_weights=t_weights)
                if max_complexity is not None and comp_val > max_complexity:
                    continue
                pop_bonus = _popularity_bonus(tuple(recs))
                score = _combo_score(qlen, coeff_tuple, component_shifts, t_weights=t_weights, pop_bonus=pop_bonus)
                if min_score is not None and score < min_score:
                    continue

                expr = _format_modclass_expr(modulus, ids, component_shifts, t_names)
                latex = _format_modclass_latex(modulus, ids, component_shifts, t_names)

                if snippet_len is None:
                    comp_terms = None
                    combined_terms = None
                else:
                    snip_total = min(int(snippet_len), qlen)
                    combined_terms = [int(x) for x in q[:snip_total]]
                    comp_terms_parts: list[list[int]] = []
                    for r, ((_seq_id, s), cls) in enumerate(zip(combo, classes)):
                        need = len(q[r:snip_total:modulus])
                        comp_terms_parts.append(indexed_terms := recs[r].terms[int(s) : int(s) + need])
                        # Defensive: ensure we never emit out-of-sync component snippets.
                        if indexed_terms != cls[:need]:
                            comp_terms_parts[-1] = cls[:need]
                    comp_terms = tuple(comp_terms_parts)

                results.append(
                    (match := CombinationMatch(
                        ids=ids,
                        names=tuple(names),
                        coeffs=coeff_tuple,
                        shifts=component_shifts,
                        length=qlen,
                        score=score,
                        expression=expr,
                        latex_expression=latex,
                        component_transforms=t_names,
                        component_terms=comp_terms,
                        combined_terms=combined_terms,
                    ))
                )
                if on_match is not None:
                    on_match(match)

        results.sort(
            key=lambda m: (
                -m.score,
                _combo_complexity(m.coeffs, m.shifts),
                -(m.latex_expression is not None),
                -m.length,
                m.ids,
                m.shifts,
            )
        )
        return results[:limit] if limit else results
    finally:
        lookup.close()
        fetcher.close()
