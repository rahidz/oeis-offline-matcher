from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
import time

from .config import load_config
from .matcher import match_exact, candidate_sequences
from .models import Match, SequenceQuery, AnalysisResult
from .query import parse_query
from .ranking import rank_candidates_for_query
from .transform_search import search_transform_matches
from .transforms import default_transforms
from .candidates import get_candidate_bucket
from .combination_search import search_two_sequence_combinations, search_three_sequence_combinations, resolve_component_transforms


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
    seq_iter = candidate_sequences(db_path, query)
    matches = match_exact(query, seq_iter, limit=limit, snippet_len=show_terms)
    if matches or allow_subsequence or not fallback_subsequence:
        return matches
    # fallback to subsequence search using invariant-filtered candidates first, optionally full scan
    fallback_query = SequenceQuery(
        terms=list(terms),
        min_match_length=min_match_length,
        allow_subsequence=True,
    )
    seq_iter = candidate_sequences(db_path, fallback_query)
    fmatches = match_exact(fallback_query, seq_iter, limit=limit, snippet_len=show_terms)
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
    scale_values: Iterable[int] = (-3, -2, -1, 2, 3),
    beta_values: Iterable[int] = (),
    shift_values: Iterable[int] = (1, 2),
    decimate_params: Iterable[tuple[int, int]] = (),
    allow_diff: bool = True,
    allow_partial_sum: bool = True,
    allow_abs: bool = True,
    allow_gcd_norm: bool = True,
    full_scan: bool = False,
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
        allow_partial_sum=allow_partial_sum,
        allow_abs=allow_abs,
        allow_gcd_norm=allow_gcd_norm,
        decimate_params=decimate_params,
    )
    return search_transform_matches(
        query,
        db_path,
        max_depth=max_depth,
        transforms=transforms,
        limit=limit,
        snippet_len=show_terms,
        full_scan=full_scan,
    )


def search_combinations(
    terms: Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    coeffs: Iterable[int] = (-3, -2, -1, 1, 2, 3),
    max_shift: int = 0,
    limit: int = 20,
    candidate_cap: int = 40,
    max_checks: int | None = 200_000,
    max_time: float | None = None,
    max_combinations: int | None = None,
    component_transforms: Iterable[str] | None = None,
    combo_unfiltered: bool = False,
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
    )
    return search_two_sequence_combinations(
        query,
        bucket.records,
        coeffs=tuple(coeffs),
        max_shift=max_shift,
        limit=limit,
        max_candidates=candidate_cap,
        max_checks=max_checks,
        max_time_s=max_time,
        max_combinations=max_combinations,
        component_transforms=resolve_component_transforms(list(component_transforms) if component_transforms is not None else None),
    )


def search_three_combinations(
    terms: Sequence[int],
    *,
    db_path: str | Path | None = None,
    min_match_length: int = 3,
    coeffs: Iterable[int] = (-2, -1, 1, 2),
    max_shift: int = 0,
    limit: int = 10,
    candidate_cap: int = 25,
    max_checks: int | None = 300_000,
    max_time: float | None = None,
    max_combinations: int | None = None,
    component_transforms: Iterable[str] | None = None,
    combo_unfiltered: bool = False,
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
    )
    return search_three_sequence_combinations(
        query,
        bucket.records,
        coeffs=tuple(coeffs),
        max_shift=max_shift,
        limit=limit,
        max_candidates=candidate_cap,
        max_checks=max_checks,
        max_time_s=max_time,
        max_combinations=max_combinations,
        component_transforms=resolve_component_transforms(list(component_transforms) if component_transforms is not None else None),
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
    similarity: int = 0,
    combos: int = 0,
    triples: int = 0,
    combo_coeffs: Iterable[int] = (-3, -2, -1, 1, 2, 3),
    combo_max_shift: int = 0,
    combo_candidates: int = 40,
    combo_max_checks: int | None = 200_000,
    combo_max_time: float | None = None,
    combo_max_combinations: int | None = None,
    triple_candidates: int = 25,
    triple_max_checks: int | None = 300_000,
    triple_max_time: float | None = None,
    triple_max_combinations: int | None = None,
    combo_component_transforms: Iterable[str] | None = None,
    fallback_subsequence: bool = True,
    fallback_full_scan: bool = False,
    show_terms: int | None = None,
    as_dataclass: bool = False,
    collect_timings: bool = False,
    full_transform_scan: bool = False,
    combo_unfiltered: bool = False,
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

    # Exact
    exact_iter = candidate_sequences(db_path, query)
    exact = match_exact(query, exact_iter, limit=exact_limit, snippet_len=show_terms)
    fallback_used = False
    if not exact and not query.allow_subsequence and fallback_subsequence:
        fb_query = SequenceQuery(terms=query.terms, min_match_length=min_match_length, allow_subsequence=True)
        exact_iter = candidate_sequences(db_path, fb_query)
        exact = match_exact(fb_query, exact_iter, limit=exact_limit, snippet_len=show_terms)
        if not exact and fallback_full_scan:
            from .storage import iter_sequences

            exact = match_exact(fb_query, iter_sequences(db_path), limit=exact_limit, snippet_len=show_terms)
        fallback_used = bool(exact)
    if collect_timings:
        timings["exact_ms"] = 1000 * (time.perf_counter() - t0)
    t1 = time.perf_counter()

    # Transforms
    t_args = transform_args or {}
    t_matches = search_transforms(
        query.terms,
        db_path=db_path,
        min_match_length=min_match_length,
        allow_subsequence=allow_subsequence,
        max_depth=transform_depth,
        limit=transform_limit,
        show_terms=show_terms,
        full_scan=full_transform_scan,
        **t_args,
    )
    if collect_timings:
        timings["transform_ms"] = 1000 * (time.perf_counter() - t1)
    t2 = time.perf_counter()

    sim_matches = rank_candidates_for_query(query, db_path, top_k=similarity) if similarity else []
    if collect_timings:
        timings["similarity_ms"] = 1000 * (time.perf_counter() - t2)

    combo_matches = []
    triple_matches = []
    if combos or triples:
        combo_coeffs_seq = combo_coeffs
        if combos:
            combo_start = time.perf_counter()
            combo_matches = search_combinations(
                query.terms,
                db_path=db_path,
                min_match_length=min_match_length,
                coeffs=combo_coeffs_seq,
                max_shift=combo_max_shift,
                limit=combos,
                candidate_cap=combo_candidates,
                max_checks=combo_max_checks,
                max_time=combo_max_time,
                max_combinations=combo_max_combinations,
                component_transforms=combo_component_transforms,
                combo_unfiltered=combo_unfiltered,
            )
            combo_end = time.perf_counter()
        else:
            combo_start = combo_end = None
        if triples:
            triple_start = time.perf_counter()
            triple_matches = search_three_combinations(
                query.terms,
                db_path=db_path,
                min_match_length=min_match_length,
                coeffs=combo_coeffs_seq,
                max_shift=combo_max_shift,
                limit=triples,
                candidate_cap=triple_candidates,
                max_checks=triple_max_checks,
                max_time=triple_max_time,
                max_combinations=triple_max_combinations,
                component_transforms=combo_component_transforms,
                combo_unfiltered=combo_unfiltered,
            )
            triple_end = time.perf_counter()
        else:
            triple_start = triple_end = None
        if collect_timings:
            if combo_start is not None and combo_end is not None:
                timings["combination_ms"] = 1000 * (combo_end - combo_start)
            if triple_start is not None and triple_end is not None:
                timings["triple_ms"] = 1000 * (triple_end - triple_start)

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
        diagnostics=diag,
    )

    return result if as_dataclass else result.to_dict()
