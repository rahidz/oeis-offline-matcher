from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
import time

from .config import load_config
from .matcher import candidate_sequences, match_exact, match_exact_db
from .models import Match, SequenceQuery, AnalysisResult
from .query import parse_query
from .ranking import rank_candidates_for_query
from .transform_search import search_transform_matches
from .transforms import default_transforms
from .candidates import get_candidate_bucket
from .combination_search import (
    resolve_component_transforms,
    search_convolution_two_sequence_combinations,
    search_pointwise_two_sequence_combinations,
    search_three_sequence_combinations,
    search_two_sequence_combinations,
)
from .similarity import growth_rate


def match_exact_terms(
    terms: Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    allow_subsequence: bool = False,
    fallback_subsequence: bool = True,
    fallback_full_scan: bool = True,
    limit: int | None = 10,
    show_terms: int | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
) -> List[Match]:
    """
    Convenience wrapper around match_exact for library use.
    """
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = SequenceQuery(
        terms=list(terms),
        min_match_length=min_match_length,
        allow_subsequence=allow_subsequence,
    )
    matches = match_exact_db(query, db_path, limit=limit, snippet_len=show_terms)
    if matches or allow_subsequence or not fallback_subsequence:
        return matches
    # fallback to subsequence search using invariant-filtered candidates first, optionally full scan
    fallback_query = SequenceQuery(
        terms=list(terms),
        min_match_length=min_match_length,
        allow_subsequence=True,
    )
    fmatches = match_exact_db(fallback_query, db_path, limit=limit, snippet_len=show_terms)
    if fmatches or not fallback_full_scan:
        return fmatches
    # final try: full scan
    from .storage import iter_sequences

    return match_exact(fallback_query, iter_sequences(db_path), limit=limit, snippet_len=show_terms)


def search_transforms(
    terms: Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    allow_subsequence: bool = False,
    max_depth: int = 2,
    limit: int = 20,
    show_terms: int | None = None,
    max_time: float | None = None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
    scale_values: Iterable[int] = (-3, -2, -1, 2, 3),
    beta_values: Iterable[int] = (),
    shift_values: Iterable[int] = (1, 2),
    decimate_params: Iterable[tuple[int, int]] = (),
    allow_diff: bool = True,
    allow_partial_sum: bool = True,
    allow_abs: bool = True,
    allow_gcd_norm: bool = True,
    full_scan: bool = False,
    allow_binomial: bool = False,
    allow_euler: bool = False,
    digit_sum_bases: Iterable[int] = (),
    modulus_values: Iterable[int] = (),
    allow_xor_index: bool = False,
    allow_rle: bool = False,
    allow_log: bool = False,
    log_bases: Iterable[float] = (),
    allow_exp: bool = False,
    exp_bases: Iterable[float] = (),
    allow_mobius: bool = False,
    allow_omega: bool = False,
    allow_bigomega: bool = False,
    allow_tau: bool = False,
    allow_sigma: bool = False,
    allow_phi: bool = False,
    allow_v2: bool = False,
    allow_index_square: bool = False,
    allow_prime_index: bool = False,
    allow_constant_outputs: bool = False,
) -> List[Match]:
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = SequenceQuery(
        terms=list(terms),
        min_match_length=min_match_length,
        allow_subsequence=allow_subsequence,
    )
    transforms = default_transforms(
        scale_values=scale_values,
        beta_values=beta_values,
        shift_values=shift_values,
        allow_diff=allow_diff,
        diff_orders=(1,),
        allow_partial_sum=allow_partial_sum,
        allow_cumprod=False,
        allow_abs=allow_abs,
        allow_gcd_norm=allow_gcd_norm,
        decimate_params=decimate_params,
        allow_reverse=False,
        allow_even_odd=False,
        moving_sum_windows=(),
        allow_popcount=False,
        allow_digit_sum=bool(digit_sum_bases),
        digit_sum_bases=digit_sum_bases,
        modulus_values=modulus_values,
        allow_xor_index=allow_xor_index,
        allow_rle=allow_rle,
        allow_rle_decode=False,
        allow_concat=False,
        allow_log=allow_log,
        log_bases=log_bases,
        allow_exp=allow_exp,
        exp_bases=exp_bases,
        allow_mobius=allow_mobius,
        allow_binomial=allow_binomial,
        allow_euler=allow_euler,
        allow_omega=allow_omega,
        allow_bigomega=allow_bigomega,
        allow_tau=allow_tau,
        allow_sigma=allow_sigma,
        allow_phi=allow_phi,
        allow_v2=allow_v2,
        allow_index_square=allow_index_square,
        allow_prime_index=allow_prime_index,
    )
    return search_transform_matches(
        query,
        db_path,
        max_depth=max_depth,
        transforms=transforms,
        limit=limit,
        snippet_len=show_terms,
        full_scan=full_scan,
        max_time_s=max_time,
        min_score=min_score,
        max_complexity=max_complexity,
        variance_band=variance_band,
        growth_band=growth_band,
        allow_constant_outputs=allow_constant_outputs,
    )


def search_combinations(
    terms: Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    coeffs: Iterable[int] = (-3, -2, -1, 1, 2, 3),
    max_shift: int = 0,
    max_shift_back: int = 0,
    limit: int = 20,
    candidate_cap: int = 40,
    max_checks: int | None = 200_000,
    max_time: float | None = None,
    max_combinations: int | None = None,
    component_transforms: Iterable[str] | None = None,
    combo_unfiltered: bool = False,
    snippet_len: int | None = None,
    use_rational: bool = False,
    combo_min_score: float | None = None,
    combo_max_complexity: float | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
) -> list:
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = SequenceQuery(terms=list(terms), min_match_length=min_match_length, allow_subsequence=False)
    bucket = get_candidate_bucket(
        query,
        db_path,
        exact_limit=candidate_cap,
        similar_limit=candidate_cap,
        max_records=candidate_cap,
        fill_unfiltered=True,
        skip_prefix_filter=combo_unfiltered,
        variance_band=variance_band,
        growth_band=growth_band,
    )
    return search_two_sequence_combinations(
        query,
        bucket.records,
        coeffs=tuple(coeffs),
        max_shift=max_shift,
        max_shift_back=max_shift_back,
        limit=limit,
        max_candidates=candidate_cap,
        max_checks=max_checks,
        max_time_s=max_time,
        max_combinations=max_combinations,
        component_transforms=resolve_component_transforms(list(component_transforms) if component_transforms is not None else None),
        snippet_len=snippet_len,
        use_rational=use_rational,
        min_score=combo_min_score,
        max_complexity=combo_max_complexity,
    )


def search_three_combinations(
    terms: Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    coeffs: Iterable[int] = (-2, -1, 1, 2),
    max_shift: int = 0,
    max_shift_back: int = 0,
    limit: int = 10,
    candidate_cap: int = 25,
    max_checks: int | None = 300_000,
    max_time: float | None = None,
    max_combinations: int | None = None,
    component_transforms: Iterable[str] | None = None,
    combo_unfiltered: bool = False,
    snippet_len: int | None = None,
    use_rational: bool = False,
    triple_min_score: float | None = None,
    triple_max_complexity: float | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
) -> list:
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = SequenceQuery(terms=list(terms), min_match_length=min_match_length, allow_subsequence=False)
    bucket = get_candidate_bucket(
        query,
        db_path,
        exact_limit=candidate_cap,
        similar_limit=candidate_cap,
        max_records=candidate_cap,
        fill_unfiltered=True,
        skip_prefix_filter=combo_unfiltered,
        variance_band=variance_band,
        growth_band=growth_band,
    )
    return search_three_sequence_combinations(
        query,
        bucket.records,
        coeffs=tuple(coeffs),
        max_shift=max_shift,
        max_shift_back=max_shift_back,
        limit=limit,
        max_candidates=candidate_cap,
        max_checks=max_checks,
        max_time_s=max_time,
        max_combinations=max_combinations,
        component_transforms=resolve_component_transforms(list(component_transforms) if component_transforms is not None else None),
        snippet_len=snippet_len,
        use_rational=use_rational,
        min_score=triple_min_score,
        max_complexity=triple_max_complexity,
    )


def analyze_sequence(
    sequence_text: str | Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    allow_subsequence: bool = False,
    exact_limit: int = 10,
    transform_limit: int = 10,
    transform_depth: int = 2,
    transform_args: Optional[Dict] = None,
    transform_max_time: float | None = None,
    similarity: int = 0,
    similarity_min_corr: float | None = None,
    similarity_max_mse: float | None = None,
    combos: int = 0,
    triples: int = 0,
    combo_coeffs: Iterable[int] = (-3, -2, -1, 1, 2, 3),
    combo_max_shift: int = 0,
    combo_max_shift_back: int = 0,
    combo_rational: bool = False,
    combo_candidates: int = 40,
    combo_max_checks: int | None = 200_000,
    combo_max_time: float | None = None,
    combo_max_combinations: int | None = None,
    triple_candidates: int = 25,
    triple_max_checks: int | None = 300_000,
    triple_max_time: float | None = None,
    triple_max_combinations: int | None = None,
    triple_max_shift_back: int = 0,
    combo_component_transforms: Iterable[str] | None = None,
    triple_rational: bool = False,
    combo_min_score: float | None = None,
    combo_max_complexity: float | None = None,
    triple_min_score: float | None = None,
    triple_max_complexity: float | None = None,
    pointwise_limit: int = 0,
    pointwise_ops: Iterable[str] = (),
    pointwise_max_time: float | None = None,
    convolution_limit: int = 0,
    convolution_ops: Iterable[str] = (),
    convolution_max_time: float | None = None,
    convolution_max_length: int = 32,
    fallback_subsequence: bool = True,
    fallback_full_scan: bool = False,
    show_terms: int | None = None,
    as_dataclass: bool = False,
    collect_timings: bool = False,
    full_transform_scan: bool = False,
    combo_unfiltered: bool = False,
    variance_band: float | None = None,
    growth_band: float | None = None,
) -> Dict[str, object]:
    """
    High-level, deterministic analysis pipeline used by CLI but available as a library call.
    Returns a dict (default) or AnalysisResult dataclass with exact, transform, similarity, and combination matches.
    """
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])

    if isinstance(sequence_text, str):
        query = parse_query(sequence_text, min_match_length=min_match_length, allow_subsequence=allow_subsequence)
    else:
        query = SequenceQuery(terms=list(sequence_text), min_match_length=min_match_length, allow_subsequence=allow_subsequence)

    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    def _variance(vals: list[int]) -> float | None:
        if len(vals) < 2:
            return None
        m = sum(vals) / len(vals)
        return sum((v - m) ** 2 for v in vals) / len(vals)

    # Exact
    exact = match_exact_db(query, db_path, limit=exact_limit, snippet_len=show_terms)
    fallback_used = False
    if not exact and not query.allow_subsequence and fallback_subsequence:
        fb_query = SequenceQuery(terms=query.terms, min_match_length=min_match_length, allow_subsequence=True)
        exact = match_exact_db(fb_query, db_path, limit=exact_limit, snippet_len=show_terms)
        if not exact and fallback_full_scan:
            from .storage import iter_sequences

            exact = match_exact(fb_query, iter_sequences(db_path), limit=exact_limit, snippet_len=show_terms)
        fallback_used = bool(exact)
    if collect_timings:
        timings["exact_ms"] = 1000 * (time.perf_counter() - t0)
    t1 = time.perf_counter()

    # Transforms
    t_args = transform_args or {}
    snip_len = show_terms if show_terms is not None else (min(len(query.terms), 20) if query.terms else None)

    if transform_limit and transform_limit > 0:
        t_matches = search_transforms(
            query.terms,
            db_path=db_path,
            min_match_length=min_match_length,
            allow_subsequence=allow_subsequence,
            max_depth=transform_depth,
            limit=transform_limit,
            show_terms=snip_len,
            full_scan=full_transform_scan,
            max_time=transform_max_time,
            **t_args,
        )
    else:
        t_matches = []
    if collect_timings:
        timings["transform_ms"] = 1000 * (time.perf_counter() - t1)
    t2 = time.perf_counter()

    sim_matches = rank_candidates_for_query(
        query,
        db_path,
        top_k=similarity,
        min_corr=similarity_min_corr,
        max_mse=similarity_max_mse,
        variance_band=variance_band,
        growth_band=growth_band,
    ) if similarity else []
    if collect_timings:
        timings["similarity_ms"] = 1000 * (time.perf_counter() - t2)

    combo_matches = []
    triple_matches = []
    pointwise_matches = []
    convolution_matches = []
    if combos or triples or (pointwise_limit and pointwise_ops) or (convolution_limit and convolution_ops):
        combo_coeffs_seq = combo_coeffs
        cap = max(int(combo_candidates or 0), int(triple_candidates or 0))
        if cap <= 0:
            cap = max(int(combo_candidates or 0), 1)

        bucket = get_candidate_bucket(
            query,
            db_path,
            exact_limit=cap,
            similar_limit=cap,
            max_records=cap,
            fill_unfiltered=True,
            skip_prefix_filter=combo_unfiltered,
            variance_band=variance_band,
            growth_band=growth_band,
        )
        if combo_component_transforms is None:
            comp_names = None
        elif isinstance(combo_component_transforms, str):
            comp_names = [t.strip() for t in combo_component_transforms.split(",") if t.strip()]
        else:
            comp_names = list(combo_component_transforms)
        comp_transforms = resolve_component_transforms(comp_names)

        if combos:
            combo_start = time.perf_counter()
            combo_matches = search_two_sequence_combinations(
                query,
                bucket.records,
                coeffs=tuple(combo_coeffs_seq),
                max_shift=combo_max_shift,
                max_shift_back=combo_max_shift_back,
                limit=combos,
                max_candidates=combo_candidates,
                max_checks=combo_max_checks,
                max_time_s=combo_max_time,
                max_combinations=combo_max_combinations,
                component_transforms=comp_transforms,
                snippet_len=snip_len,
                use_rational=combo_rational,
                min_score=combo_min_score,
                max_complexity=combo_max_complexity,
            )
            combo_end = time.perf_counter()
        else:
            combo_start = combo_end = None

        if triples:
            triple_start = time.perf_counter()
            triple_matches = search_three_sequence_combinations(
                query,
                bucket.records,
                coeffs=tuple(combo_coeffs_seq),
                max_shift=combo_max_shift,
                max_shift_back=triple_max_shift_back,
                limit=triples,
                max_candidates=triple_candidates,
                max_checks=triple_max_checks,
                max_time_s=triple_max_time,
                max_combinations=triple_max_combinations,
                component_transforms=comp_transforms,
                snippet_len=snip_len,
                use_rational=triple_rational,
                min_score=triple_min_score,
                max_complexity=triple_max_complexity,
            )
            triple_end = time.perf_counter()
        else:
            triple_start = triple_end = None

        pw_ops = []
        if isinstance(pointwise_ops, str):
            pw_ops = [t.strip() for t in pointwise_ops.split(",") if t.strip()]
        else:
            pw_ops = list(pointwise_ops or ())
        if pointwise_limit and pw_ops:
            pw_start = time.perf_counter()
            pointwise_matches = search_pointwise_two_sequence_combinations(
                query,
                bucket.records,
                ops=tuple(pw_ops),
                max_shift=combo_max_shift,
                max_shift_back=combo_max_shift_back,
                limit=pointwise_limit,
                max_candidates=combo_candidates,
                max_checks=combo_max_checks,
                max_time_s=pointwise_max_time if pointwise_max_time is not None else combo_max_time,
                component_transforms=comp_transforms,
                snippet_len=snip_len,
                min_score=combo_min_score,
                max_complexity=combo_max_complexity,
            )
            pw_end = time.perf_counter()
        else:
            pw_start = pw_end = None

        conv_ops = []
        if isinstance(convolution_ops, str):
            conv_ops = [t.strip() for t in convolution_ops.split(",") if t.strip()]
        else:
            conv_ops = list(convolution_ops or ())
        if convolution_limit and conv_ops:
            conv_start = time.perf_counter()
            convolution_matches = search_convolution_two_sequence_combinations(
                query,
                bucket.records,
                ops=tuple(conv_ops),
                max_length=int(convolution_max_length),
                limit=convolution_limit,
                max_candidates=combo_candidates,
                max_checks=combo_max_checks,
                max_time_s=convolution_max_time if convolution_max_time is not None else combo_max_time,
                component_transforms=comp_transforms,
                snippet_len=snip_len,
                min_score=combo_min_score,
                max_complexity=combo_max_complexity,
            )
            conv_end = time.perf_counter()
        else:
            conv_start = conv_end = None

        if collect_timings:
            if combo_start is not None and combo_end is not None:
                timings["combination_ms"] = 1000 * (combo_end - combo_start)
            if triple_start is not None and triple_end is not None:
                timings["triple_ms"] = 1000 * (triple_end - triple_start)
            if pw_start is not None and pw_end is not None:
                timings["pointwise_ms"] = 1000 * (pw_end - pw_start)
            if conv_start is not None and conv_end is not None:
                timings["convolution_ms"] = 1000 * (conv_end - conv_start)

    similarity_rows = [
        {
            "id": c.record.id,
            "name": c.record.name,
            "corr": c.corr,
            "mse": c.mse,
            "scale": c.scale,
            "offset": c.offset,
        }
        for c in sim_matches
    ]

    query_var = _variance(query.terms)
    query_diff_var = _variance([query.terms[i + 1] - query.terms[i] for i in range(len(query.terms) - 1)]) if len(query.terms) > 1 else None
    query_growth = growth_rate([t for t in query.terms if t is not None])

    diag = {
        "query_length": len(query.terms),
        "exact_limit": exact_limit,
        "transform_limit": transform_limit,
        "similarity_limit": similarity,
        "combination_limit": combos,
        "combo_candidate_cap": combo_candidates,
        "combo_max_checks": combo_max_checks,
        "triple_limit": triples,
        "triple_candidate_cap": triple_candidates,
        "triple_max_checks": triple_max_checks,
        "pointwise_limit": pointwise_limit,
        "convolution_limit": convolution_limit,
        "variance_band": variance_band,
        "growth_band": growth_band,
        "query_var": query_var,
        "query_diff_var": query_diff_var,
        "query_growth": query_growth,
    }
    if fallback_used:
        diag["subsequence_fallback"] = True
    if collect_timings:
        diag["timings_ms"] = timings

    result = AnalysisResult(
        query=query.terms,
        exact_matches=exact,
        transform_matches=t_matches,
        similarity=similarity_rows,
        combinations=combo_matches,
        triple_combinations=triple_matches,
        pointwise_combinations=pointwise_matches,
        convolution_combinations=convolution_matches,
        diagnostics=diag,
    )

    return result if as_dataclass else result.to_dict()
