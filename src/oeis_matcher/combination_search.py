from __future__ import annotations

import time
from fractions import Fraction
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Iterable, Sequence

from .models import CombinationMatch, SequenceQuery, SequenceRecord
from .transforms import diff_transform, partial_sum_transform


def _shift_str(k: int) -> str:
    if k == 0:
        return "n"
    sign = "+" if k > 0 else "-"
    return f"n{sign}{abs(k)}"


@dataclass(frozen=True)
class ComponentTransform:
    name: str
    func: Callable[[list[int]], list[int]]
    weight: float = 0.0


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


def _sorted_and_trim(results: list[CombinationMatch], limit: int | None) -> list[CombinationMatch]:
    results.sort(
        key=lambda m: (
            -m.score,
            _combo_complexity(m.coeffs, m.shifts),
            -(m.latex_expression is not None),
            -m.length,
            m.ids,
        )
    )
    if limit:
        results = results[:limit]
    return results


def _aligned_slices(
    query_terms: Sequence[int],
    sequences: Sequence[Sequence[int]],
    shifts: Sequence[int],
    *,
    min_match_length: int,
) -> tuple[int, int, list[int], list[list[int]]] | None:
    """
    Compute aligned slices for the given shifts.

    If all shifts are non-negative, require full-length alignment with the query.
    If any shift is negative, allow partial overlap but enforce min_match_length.
    Returns (start_index_in_query, match_length, query_slice, sequence_slices) or None.
    """
    qlen = len(query_terms)
    if qlen == 0:
        return None

    if all(s >= 0 for s in shifts):
        if any(len(seq) - s < qlen for seq, s in zip(sequences, shifts)):
            return None
        start = 0
        length = qlen
    else:
        n_min = max(0, *[-s for s in shifts if s < 0])
        n_max = min(qlen, *[len(seq) - s for seq, s in zip(sequences, shifts)])
        length = n_max - n_min
        if length < min_match_length or length <= 0:
            return None
        start = n_min

    seq_slices = []
    for seq, shift in zip(sequences, shifts):
        seq_start = start + shift
        seq_end = seq_start + length
        if seq_start < 0 or seq_end > len(seq):
            return None
        seq_slices.append(seq[seq_start:seq_end])

    q_slice = query_terms[start : start + length]
    return start, length, q_slice, seq_slices


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
    if not coeff_list and not use_rational:
        return []

    records = list(candidates)
    records.sort(key=lambda r: r.id)
    if max_candidates is not None:
        records = records[:max_candidates]

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()
    checks = 0
    t_start = time_fn()

    shift_vals = range(-max_shift_back, max_shift + 1)
    transforms = list(component_transforms or [t for t in _default_component_transforms() if t.name == "id"])
    if snippet_len is None:
        snippet_len = len(query.terms)

    for rec1, rec2 in combinations(records, 2):
        for t1 in transforms:
            seq1 = t1.func(rec1.terms)
            for s1 in shift_vals:
                # If any shift is negative we allow partial overlap; otherwise require full-length match.
                for t2 in transforms:
                    seq2 = t2.func(rec2.terms)
                    for s2 in shift_vals:
                        alignment = _aligned_slices(
                            query.terms,
                            (seq1, seq2),
                            (s1, s2),
                            min_match_length=query.min_match_length,
                        )
                        if alignment is None:
                            continue
                        _q_start, match_len, q_slice, seq_slices = alignment
                        slice1, slice2 = seq_slices
                        if use_rational:
                            sol = _solve_rational_coeffs(slice1, slice2, q_slice)
                            coeff_pairs = [sol] if sol else []
                        else:
                            coeff_pairs = ((a, b) for a in coeff_list for b in coeff_list)
                        for pair in coeff_pairs:
                            if pair is None:
                                continue
                            a, b = pair
                            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                return _sorted_and_trim(results, limit)
                            checks += 1
                            if max_checks is not None and checks > max_checks:
                                return _sorted_and_trim(results, limit)
                            if max_combinations is not None and checks > max_combinations:
                                return _sorted_and_trim(results, limit)
                            if not use_rational and a == 0 and b == 0:
                                continue
                            combined = [a * x + b * y for x, y in zip(slice1, slice2)]
                            if combined != q_slice:
                                continue
                            key = (rec1.id, rec2.id, t1.name, t2.name, a, b, s1, s2)
                            if key in seen:
                                continue
                            seen.add(key)
                            pop_bonus = _popularity_bonus((rec1, rec2))
                            t_weights = (t1.weight, t2.weight)
                            comp_val = _combo_complexity((a, b), (s1, s2), t_weights=t_weights)
                            if max_complexity is not None and comp_val > max_complexity:
                                continue
                            score = _combo_score(match_len, (a, b), (s1, s2), t_weights=t_weights, pop_bonus=pop_bonus)
                            if min_score is not None and score < min_score:
                                continue
                            expr = _format_expr((rec1.id, rec2.id), (a, b), (s1, s2), (t1.name, t2.name))
                            latex = _format_latex((rec1.id, rec2.id), (a, b), (s1, s2), (t1.name, t2.name))
                            if snippet_len is None:
                                comp_terms = None
                                combined_terms = None
                            else:
                                snip = min(snippet_len, match_len)
                                comp_terms = (slice1[:snip], slice2[:snip])
                                combined_terms = q_slice[:snip]

                            results.append(
                                CombinationMatch(
                                    ids=(rec1.id, rec2.id),
                                    names=(rec1.name, rec2.name),
                                    coeffs=(a, b),
                                    shifts=(s1, s2),
                                    length=match_len,
                                    score=score,
                                    expression=expr,
                                    latex_expression=latex,
                                    component_transforms=(t1.name, t2.name),
                                    component_terms=comp_terms,
                                    combined_terms=combined_terms,
                                )
                            )

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
    min_score: float | None = None,
    max_complexity: float | None = None,
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
    if not coeff_list and not use_rational:
        return []

    records = list(candidates)
    records.sort(key=lambda r: r.id)
    if max_candidates is not None:
        records = records[:max_candidates]

    results: list[CombinationMatch] = []
    seen: set[tuple] = set()
    checks = 0
    t_start = time_fn()

    shift_vals = range(-max_shift_back, max_shift + 1)
    transforms = list(component_transforms or [t for t in _default_component_transforms() if t.name == "id"])
    if snippet_len is None:
        snippet_len = len(query.terms)

    for rec1, rec2, rec3 in combinations(records, 3):
        for t1 in transforms:
            seq1 = t1.func(rec1.terms)
            for s1 in shift_vals:
                for t2 in transforms:
                    seq2 = t2.func(rec2.terms)
                    for s2 in shift_vals:
                        for t3 in transforms:
                            seq3 = t3.func(rec3.terms)
                            for s3 in shift_vals:
                                alignment = _aligned_slices(
                                    query.terms,
                                    (seq1, seq2, seq3),
                                    (s1, s2, s3),
                                    min_match_length=query.min_match_length,
                                )
                                if alignment is None:
                                    continue
                                _q_start, match_len, q_slice, seq_slices = alignment
                                slice1, slice2, slice3 = seq_slices
                                if use_rational:
                                    sol3 = _solve_rational_coeffs_triple(slice1, slice2, slice3, q_slice)
                                    coeff_triples = [sol3] if sol3 else []
                                else:
                                    coeff_triples = ((a, b, c) for a in coeff_list for b in coeff_list for c in coeff_list)
                                for triple in coeff_triples:
                                    if triple is None:
                                        continue
                                    a, b, c = triple
                                    if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                        return _sorted_and_trim(results, limit)
                                    checks += 1
                                    if max_checks is not None and checks > max_checks:
                                        return _sorted_and_trim(results, limit)
                                    if max_combinations is not None and checks > max_combinations:
                                        return _sorted_and_trim(results, limit)
                                    if not use_rational and a == 0 and b == 0 and c == 0:
                                        continue
                                    combined = [a * x + b * y + c * z for x, y, z in zip(slice1, slice2, slice3)]
                                    if combined != q_slice:
                                        continue
                                    key = (rec1.id, rec2.id, rec3.id, t1.name, t2.name, t3.name, a, b, c, s1, s2, s3)
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    pop_bonus = _popularity_bonus((rec1, rec2, rec3))
                                    coeff_tuple = (a, b, c)
                                    shift_tuple = (s1, s2, s3)
                                    t_weights = (t1.weight, t2.weight, t3.weight)
                                    t_names = (t1.name, t2.name, t3.name)
                                    comp_val = _combo_complexity(coeff_tuple, shift_tuple, t_weights=t_weights)
                                    if max_complexity is not None and comp_val > max_complexity:
                                        continue
                                    score = _combo_score(match_len, coeff_tuple, shift_tuple, t_weights=t_weights, pop_bonus=pop_bonus)
                                    if min_score is not None and score < min_score:
                                        continue
                                    expr = _format_expr((rec1.id, rec2.id, rec3.id), coeff_tuple, shift_tuple, t_names)
                                    latex = _format_latex((rec1.id, rec2.id, rec3.id), coeff_tuple, shift_tuple, t_names)
                                    if snippet_len is None:
                                        comp_terms = None
                                        combined_terms = None
                                    else:
                                        snip = min(snippet_len, match_len)
                                        comp_terms = (
                                            slice1[:snip],
                                            slice2[:snip],
                                            slice3[:snip],
                                        )
                                        combined_terms = q_slice[:snip]

                                    results.append(
                                        CombinationMatch(
                                            ids=(rec1.id, rec2.id, rec3.id),
                                            names=(rec1.name, rec2.name, rec3.name),
                                            coeffs=coeff_tuple,
                                            shifts=shift_tuple,
                                            length=match_len,
                                            score=score,
                                            expression=expr,
                                            latex_expression=latex,
                                            component_transforms=t_names,
                                            component_terms=comp_terms,
                                            combined_terms=combined_terms,
                                        )
                                    )

    return _sorted_and_trim(results, limit)
