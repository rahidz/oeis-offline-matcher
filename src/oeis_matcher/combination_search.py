from __future__ import annotations

import time
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Iterable, Sequence

from .models import CombinationMatch, SequenceQuery, SequenceRecord
from .transforms import diff_transform, partial_sum_transform


def _shift_str(k: int) -> str:
    return "n" if k == 0 else f"n+{k}"


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


def _combo_complexity(coeffs: Sequence[int], shifts: Sequence[int], t_weights: Sequence[float] | None = None) -> float:
    """
    Penalize larger coefficients, shifts, extra components, and per-component transforms.
    """
    comp = sum(abs(c) for c in coeffs) + 0.5 * sum(abs(s) for s in shifts)
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


def _format_expr(ids: Sequence[str], coeffs: Sequence[int], shifts: Sequence[int], t_names: Sequence[str]) -> str:
    def _tn(tn: str, id_: str, shift: int) -> str:
        if tn == "id":
            return f"{id_}({_shift_str(shift)})"
        return f"{tn}({id_}({_shift_str(shift)}) )".replace(") )", ")")

    parts = [f"{c}*{_tn(tn, id_, s)}" for id_, c, s, tn in zip(ids, coeffs, shifts, t_names)]
    return "a(n) = " + " + ".join(parts)


def _format_latex(ids: Sequence[str], coeffs: Sequence[int], shifts: Sequence[int], t_names: Sequence[str]) -> str:
    def shift_to_tex(k: int) -> str:
        return "n" if k == 0 else f"n+{k}"

    def t_tex(name: str, id_: str, s: int) -> str:
        base = f"\\mathrm{{{id_}}}({shift_to_tex(s)})"
        if name == "id":
            return base
        if name == "diff":
            return f"\\Delta\\,{base}"
        if name == "partial_sum":
            return f"\\mathrm{{psum}}\\,{base}"
        return f"\\mathrm{{{name}}}\\,{base}"

    parts = [f"{c}\\,{t_tex(tn, id_, s)}" for id_, c, s, tn in zip(ids, coeffs, shifts, t_names)]
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
    if not coeff_list:
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
                start1 = max(0, s1)
                if len(seq1) - start1 < qlen:
                    continue
                slice1 = seq1[start1 : start1 + qlen]
                for t2 in transforms:
                    seq2 = t2.func(rec2.terms)
                    for s2 in shift_vals:
                        start2 = max(0, s2)
                        if len(seq2) - start2 < qlen:
                            continue
                        slice2 = seq2[start2 : start2 + qlen]
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
                                combined = [a * x + b * y for x, y in zip(slice1, slice2)]
                                if combined != q:
                                    continue
                                key = (rec1.id, rec2.id, t1.name, t2.name, a, b, s1, s2)
                                if key in seen:
                                    continue
                                seen.add(key)
                                pop_bonus = _popularity_bonus((rec1, rec2))
                                t_weights = (t1.weight, t2.weight)
                                score = _combo_score(qlen, (a, b), (s1, s2), t_weights=t_weights, pop_bonus=pop_bonus)
                                expr = _format_expr((rec1.id, rec2.id), (a, b), (s1, s2), (t1.name, t2.name))
                                latex = _format_latex((rec1.id, rec2.id), (a, b), (s1, s2), (t1.name, t2.name))
                                comp_terms = None if snippet_len is None else (slice1[:snippet_len], slice2[:snippet_len])
                                combined_terms = query.terms[:snippet_len] if snippet_len is not None else None

                                results.append(
                                    CombinationMatch(
                                        ids=(rec1.id, rec2.id),
                                        names=(rec1.name, rec2.name),
                                        coeffs=(a, b),
                                        shifts=(s1, s2),
                                        length=qlen,
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
    if not coeff_list:
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
                start1 = max(0, s1)
                if len(seq1) - start1 < qlen:
                    continue
                slice1 = seq1[start1 : start1 + qlen]
                for t2 in transforms:
                    seq2 = t2.func(rec2.terms)
                    for s2 in shift_vals:
                        start2 = max(0, s2)
                        if len(seq2) - start2 < qlen:
                            continue
                        slice2 = seq2[start2 : start2 + qlen]
                        for t3 in transforms:
                            seq3 = t3.func(rec3.terms)
                            for s3 in shift_vals:
                                start3 = max(0, s3)
                                if len(seq3) - start3 < qlen:
                                    continue
                                slice3 = seq3[start3 : start3 + qlen]
                                for a in coeff_list:
                                    for b in coeff_list:
                                        for c in coeff_list:
                                            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                                                return _sorted_and_trim(results, limit)
                                            checks += 1
                                            if max_checks is not None and checks > max_checks:
                                                return _sorted_and_trim(results, limit)
                                            if max_combinations is not None and checks > max_combinations:
                                                return _sorted_and_trim(results, limit)
                                            if a == 0 and b == 0 and c == 0:
                                                continue
                                            combined = [a * x + b * y + c * z for x, y, z in zip(slice1, slice2, slice3)]
                                            if combined != q:
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
                                            score = _combo_score(qlen, coeff_tuple, shift_tuple, t_weights=t_weights, pop_bonus=pop_bonus)
                                            expr = _format_expr((rec1.id, rec2.id, rec3.id), coeff_tuple, shift_tuple, t_names)
                                            latex = _format_latex((rec1.id, rec2.id, rec3.id), coeff_tuple, shift_tuple, t_names)
                                            comp_terms = None if snippet_len is None else (
                                                slice1[:snippet_len],
                                                slice2[:snippet_len],
                                                slice3[:snippet_len],
                                            )
                                            combined_terms = query.terms[:snippet_len] if snippet_len is not None else None

                                            results.append(
                                                CombinationMatch(
                                                    ids=(rec1.id, rec2.id, rec3.id),
                                                    names=(rec1.name, rec2.name, rec3.name),
                                                    coeffs=coeff_tuple,
                                                    shifts=shift_tuple,
                                                    length=qlen,
                                                    score=score,
                                                    expression=expr,
                                                    latex_expression=latex,
                                                    component_transforms=t_names,
                                                    component_terms=comp_terms,
                                                    combined_terms=combined_terms,
                                                )
                                            )

    return _sorted_and_trim(results, limit)
