from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Callable, Iterable, List

from .discovery import discover_candidate_ids
from .matcher import candidate_sequences
from .models import SequenceQuery, SequenceRecord
from .ranking import rank_candidates_for_query


@dataclass(frozen=True)
class CandidateBucket:
    exact_ids: List[str]
    transform_ids: List[str]
    similar_ids: List[str]
    records: List[SequenceRecord]
    discovery_ids: List[str] = field(default_factory=list)
    provenance: dict[str, list[str]] = field(default_factory=dict)
    discovery_diagnostics: dict[str, object] = field(default_factory=dict)
    provider_diagnostics: dict[str, object] = field(default_factory=dict)


SUPPORTED_CANDIDATE_PROVIDERS: tuple[str, ...] = (
    "seed",
    "index_join",
    "exact",
    "similarity",
    "expanded",
    "discovery",
)

_PROVIDER_ALIASES: dict[str, str] = {
    "seed": "seed",
    "index": "index_join",
    "index_join": "index_join",
    "index-join": "index_join",
    "prefix": "index_join",
    "exact": "exact",
    "similar": "similarity",
    "similarity": "similarity",
    "expanded": "expanded",
    "fill": "expanded",
    "full_scan": "expanded",
    "fullscan": "expanded",
    "discovery": "discovery",
}


def _normalize_provider_name(name: str) -> str | None:
    return _PROVIDER_ALIASES.get(str(name).strip().lower())


def _dedup_keep_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for val in values:
        if val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def _resolve_candidate_providers(
    provider_names: tuple[str, ...] | None,
    *,
    skip_prefix_filter: bool,
    fill_unfiltered: bool,
    enable_discovery: bool,
    widen_prefilter: bool,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if provider_names:
        requested = tuple(str(p).strip() for p in provider_names if str(p).strip())
    else:
        defaults: list[str] = ["seed", "exact", "similarity"] if skip_prefix_filter else ["seed", "index_join", "similarity"]
        if widen_prefilter and "exact" not in defaults:
            defaults.append("exact")
        if fill_unfiltered:
            defaults.append("expanded")
        if enable_discovery:
            defaults.append("discovery")
        requested = tuple(defaults)
    enabled: list[str] = []
    unknown: list[str] = []
    for name in requested:
        norm = _normalize_provider_name(name)
        if norm is None:
            unknown.append(name)
            continue
        enabled.append(norm)
    enabled = _dedup_keep_order(enabled)
    return tuple(requested), tuple(enabled), tuple(_dedup_keep_order(unknown))


def _widen_band(value: float | None, *, default: float, factor: float) -> float:
    if value is None:
        return default
    try:
        return max(default, float(value) * factor)
    except (TypeError, ValueError):
        return default


def get_candidate_bucket(
    query: SequenceQuery,
    db_path: Path,
    *,
    exact_limit: int = 50,
    similar_limit: int = 100,
    max_records: int | None = None,
    fill_unfiltered: bool = False,
    skip_prefix_filter: bool = False,
    variance_band: float | None = None,
    growth_band: float | None = None,
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    enable_discovery: bool = False,
    discovery_limit: int = 16,
    discovery_max_time_s: float | None = None,
    discovery_tools: tuple[str, ...] = ("sympy",),
    candidate_providers: tuple[str, ...] | None = None,
    widen_prefilter: bool = False,
) -> CandidateBucket:
    """
    Collect a union of ids from direct candidate filter and similarity ranking,
    capped to keep combination search manageable.
    """
    provider_requested, provider_order, provider_unknown = _resolve_candidate_providers(
        candidate_providers,
        skip_prefix_filter=skip_prefix_filter,
        fill_unfiltered=fill_unfiltered,
        enable_discovery=enable_discovery,
        widen_prefilter=widen_prefilter,
    )
    provider_diag = {
        "requested": list(provider_requested),
        "enabled": list(provider_order),
        "unknown": list(provider_unknown),
        "widen_prefilter": bool(widen_prefilter),
    }
    if deadline_s is not None and time_fn() >= deadline_s:
        return CandidateBucket(
            exact_ids=[],
            transform_ids=[],
            similar_ids=[],
            records=[],
            provider_diagnostics=provider_diag,
        )
    qlen = len(query.terms)
    variance_for_wide = _widen_band(variance_band, default=150.0, factor=3.0) if widen_prefilter else variance_band
    growth_for_wide = _widen_band(growth_band, default=8.0, factor=2.0) if widen_prefilter else growth_band
    # Seed a few canonical "building block" sequences into combo/similarity
    # candidate pools. This dramatically improves combo discovery for cases
    # where the components do not resemble the target query (e.g., n^2+n,
    # n*(n+1), ones*ones, etc.), without requiring the user to know A-numbers.
    #
    # Note: these are deliberately few and fetched by id so they're stable even
    # when many unrelated sequences share the same short prefix.
    # Note on ordering:
    # Candidate-bucket order impacts which pairs/triples get tried first in
    # time-capped combo searches. Start with "information-rich" seeds (Fibonacci,
    # n, squares) and put degenerate constants (0/1) later to avoid burning
    # budget on brute-force degenerate-column cases.
    seed_ids: list[str] = [
        "A000045",  # Fibonacci numbers (common building block in identities)
        "A001477",  # nonnegative integers
        "A000027",  # positive integers
        "A000290",  # squares
        "A000012",  # all ones
        "A000004",  # all zeros
    ]
    seed_records: list[SequenceRecord] = []
    if "seed" in provider_order:
        from .storage import get_sequence_by_id

        for sid in seed_ids:
            rec = get_sequence_by_id(db_path, sid)
            if rec:
                seed_records.append(rec)

    def _collect_records(
        *,
        use_prefix_index: bool,
        loosen_nonzero: bool,
        cap: int | None,
        limit: int | None = None,
    ) -> list[SequenceRecord]:
        records: list[SequenceRecord] = []
        for rec in candidate_sequences(
            db_path,
            query,
            use_prefix_index=use_prefix_index,
            loosen_nonzero=loosen_nonzero,
            variance_band=variance_for_wide,
            growth_band=growth_for_wide,
            limit=limit,
        ):
            if deadline_s is not None and time_fn() >= deadline_s:
                break
            records.append(rec)
            if cap is not None and len(records) >= cap:
                break
        return records

    index_records: list[SequenceRecord] = []
    exact_records: list[SequenceRecord] = []
    if "index_join" in provider_order and not skip_prefix_filter:
        index_records = _collect_records(
            use_prefix_index=True,
            loosen_nonzero=widen_prefilter,
            cap=exact_limit,
        )
    if "exact" in provider_order:
        exact_cap = max_records if (skip_prefix_filter and max_records is not None) else exact_limit
        exact_records = _collect_records(
            use_prefix_index=False,
            loosen_nonzero=(skip_prefix_filter or widen_prefilter),
            cap=exact_cap,
            limit=exact_cap if (skip_prefix_filter and max_records is not None) else None,
        )
    base_records: list[SequenceRecord] = [*index_records, *exact_records]
    exact_ids = _dedup_keep_order(r.id for r in base_records)

    # Similarity-ranked set
    sim: list = []
    sim_ids: list[str] = []
    if "similarity" in provider_order:
        sim_top = max_records if (skip_prefix_filter and max_records is not None) else similar_limit
        sim_candidate_limit: int | None = None
        if max_records is not None and (skip_prefix_filter or widen_prefilter):
            mult = 100 if widen_prefilter else 50
            base = 10000 if widen_prefilter else 5000
            sim_candidate_limit = max(base, int(max_records) * mult)
        sim = rank_candidates_for_query(
            query,
            db_path,
            top_k=sim_top,
            use_prefix_index=not (skip_prefix_filter or widen_prefilter),
            loosen_nonzero=(skip_prefix_filter or widen_prefilter),
            min_corr=None,
            max_mse=None,
            variance_band=variance_for_wide,
            growth_band=growth_for_wide,
            deadline_s=deadline_s,
            time_fn=time_fn,
            candidate_limit=sim_candidate_limit,
        )
        sim_ids = [c.record.id for c in sim]

    # Transform ids will be added by transform search; placeholder empty for now
    transform_ids: List[str] = []
    discovery_ids: List[str] = []
    discovery_diag: dict[str, object] = {}

    # Union records by id
    id_set = {}
    provenance: dict[str, list[str]] = {}

    def _mark(sid: str, reason: str) -> None:
        reasons = provenance.setdefault(sid, [])
        if reason not in reasons:
            reasons.append(reason)

    for r in seed_records:
        id_set[r.id] = r
        _mark(r.id, "seed")
    for r in index_records:
        if r.id not in id_set:
            id_set[r.id] = r
        _mark(r.id, "index_join")
    for r in exact_records:
        if r.id not in id_set:
            id_set[r.id] = r
        _mark(r.id, "exact")
    for c in sim:
        if c.record.id not in id_set:
            id_set[c.record.id] = c.record
        _mark(c.record.id, "similarity")

    if "discovery" in provider_order and enable_discovery and (deadline_s is None or time_fn() < deadline_s):
        if discovery_max_time_s is not None:
            try:
                disc_cap = float(discovery_max_time_s)
            except (TypeError, ValueError):
                disc_cap = None
        else:
            disc_cap = None
        disc_deadline = deadline_s
        if disc_cap is not None:
            if disc_cap <= 0:
                disc_deadline = time_fn()
            else:
                local = time_fn() + disc_cap
                disc_deadline = min(local, disc_deadline) if disc_deadline is not None else local
        discovery = discover_candidate_ids(
            [int(t) for t in query.terms if t is not None],
            db_path,
            limit=max(0, int(discovery_limit)),
            tools=tuple(discovery_tools),
            deadline_s=disc_deadline,
            time_fn=time_fn,
        )
        discovery_ids = list(discovery.ids)
        discovery_diag = discovery.diagnostics
        from .storage import get_sequence_by_id

        for sid in discovery_ids:
            rec = get_sequence_by_id(db_path, sid)
            if rec is not None and sid not in id_set:
                id_set[sid] = rec
            for reason in discovery.provenance.get(sid, []):
                _mark(sid, reason)

    records_by_id: dict[str, SequenceRecord] = dict(id_set)
    bucket_records = list(records_by_id.values())

    def _length_score(rec: SequenceRecord) -> tuple[int, str]:
        return (abs(rec.length - qlen), rec.id)

    # When trimming to a bounded bucket, keep a mix of:
    # - stable "seed" building blocks,
    # - a slice of invariant-filtered candidates (exact-ish),
    # - similarity-ranked candidates.
    #
    # Rationale:
    # Similarity alone can miss useful components (e.g., shifted Fibonacci inside a
    # Lucas identity). Exact/invariant candidates help keep those around.
    if max_records is not None:
        max_records = int(max_records)
        selected: list[SequenceRecord] = []
        selected_ids: set[str] = set()

        def _add(seq_id: str) -> None:
            if seq_id in selected_ids:
                return
            rec = records_by_id.get(seq_id)
            if rec is None:
                return
            selected.append(rec)
            selected_ids.add(seq_id)

        # 1) Seeds first (if present in this DB and provider enabled)
        if "seed" in provider_order:
            for sid in seed_ids:
                _add(sid)
                if len(selected) >= max_records:
                    break

        if len(selected) < max_records:
            rem = max_records - len(selected)
            # Keep ~1/3 exact-ish + ~2/3 similarity-ish by default.
            if exact_ids and sim_ids:
                exact_budget = max(0, rem // 3)
                sim_budget = rem - exact_budget
            elif exact_ids:
                exact_budget = rem
                sim_budget = 0
            else:
                exact_budget = 0
                sim_budget = rem

            # 2) Invariant-filtered candidates (stable)
            exact_added = 0
            for sid in exact_ids:
                if exact_added >= exact_budget:
                    break
                if sid in records_by_id and sid not in selected_ids:
                    _add(sid)
                    exact_added += 1
                if len(selected) >= max_records:
                    break

            # 3) Similarity-ranked candidates (query-specific)
            sim_added = 0
            for sid in sim_ids:
                if sim_added >= sim_budget:
                    break
                if sid in records_by_id and sid not in selected_ids:
                    _add(sid)
                    sim_added += 1
                if len(selected) >= max_records:
                    break

            # 4) Fill remaining slots by length closeness, then id for determinism.
            if len(selected) < max_records:
                remaining = [r for r in bucket_records if r.id not in selected_ids]
                remaining.sort(key=_length_score)
                for r in remaining:
                    if len(selected) >= max_records:
                        break
                    selected.append(r)
                    selected_ids.add(r.id)

        bucket_records = selected[:max_records]

    chosen_ids = {r.id for r in bucket_records}
    exact_ids = [i for i in exact_ids if i in chosen_ids]
    transform_ids = [i for i in transform_ids if i in chosen_ids]
    sim_ids = [i for i in sim_ids if i in chosen_ids]
    discovery_ids = [i for i in discovery_ids if i in chosen_ids]

    if "expanded" in provider_order and max_records is not None and len(bucket_records) < max_records:
        from .storage import iter_sequences

        for rec in iter_sequences(db_path):
            if deadline_s is not None and time_fn() >= deadline_s:
                break
            if rec.id in id_set:
                continue
            if rec.length < query.min_match_length:
                continue
            bucket_records.append(rec)
            id_set[rec.id] = rec
            _mark(rec.id, "expanded")
            if len(bucket_records) >= max_records:
                break

    provenance = {sid: rs for sid, rs in provenance.items() if sid in {r.id for r in bucket_records}}
    return CandidateBucket(
        exact_ids=exact_ids,
        transform_ids=transform_ids,
        similar_ids=sim_ids,
        discovery_ids=discovery_ids,
        records=bucket_records,
        provenance=provenance,
        discovery_diagnostics=discovery_diag,
        provider_diagnostics=provider_diag,
    )
