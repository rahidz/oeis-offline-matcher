from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import time
from typing import Callable, Iterable, Sequence

from .candidates import get_candidate_bucket
from .combination_search import (
    merge_combination_families,
    resolve_component_transforms,
    search_convolution_two_sequence_combinations,
    search_mod_class_combinations,
    search_pointwise_two_sequence_combinations,
    search_pointwise_two_sequence_combinations_expanded,
    search_three_sequence_combinations,
    search_three_sequence_combinations_expanded,
    search_two_sequence_combinations,
    search_two_sequence_combinations_expanded,
)
from .explanation_ranking import rerank_explanations
from .matcher import match_exact, match_exact_db
from .models import AnalysisResult, CombinationMatch, Match, SequenceQuery
from .ranking import rank_candidates_for_query
from .similarity import growth_rate
from .storage import iter_sequences


@dataclass(frozen=True)
class AnalysisEvent:
    kind: str
    stage: str
    value: object | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class AnalysisOptions:
    preset: str | None = None
    exact_limit: int = 10
    show_terms: int | None = None
    derived_terms: int | None = None
    fallback_subsequence: bool = True
    fallback_full_scan: bool = False
    exact_max_time: float | None = None
    transform_limit: int = 10
    transform_max_time: float | None = None
    similarity_limit: int = 0
    similarity_max_time: float | None = None
    min_corr: float | None = None
    max_mse: float | None = None
    variance_band: float | None = None
    growth_band: float | None = None
    modclass_limit: int = 0
    modclass_moduli: tuple[int, ...] = (2, 3)
    modclass_max_time: float | None = None
    combo_limit: int = 0
    triple_limit: int = 0
    pointwise_limit: int = 0
    pointwise_ops: tuple[str, ...] = ()
    convolution_limit: int = 0
    convolution_ops: tuple[str, ...] = ()
    convolution_max_length: int = 32
    combo_coeffs: tuple[int, ...] = (-3, -2, -1, 1, 2, 3)
    combo_candidates: int = 40
    combo_candidate_max_time: float | None = None
    combo_discovery: bool = False
    combo_discovery_limit: int = 16
    combo_discovery_max_time: float | None = 2.0
    combo_discovery_tools: tuple[str, ...] = ("sympy",)
    combo_candidate_providers: tuple[str, ...] | None = None
    combo_wide_prefilter: bool = False
    combo_max_shift: int = 0
    combo_max_shift_back: int = 0
    combo_max_checks: int | None = 200_000
    combo_max_time: float | None = None
    combo_max_combinations: int | None = None
    combo_rational: bool = False
    combo_min_score: float | None = None
    combo_max_complexity: float | None = None
    component_transforms: tuple[str, ...] = ("id",)
    triple_candidates: int = 25
    triple_max_shift_back: int = 0
    triple_max_checks: int | None = 300_000
    triple_max_time: float | None = None
    triple_max_combinations: int | None = None
    triple_rational: bool = False
    triple_allow_self_reference: bool = False
    triple_min_score: float | None = None
    triple_max_complexity: float | None = None
    pointwise_max_time: float | None = None
    convolution_max_time: float | None = None
    combo_unfiltered: bool = False
    combo_expanded: bool = False
    combo_expanded_max_time: float | None = None
    combo_expanded_anchors: int = 400
    combo_expanded_pointwise: bool | None = None
    combo_expanded_pointwise_max_time: float | None = None
    combined_limit: int | None = None
    combined_family_quota: int = 1
    rerank: bool | None = None
    rerank_limit: int = 0
    rerank_default_quota: int = 1
    rerank_quotas: dict[str, int] = field(default_factory=dict)
    total_max_time: float | None = None
    collect_timings: bool = False
    exclude_exact_from_derived: bool | None = None


@dataclass
class _Budget:
    total: float | None
    now: Callable[[], float]
    start: float = field(init=False)

    def __post_init__(self) -> None:
        self.start = self.now()

    def remaining(self) -> float | None:
        if self.total is None:
            return None
        return max(0.0, float(self.total) - (self.now() - self.start))

    def cap(self, stage_cap: float | None) -> float | None:
        remaining = self.remaining()
        if remaining is None:
            return stage_cap
        if remaining <= 0:
            return 0.0
        return remaining if stage_cap is None else min(float(stage_cap), remaining)

    def available(self) -> bool:
        remaining = self.remaining()
        return remaining is None or remaining > 0

    def exhausted(self) -> bool:
        remaining = self.remaining()
        return remaining is not None and remaining <= 0


TransformRunner = Callable[[float | None, Callable[[Match], None] | None], list[Match]]
EventCallback = Callable[[AnalysisEvent], None]
CacheGet = Callable[[str], dict | None]
CachePut = Callable[[str, dict], None]


def attach_candidate_provenance(
    matches: list[CombinationMatch], provenance: dict[str, list[str]] | None
) -> list[CombinationMatch]:
    if not matches or not provenance:
        return matches
    out = []
    for match in matches:
        reasons = tuple(tuple(sorted(set(provenance.get(seq_id, ())))) for seq_id in match.ids)
        out.append(replace(match, candidate_provenance=reasons if any(reasons) else None))
    return out


def run_analysis(
    query: SequenceQuery,
    db_path: str | Path,
    options: AnalysisOptions,
    *,
    transform_runner: TransformRunner | None = None,
    on_event: EventCallback | None = None,
    cache_get: CacheGet | None = None,
    cache_put: CachePut | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
) -> AnalysisResult:
    db_path = Path(db_path)
    budget = _Budget(options.total_max_time, time_fn)
    timings: dict[str, float] = {}
    cache_get = cache_get or (lambda _stage: None)
    cache_put = cache_put or (lambda _stage, _payload: None)

    def emit(kind: str, stage: str, value=None, **details) -> None:
        if on_event is not None:
            on_event(AnalysisEvent(kind, stage, value, details))

    def stage_deadline(cap: float | None) -> float | None:
        cap = budget.cap(cap)
        if cap is None:
            return None
        return time_fn() + max(0.0, cap)

    def timed(stage: str, started: float) -> None:
        if options.collect_timings:
            timings[f"{stage}_ms"] = 1000 * (time_fn() - started)

    exclude_ids: set[str] = set()

    def filter_matches(matches: Iterable[Match]) -> list[Match]:
        return [m for m in matches if m.id not in exclude_ids]

    def filter_combos(matches: Iterable[CombinationMatch]) -> list[CombinationMatch]:
        return [m for m in matches if not any(seq_id in exclude_ids for seq_id in m.ids)]

    def emit_combo(stage: str, match: CombinationMatch) -> None:
        if not any(seq_id in exclude_ids for seq_id in match.ids):
            emit("match", stage, match)

    emit("stage_start", "exact")
    started = time_fn()
    cached = cache_get("exact")
    if cached is not None:
        exact_matches = list(cached.get("matches") or ())
        fallback_used = bool(cached.get("fallback_used"))
    else:
        deadline = stage_deadline(options.exact_max_time)
        exact_matches = match_exact_db(
            query,
            db_path,
            limit=options.exact_limit,
            snippet_len=options.show_terms,
            deadline_s=deadline,
            time_fn=time_fn,
        )
        fallback_used = False
        if (
            not exact_matches
            and not query.allow_subsequence
            and options.fallback_subsequence
            and (deadline is None or time_fn() < deadline)
        ):
            fallback_query = SequenceQuery(query.terms, query.min_match_length, True)
            exact_matches = match_exact_db(
                fallback_query,
                db_path,
                limit=options.exact_limit,
                snippet_len=options.show_terms,
                deadline_s=deadline,
                time_fn=time_fn,
            )
            if not exact_matches and options.fallback_full_scan and (deadline is None or time_fn() < deadline):
                exact_matches = match_exact(
                    fallback_query,
                    iter_sequences(db_path),
                    limit=options.exact_limit,
                    snippet_len=options.show_terms,
                )
            fallback_used = True
        cache_put("exact", {"matches": exact_matches, "fallback_used": fallback_used})
    timed("exact", started)
    emit("stage_end", "exact", exact_matches, cached=cached is not None)

    exclude = options.exclude_exact_from_derived
    if exclude is None:
        exclude = options.preset in {"deep", "max"}
    if exclude and exact_matches:
        exclude_ids = {m.id for m in exact_matches}

    combo_requested = bool(
        options.modclass_limit
        or options.combo_limit
        or options.triple_limit
        or (options.pointwise_limit and options.pointwise_ops)
        or (options.convolution_limit and options.convolution_ops)
    )
    latency_first = options.preset in {"deep", "max"}
    transform_probe_used = False
    transform_probe_cap: float | None = None
    transform_refined = False
    defer_transform_refine = False

    emit("stage_start", "transform")
    started = time_fn()
    cached = cache_get("transform")
    if cached is not None:
        transform_matches = filter_matches(cached.get("matches") or ())
    elif options.transform_limit > 0 and budget.available() and transform_runner is not None:
        transform_cap = budget.cap(options.transform_max_time)
        if transform_cap is not None and transform_cap <= 0:
            transform_matches = []
        else:
            effective_cap = transform_cap
            if latency_first and combo_requested and (transform_cap is None or transform_cap > 5.0):
                effective_cap = 5.0
                defer_transform_refine = True
                transform_probe_used = True
                transform_probe_cap = 5.0

            def on_transform(match: Match) -> None:
                if match.id not in exclude_ids:
                    emit("match", "transform", match)

            transform_matches = filter_matches(transform_runner(effective_cap, on_transform))
            if not defer_transform_refine:
                cache_put("transform", {"matches": transform_matches})
    else:
        transform_matches = []
    timed("transform", started)
    emit("stage_end", "transform", transform_matches, cached=cached is not None)

    emit("stage_start", "similarity")
    started = time_fn()
    cached = cache_get("similarity")
    if cached is not None:
        similarity_rows = [dict(row) for row in cached.get("matches") or ()]
    elif options.similarity_limit > 0 and budget.available():
        deadline = stage_deadline(options.similarity_max_time)
        candidates = rank_candidates_for_query(
            query,
            db_path,
            top_k=options.similarity_limit,
            min_corr=options.min_corr,
            max_mse=options.max_mse,
            variance_band=options.variance_band,
            growth_band=options.growth_band,
            deadline_s=deadline,
            time_fn=time_fn,
        ) if deadline is None or time_fn() < deadline else []
        similarity_rows = [
            {
                "id": candidate.record.id,
                "name": candidate.record.name,
                "corr": candidate.corr,
                "mse": candidate.mse,
                "scale": candidate.scale,
                "offset": candidate.offset,
            }
            for candidate in candidates
            if candidate.record.id not in exclude_ids
        ]
        cache_put("similarity", {"matches": similarity_rows})
    else:
        similarity_rows = []
    similarity_rows = [row for row in similarity_rows if row.get("id") not in exclude_ids]
    timed("similarity", started)
    emit("stage_end", "similarity", similarity_rows, cached=cached is not None)

    modclass_matches: list[CombinationMatch] = []
    if options.modclass_limit > 0:
        emit("stage_start", "modclass")
        started = time_fn()
        cached = cache_get("modclass")
        if cached is not None:
            modclass_matches = filter_combos(cached.get("matches") or ())
        elif budget.available():
            cap = budget.cap(options.modclass_max_time)
            if cap is None or cap > 0:
                modclass_matches = filter_combos(
                    search_mod_class_combinations(
                        query,
                        db_path,
                        moduli=options.modclass_moduli or (2, 3),
                        limit=options.modclass_limit,
                        max_shift=options.combo_max_shift,
                        max_time_s=cap,
                        snippet_len=options.derived_terms,
                        min_score=options.combo_min_score,
                        max_complexity=options.combo_max_complexity,
                        on_match=lambda match: emit_combo("modclass", match),
                    )
                )
                cache_put("modclass", {"matches": modclass_matches})
        timed("modclass", started)
        emit("stage_end", "modclass", modclass_matches, cached=cached is not None)

    stage_limits = {
        "combination": options.combo_limit,
        "triple": options.triple_limit,
        "pointwise": options.pointwise_limit if options.pointwise_ops else 0,
        "convolution": options.convolution_limit if options.convolution_ops else 0,
    }
    cached_stages = {stage: cache_get(stage) if limit > 0 else None for stage, limit in stage_limits.items()}
    combo_matches = filter_combos((cached_stages["combination"] or {}).get("matches") or ())
    triple_matches = filter_combos((cached_stages["triple"] or {}).get("matches") or ())
    pointwise_matches = filter_combos((cached_stages["pointwise"] or {}).get("matches") or ())
    convolution_matches = filter_combos((cached_stages["convolution"] or {}).get("matches") or ())
    needed = {stage for stage, limit in stage_limits.items() if limit > 0 and cached_stages[stage] is None}
    bucket_diag: dict[str, object] | None = None
    provenance: dict[str, list[str]] | None = None

    if needed and budget.available():
        emit("stage_start", "candidates")
        cap = max(options.combo_candidates, options.triple_candidates if options.triple_limit else 0, 1)
        bucket_deadline = stage_deadline(options.combo_candidate_max_time)
        bucket = get_candidate_bucket(
            query,
            db_path,
            exact_limit=cap,
            similar_limit=cap,
            max_records=cap,
            fill_unfiltered=True,
            skip_prefix_filter=options.combo_unfiltered,
            variance_band=options.variance_band,
            growth_band=options.growth_band,
            deadline_s=bucket_deadline,
            time_fn=time_fn,
            enable_discovery=options.combo_discovery,
            discovery_limit=options.combo_discovery_limit,
            discovery_max_time_s=options.combo_discovery_max_time,
            discovery_tools=options.combo_discovery_tools,
            candidate_providers=options.combo_candidate_providers,
            widen_prefilter=options.combo_wide_prefilter,
        )
        if exclude_ids:
            records = [record for record in bucket.records if record.id not in exclude_ids]
            keep = {record.id for record in records}
            bucket = replace(
                bucket,
                exact_ids=[seq_id for seq_id in bucket.exact_ids if seq_id in keep],
                transform_ids=[seq_id for seq_id in bucket.transform_ids if seq_id in keep],
                similar_ids=[seq_id for seq_id in bucket.similar_ids if seq_id in keep],
                discovery_ids=[seq_id for seq_id in bucket.discovery_ids if seq_id in keep],
                records=records,
                provenance={seq_id: reasons for seq_id, reasons in bucket.provenance.items() if seq_id in keep},
            )
        provenance = bucket.provenance
        bucket_diag = {
            "size": len(bucket.records),
            "exact": len(bucket.exact_ids),
            "similar": len(bucket.similar_ids),
            "discovery": len(bucket.discovery_ids),
            "provenance_counts": {
                reason: sum(reason in reasons for reasons in bucket.provenance.values())
                for reason in sorted({reason for reasons in bucket.provenance.values() for reason in reasons})
            },
            **({"discovery_diagnostics": bucket.discovery_diagnostics} if bucket.discovery_diagnostics else {}),
            **({"provider_diagnostics": bucket.provider_diagnostics} if bucket.provider_diagnostics else {}),
        }
        emit("stage_end", "candidates", bucket.records, diagnostics=bucket_diag)
        component_transforms = resolve_component_transforms(options.component_transforms)
        expanded_pair_pending = False

        if "combination" in needed:
            emit("stage_start", "combination")
            started = time_fn()
            cap_time = budget.cap(options.combo_max_time)
            if cap_time is None or cap_time > 0:
                combo_matches = filter_combos(
                    search_two_sequence_combinations(
                        query,
                        bucket.records,
                        coeffs=options.combo_coeffs,
                        max_shift=options.combo_max_shift,
                        max_shift_back=options.combo_max_shift_back,
                        limit=options.combo_limit,
                        max_candidates=options.combo_candidates,
                        max_checks=options.combo_max_checks,
                        max_time_s=cap_time,
                        max_combinations=options.combo_max_combinations,
                        component_transforms=component_transforms,
                        snippet_len=options.derived_terms,
                        use_rational=options.combo_rational,
                        min_score=options.combo_min_score,
                        max_complexity=options.combo_max_complexity,
                        on_match=lambda match: emit_combo("combination", match),
                    )
                )
                combo_matches = attach_candidate_provenance(combo_matches, provenance)
                expanded_pair_pending = options.combo_expanded and not combo_matches and len(query.terms) >= 5
                cache_put("combination", {"matches": combo_matches})
            timed("combination", started)
            emit("stage_end", "combination", combo_matches, expanded_pending=expanded_pair_pending)

        if "pointwise" in needed:
            emit("stage_start", "pointwise")
            started = time_fn()
            cap_time = budget.cap(options.pointwise_max_time if options.pointwise_max_time is not None else options.combo_max_time)
            if cap_time is None or cap_time > 0:
                pointwise_matches = filter_combos(
                    search_pointwise_two_sequence_combinations(
                        query,
                        bucket.records,
                        ops=options.pointwise_ops,
                        max_shift=options.combo_max_shift,
                        max_shift_back=options.combo_max_shift_back,
                        limit=options.pointwise_limit,
                        max_candidates=options.combo_candidates,
                        max_checks=options.combo_max_checks,
                        max_time_s=cap_time,
                        component_transforms=component_transforms,
                        snippet_len=options.derived_terms,
                        min_score=options.combo_min_score,
                        max_complexity=options.combo_max_complexity,
                        on_match=lambda match: emit_combo("pointwise", match),
                    )
                )
                pointwise_matches = attach_candidate_provenance(pointwise_matches, provenance)
                expanded_pointwise = (
                    options.combo_expanded
                    if options.combo_expanded_pointwise is None
                    else options.combo_expanded_pointwise
                )
                if expanded_pointwise and "mul" in options.pointwise_ops and not pointwise_matches and len(query.terms) >= 5 and budget.available():
                    expanded_cap = options.combo_expanded_pointwise_max_time
                    if expanded_cap is None:
                        expanded_cap = options.combo_expanded_max_time
                    expanded_cap = budget.cap(expanded_cap)
                    if expanded_cap is None or expanded_cap > 0:
                        expanded_started = time_fn()
                        emit("message", "pointwise", message="expanded")
                        pointwise_matches = filter_combos(
                            search_pointwise_two_sequence_combinations_expanded(
                                query,
                                db_path,
                                ops=("mul",),
                                max_shift=options.combo_max_shift,
                                limit=options.pointwise_limit,
                                max_time_s=expanded_cap,
                                snippet_len=options.derived_terms,
                                min_score=options.combo_min_score,
                                max_complexity=options.combo_max_complexity,
                                on_match=lambda match: emit_combo("pointwise", match),
                            )
                        )
                        pointwise_matches = attach_candidate_provenance(pointwise_matches, provenance)
                        timed("expanded_pointwise", expanded_started)
                cache_put("pointwise", {"matches": pointwise_matches})
            timed("pointwise", started)
            emit("stage_end", "pointwise", pointwise_matches)

        if "convolution" in needed:
            emit("stage_start", "convolution")
            started = time_fn()
            cap_time = budget.cap(options.convolution_max_time if options.convolution_max_time is not None else options.combo_max_time)
            if cap_time is None or cap_time > 0:
                convolution_matches = filter_combos(
                    search_convolution_two_sequence_combinations(
                        query,
                        bucket.records,
                        ops=options.convolution_ops,
                        max_length=options.convolution_max_length,
                        limit=options.convolution_limit,
                        max_candidates=options.combo_candidates,
                        max_checks=options.combo_max_checks,
                        max_time_s=cap_time,
                        component_transforms=component_transforms,
                        snippet_len=options.derived_terms,
                        min_score=options.combo_min_score,
                        max_complexity=options.combo_max_complexity,
                        on_match=lambda match: emit_combo("convolution", match),
                    )
                )
                convolution_matches = attach_candidate_provenance(convolution_matches, provenance)
                cache_put("convolution", {"matches": convolution_matches})
            timed("convolution", started)
            emit("stage_end", "convolution", convolution_matches)

        if "triple" in needed:
            emit("stage_start", "triple")
            started = time_fn()
            cap_time = budget.cap(options.triple_max_time)
            if cap_time is None or cap_time > 0:
                triple_matches = filter_combos(
                    search_three_sequence_combinations(
                        query,
                        bucket.records,
                        coeffs=options.combo_coeffs,
                        max_shift=options.combo_max_shift,
                        max_shift_back=options.triple_max_shift_back,
                        limit=options.triple_limit,
                        max_candidates=options.triple_candidates,
                        max_checks=options.triple_max_checks,
                        max_time_s=cap_time,
                        max_combinations=options.triple_max_combinations,
                        component_transforms=component_transforms,
                        snippet_len=options.derived_terms,
                        use_rational=options.triple_rational,
                        allow_self_reference=options.triple_allow_self_reference,
                        min_score=options.triple_min_score,
                        max_complexity=options.triple_max_complexity,
                        on_match=lambda match: emit_combo("triple", match),
                    )
                )
                triple_matches = attach_candidate_provenance(triple_matches, provenance)
                if options.combo_expanded and not triple_matches and len(query.terms) >= 5 and budget.available():
                    expanded_cap = budget.cap(options.combo_expanded_max_time)
                    if expanded_cap is None or expanded_cap > 0:
                        emit("message", "triple", message="expanded")
                        triple_matches = filter_combos(
                            search_three_sequence_combinations_expanded(
                                query,
                                db_path,
                                coeffs=options.combo_coeffs,
                                limit=options.triple_limit,
                                max_anchors=options.combo_expanded_anchors,
                                max_time_s=expanded_cap,
                                snippet_len=options.derived_terms,
                                min_score=options.triple_min_score,
                                max_complexity=options.triple_max_complexity,
                                on_match=lambda match: emit_combo("triple", match),
                            )
                        )
                        triple_matches = attach_candidate_provenance(triple_matches, provenance)
                cache_put("triple", {"matches": triple_matches})
            timed("triple", started)
            emit("stage_end", "triple", triple_matches)

        if expanded_pair_pending and not combo_matches and budget.available():
            emit("stage_start", "expanded_pair")
            started = time_fn()
            expanded_cap = budget.cap(options.combo_expanded_max_time)
            if expanded_cap is None or expanded_cap > 0:
                combo_matches = filter_combos(
                    search_two_sequence_combinations_expanded(
                        query,
                        db_path,
                        coeffs=options.combo_coeffs,
                        limit=options.combo_limit,
                        max_shift=options.combo_max_shift,
                        max_time_s=expanded_cap,
                        snippet_len=options.derived_terms,
                        min_score=options.combo_min_score,
                        max_complexity=options.combo_max_complexity,
                        on_match=lambda match: emit_combo("expanded_pair", match),
                    )
                )
                combo_matches = attach_candidate_provenance(combo_matches, provenance)
                cache_put("combination", {"matches": combo_matches})
            timed("expanded_pair", started)
            emit("stage_end", "expanded_pair", combo_matches)

    for stage, matches in (
        ("combination", combo_matches),
        ("triple", triple_matches),
        ("pointwise", pointwise_matches),
        ("convolution", convolution_matches),
    ):
        if cached_stages[stage] is not None:
            emit("stage_start", stage)
            emit("stage_end", stage, matches, cached=True)

    if provenance:
        combo_matches = attach_candidate_provenance(combo_matches, provenance)
        triple_matches = attach_candidate_provenance(triple_matches, provenance)
        pointwise_matches = attach_candidate_provenance(pointwise_matches, provenance)
        convolution_matches = attach_candidate_provenance(convolution_matches, provenance)
        modclass_matches = attach_candidate_provenance(modclass_matches, provenance)

    if defer_transform_refine:
        if options.transform_limit > 0 and budget.available() and transform_runner is not None:
            cap_time = budget.cap(options.transform_max_time)
            if cap_time is None or cap_time > 0:
                emit("stage_start", "transform_refine")
                started = time_fn()
                transform_matches = filter_matches(transform_runner(cap_time, None))
                transform_refined = True
                cache_put("transform", {"matches": transform_matches})
                timed("transform_refine", started)
                if options.collect_timings:
                    timings["transform_ms"] = timings.get("transform_ms", 0.0) + timings["transform_refine_ms"]
                emit("stage_end", "transform_refine", transform_matches)
        else:
            cache_put("transform", {"matches": transform_matches})

    families = {
        "linear_pair": combo_matches,
        "linear_triple": triple_matches,
        "modclass": modclass_matches,
        "pointwise": pointwise_matches,
        "convolution": convolution_matches,
    }
    auto_limit = max(
        options.combo_limit,
        options.triple_limit,
        options.modclass_limit,
        options.pointwise_limit,
        options.convolution_limit,
        0,
    )
    combined_limit = options.combined_limit if options.combined_limit is not None else (auto_limit or None)
    combined = merge_combination_families(
        families,
        limit=combined_limit,
        per_family_quota=max(1, options.combined_family_quota),
    )
    rerank_enabled = options.rerank
    if rerank_enabled is None:
        rerank_enabled = options.preset in {"deep", "max"}
        rerank_mode = "auto_preset_deepmax" if rerank_enabled else "off_default"
    else:
        rerank_mode = "explicit_on" if rerank_enabled else "explicit_off"
    ranking_limit = options.rerank_limit or max(options.transform_limit, auto_limit, 0) or None
    ranked, ranking_info = rerank_explanations(
        transform_matches=transform_matches,
        family_matches=families,
        limit=ranking_limit,
        default_quota=max(0, options.rerank_default_quota) if rerank_enabled else 0,
        quotas=options.rerank_quotas if rerank_enabled else {},
        diversity=bool(rerank_enabled),
    )
    emit("stage_end", "ranking", ranked)

    if options.collect_timings:
        timings["total_ms"] = 1000 * (time_fn() - budget.start)
    numeric_terms = [term for term in query.terms if term is not None]

    def variance(values: Sequence[int]) -> float | None:
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values) / len(values)

    diagnostics = {
        "query_length": len(query.terms),
        "exact_limit": options.exact_limit,
        "transform_limit": options.transform_limit,
        "similarity_limit": options.similarity_limit,
        "combination_limit": options.combo_limit,
        "combo_candidate_cap": options.combo_candidates,
        "combo_max_checks": options.combo_max_checks,
        "triple_limit": options.triple_limit,
        "triple_candidate_cap": options.triple_candidates,
        "triple_max_checks": options.triple_max_checks,
        "pointwise_limit": options.pointwise_limit,
        "convolution_limit": options.convolution_limit,
        "variance_band": options.variance_band,
        "growth_band": options.growth_band,
        "query_var": variance(numeric_terms),
        "query_diff_var": variance([b - a for a, b in zip(numeric_terms, numeric_terms[1:])]),
        "query_growth": growth_rate(numeric_terms),
        "combined_combinations_count": len(combined),
        "combined_explanations": [
            {
                "family": family,
                "expression": match.expression,
                "score": match.score,
                "length": match.length,
                "ids": list(match.ids),
                "coeffs": [str(coeff) for coeff in match.coeffs],
                "shifts": list(match.shifts),
                **(
                    {"candidate_provenance": [list(reasons) for reasons in match.candidate_provenance]}
                    if match.candidate_provenance
                    else {}
                ),
            }
            for family, match in combined
        ],
        "ranking": {
            "enabled": bool(rerank_enabled),
            "mode": rerank_mode,
            "configured_limit": options.rerank_limit,
            "default_quota": max(0, options.rerank_default_quota),
            "quota_overrides": options.rerank_quotas,
            **ranking_info,
        },
        "scheduling": {
            "mode": "latency_first" if latency_first else "default",
            "combo_stage_requested": combo_requested,
            "transform_probe_used": transform_probe_used,
            "transform_refined": transform_refined,
            **({"transform_probe_cap_s": transform_probe_cap} if transform_probe_cap is not None else {}),
        },
        **({"candidate_bucket": bucket_diag} if bucket_diag is not None else {}),
        **({"subsequence_fallback": True} if fallback_used else {}),
        **({"time_budget_exhausted": True} if budget.exhausted() else {}),
        **({"timings_ms": timings} if options.collect_timings else {}),
    }
    return AnalysisResult(
        query=query.terms,
        exact_matches=exact_matches,
        transform_matches=transform_matches,
        similarity=similarity_rows,
        combinations=combo_matches,
        triple_combinations=triple_matches,
        modclass_combinations=modclass_matches,
        pointwise_combinations=pointwise_matches,
        convolution_combinations=convolution_matches,
        combined_combinations=combined,
        ranked_explanations=ranked,
        diagnostics=diagnostics,
    )
