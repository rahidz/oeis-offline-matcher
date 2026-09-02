from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from .config import load_config
from .analysis import AnalysisEvent, AnalysisOptions, attach_candidate_provenance as _attach_candidate_provenance, run_analysis
from .matcher import match_exact, match_exact_db
from .models import AnalysisResult, Match, SequenceQuery
from .query import parse_oeis_ids, parse_query
from .transform_search import search_transform_matches
from .transforms import default_transforms
from .candidates import get_candidate_bucket
from .combination_search import (
    resolve_component_transforms,
    search_three_sequence_combinations,
    search_two_sequence_combinations,
)


def _normalize_provider_names(provider_names: Iterable[str] | str | None) -> tuple[str, ...] | None:
    if provider_names is None:
        return None
    if isinstance(provider_names, str):
        parts = [p.strip() for p in provider_names.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in provider_names if str(p).strip()]
    return tuple(parts) if parts else None


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
    exclude_ids: Iterable[str] | str | None = None,
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
    excluded = set(parse_oeis_ids(exclude_ids))
    search_limit = limit + len(excluded) if limit is not None and limit > 0 else limit

    def filtered(matches: Iterable[Match]) -> list[Match]:
        kept = [match for match in matches if match.id not in excluded]
        return kept[:limit] if limit is not None and limit > 0 else kept

    matches = filtered(match_exact_db(query, db_path, limit=search_limit, snippet_len=show_terms))
    if matches or allow_subsequence or not fallback_subsequence:
        return matches
    # fallback to subsequence search using invariant-filtered candidates first, optionally full scan
    fallback_query = SequenceQuery(
        terms=list(terms),
        min_match_length=min_match_length,
        allow_subsequence=True,
    )
    fmatches = filtered(match_exact_db(fallback_query, db_path, limit=search_limit, snippet_len=show_terms))
    if fmatches or not fallback_full_scan:
        return fmatches
    # final try: full scan
    from .storage import iter_sequences

    return filtered(match_exact(fallback_query, iter_sequences(db_path), limit=search_limit, snippet_len=show_terms))


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
    allow_inverse_binomial: bool = False,
    allow_euler: bool = False,
    allow_euler_ogf: bool = False,
    allow_inverse_euler_ogf: bool = False,
    allow_stirling1: bool = False,
    allow_stirling2: bool = False,
    allow_inverse_stirling1: bool = False,
    allow_inverse_stirling2: bool = False,
    allow_ogf_inverse: bool = False,
    allow_series_reversion: bool = False,
    allow_alt_sign: bool = False,
    vp_values: Iterable[int] = (),
    allow_lpf: bool = False,
    allow_gpf: bool = False,
    allow_rad: bool = False,
    allow_squarefree: bool = False,
    allow_liouville: bool = False,
    allow_ratio_int: bool = False,
    allow_index_triangular: bool = False,
    allow_index_fibonacci: bool = False,
    index_power_values: Iterable[int] = (),
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
    exclude_ids: Iterable[str] | str | None = None,
    on_match: Callable[[Match], None] | None = None,
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
        allow_alt_sign=allow_alt_sign,
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
        allow_inverse_binomial=allow_inverse_binomial,
        allow_euler=allow_euler,
        allow_euler_ogf=allow_euler_ogf,
        allow_inverse_euler_ogf=allow_inverse_euler_ogf,
        allow_stirling1=allow_stirling1,
        allow_stirling2=allow_stirling2,
        allow_inverse_stirling1=allow_inverse_stirling1,
        allow_inverse_stirling2=allow_inverse_stirling2,
        allow_ogf_inverse=allow_ogf_inverse,
        allow_series_reversion=allow_series_reversion,
        allow_omega=allow_omega,
        allow_bigomega=allow_bigomega,
        allow_tau=allow_tau,
        allow_sigma=allow_sigma,
        allow_phi=allow_phi,
        allow_v2=allow_v2,
        vp_values=vp_values,
        allow_lpf=allow_lpf,
        allow_gpf=allow_gpf,
        allow_rad=allow_rad,
        allow_squarefree=allow_squarefree,
        allow_liouville=allow_liouville,
        allow_ratio_int=allow_ratio_int,
        allow_index_square=allow_index_square,
        allow_prime_index=allow_prime_index,
        allow_index_triangular=allow_index_triangular,
        allow_index_fibonacci=allow_index_fibonacci,
        index_power_values=index_power_values,
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
        exclude_ids=parse_oeis_ids(exclude_ids),
        on_match=on_match,
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
    discovery: bool = False,
    discovery_limit: int = 16,
    discovery_max_time: float | None = 2.0,
    discovery_tools: Iterable[str] = ("sympy",),
    candidate_providers: Iterable[str] | None = None,
    wide_prefilter: bool = False,
    exclude_ids: Iterable[str] | str | None = None,
) -> list:
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = SequenceQuery(terms=list(terms), min_match_length=min_match_length, allow_subsequence=False)
    excluded = set(parse_oeis_ids(exclude_ids))
    bucket_cap = candidate_cap + len(excluded)
    bucket = get_candidate_bucket(
        query,
        db_path,
        exact_limit=bucket_cap,
        similar_limit=bucket_cap,
        max_records=bucket_cap,
        fill_unfiltered=True,
        skip_prefix_filter=combo_unfiltered,
        variance_band=variance_band,
        growth_band=growth_band,
        enable_discovery=discovery,
        discovery_limit=discovery_limit,
        discovery_max_time_s=discovery_max_time,
        discovery_tools=tuple(discovery_tools),
        candidate_providers=_normalize_provider_names(candidate_providers),
        widen_prefilter=wide_prefilter,
    )
    records = [record for record in bucket.records if record.id not in excluded][:candidate_cap]
    matches = search_two_sequence_combinations(
        query,
        records,
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
    return _attach_candidate_provenance(matches, bucket.provenance)


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
    allow_self_reference: bool = False,
    triple_min_score: float | None = None,
    triple_max_complexity: float | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
    discovery: bool = False,
    discovery_limit: int = 16,
    discovery_max_time: float | None = 2.0,
    discovery_tools: Iterable[str] = ("sympy",),
    candidate_providers: Iterable[str] | None = None,
    wide_prefilter: bool = False,
    exclude_ids: Iterable[str] | str | None = None,
) -> list:
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = SequenceQuery(terms=list(terms), min_match_length=min_match_length, allow_subsequence=False)
    excluded = set(parse_oeis_ids(exclude_ids))
    bucket_cap = candidate_cap + len(excluded)
    bucket = get_candidate_bucket(
        query,
        db_path,
        exact_limit=bucket_cap,
        similar_limit=bucket_cap,
        max_records=bucket_cap,
        fill_unfiltered=True,
        skip_prefix_filter=combo_unfiltered,
        variance_band=variance_band,
        growth_band=growth_band,
        enable_discovery=discovery,
        discovery_limit=discovery_limit,
        discovery_max_time_s=discovery_max_time,
        discovery_tools=tuple(discovery_tools),
        candidate_providers=_normalize_provider_names(candidate_providers),
        widen_prefilter=wide_prefilter,
    )
    records = [record for record in bucket.records if record.id not in excluded][:candidate_cap]
    matches = search_three_sequence_combinations(
        query,
        records,
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
        allow_self_reference=allow_self_reference,
        min_score=triple_min_score,
        max_complexity=triple_max_complexity,
    )
    return _attach_candidate_provenance(matches, bucket.provenance)


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
    combo_component_transforms: Iterable[str] | str | None = None,
    triple_rational: bool = False,
    combo_allow_self_reference: bool = False,
    combo_min_score: float | None = None,
    combo_max_complexity: float | None = None,
    triple_min_score: float | None = None,
    triple_max_complexity: float | None = None,
    pointwise_limit: int = 0,
    pointwise_ops: Iterable[str] | str = (),
    pointwise_max_time: float | None = None,
    convolution_limit: int = 0,
    convolution_ops: Iterable[str] | str = (),
    convolution_max_time: float | None = None,
    convolution_max_length: int = 32,
    combined_limit: int | None = None,
    combined_family_quota: int = 1,
    fallback_subsequence: bool = True,
    fallback_full_scan: bool = False,
    show_terms: int | None = None,
    show_formula: bool = True,
    as_dataclass: bool = False,
    collect_timings: bool = False,
    full_transform_scan: bool = False,
    combo_unfiltered: bool = False,
    variance_band: float | None = None,
    growth_band: float | None = None,
    combo_discovery: bool = False,
    combo_discovery_limit: int = 16,
    combo_discovery_max_time: float | None = 2.0,
    combo_discovery_tools: Iterable[str] = ("sympy",),
    combo_candidate_providers: Iterable[str] | str | None = None,
    combo_wide_prefilter: bool = False,
    preset: str | None = None,
    total_max_time: float | None = None,
    exact_max_time: float | None = None,
    similarity_max_time: float | None = None,
    combo_candidate_max_time: float | None = None,
    modclass_limit: int = 0,
    modclass_moduli: Iterable[int] = (2, 3),
    modclass_max_time: float | None = None,
    combo_expanded: bool = False,
    combo_expanded_max_time: float | None = None,
    combo_expanded_anchors: int = 400,
    combo_expanded_pointwise: bool | None = None,
    combo_expanded_pointwise_max_time: float | None = None,
    rerank: bool | None = None,
    rerank_limit: int = 0,
    rerank_default_quota: int = 1,
    rerank_quotas: dict[str, int] | None = None,
    exclude_exact_from_derived: bool | None = None,
    exclude_ids: Iterable[str] | str | None = None,
    on_event: Callable[[AnalysisEvent], None] | None = None,
) -> Dict[str, object] | AnalysisResult:
    """Run the shared exact/transform/similarity/combination analysis pipeline."""
    cfg = load_config()
    db_path = Path(db_path or cfg["paths"]["db"])
    query = (
        parse_query(sequence_text, min_match_length=min_match_length, allow_subsequence=allow_subsequence)
        if isinstance(sequence_text, str)
        else SequenceQuery(list(sequence_text), min_match_length, allow_subsequence)
    )
    snippet_len = show_terms if show_terms is not None else min(len(query.terms), 20)
    transform_options = dict(transform_args or {})
    normalized_exclude_ids = tuple(parse_oeis_ids(exclude_ids))

    def run_transforms(max_time: float | None, callback: Callable[[Match], None] | None) -> list[Match]:
        return search_transforms(
            query.terms,
            db_path=db_path,
            min_match_length=min_match_length,
            allow_subsequence=allow_subsequence,
            max_depth=transform_depth,
            limit=transform_limit,
            show_terms=snippet_len,
            full_scan=full_transform_scan,
            max_time=max_time,
            exclude_ids=normalized_exclude_ids,
            on_match=callback,
            **transform_options,
        )

    def names(value: Iterable[str] | str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
        if value is None:
            return default
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return tuple(str(part).strip() for part in value if str(part).strip())

    options = AnalysisOptions(
        preset=preset,
        exact_limit=exact_limit,
        show_terms=show_terms,
        derived_terms=snippet_len,
        fallback_subsequence=fallback_subsequence,
        fallback_full_scan=fallback_full_scan,
        exact_max_time=exact_max_time,
        transform_limit=transform_limit,
        transform_max_time=transform_max_time,
        similarity_limit=similarity,
        similarity_max_time=similarity_max_time,
        min_corr=similarity_min_corr,
        max_mse=similarity_max_mse,
        variance_band=variance_band,
        growth_band=growth_band,
        modclass_limit=modclass_limit,
        modclass_moduli=tuple(int(value) for value in modclass_moduli),
        modclass_max_time=modclass_max_time,
        combo_limit=combos,
        triple_limit=triples,
        pointwise_limit=pointwise_limit,
        pointwise_ops=names(pointwise_ops),
        pointwise_max_time=pointwise_max_time,
        convolution_limit=convolution_limit,
        convolution_ops=names(convolution_ops),
        convolution_max_time=convolution_max_time,
        convolution_max_length=convolution_max_length,
        combo_coeffs=tuple(combo_coeffs),
        combo_candidates=combo_candidates,
        combo_candidate_max_time=combo_candidate_max_time,
        combo_discovery=combo_discovery,
        combo_discovery_limit=combo_discovery_limit,
        combo_discovery_max_time=combo_discovery_max_time,
        combo_discovery_tools=names(combo_discovery_tools, ("sympy",)),
        combo_candidate_providers=_normalize_provider_names(combo_candidate_providers),
        combo_wide_prefilter=combo_wide_prefilter,
        combo_max_shift=combo_max_shift,
        combo_max_shift_back=combo_max_shift_back,
        combo_max_checks=combo_max_checks,
        combo_max_time=combo_max_time,
        combo_max_combinations=combo_max_combinations,
        combo_rational=combo_rational,
        combo_min_score=combo_min_score,
        combo_max_complexity=combo_max_complexity,
        component_transforms=names(combo_component_transforms, ("id",)),
        triple_candidates=triple_candidates,
        triple_max_shift_back=triple_max_shift_back,
        triple_max_checks=triple_max_checks,
        triple_max_time=triple_max_time,
        triple_max_combinations=triple_max_combinations,
        triple_rational=triple_rational,
        triple_allow_self_reference=combo_allow_self_reference,
        triple_min_score=triple_min_score,
        triple_max_complexity=triple_max_complexity,
        combo_unfiltered=combo_unfiltered,
        combo_expanded=combo_expanded,
        combo_expanded_max_time=combo_expanded_max_time,
        combo_expanded_anchors=combo_expanded_anchors,
        combo_expanded_pointwise=combo_expanded_pointwise,
        combo_expanded_pointwise_max_time=combo_expanded_pointwise_max_time,
        combined_limit=combined_limit,
        combined_family_quota=combined_family_quota,
        rerank=rerank,
        rerank_limit=rerank_limit,
        rerank_default_quota=rerank_default_quota,
        rerank_quotas=dict(rerank_quotas or {}),
        total_max_time=total_max_time,
        collect_timings=collect_timings,
        exclude_exact_from_derived=exclude_exact_from_derived,
        exclude_ids=normalized_exclude_ids,
    )
    result = run_analysis(
        query,
        db_path,
        options,
        transform_runner=run_transforms if transform_limit > 0 else None,
        on_event=on_event,
    )
    return result if as_dataclass else result.to_dict(show_formula=show_formula)
