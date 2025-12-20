from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable, List

from .matcher import candidate_sequences
from .models import SequenceQuery, SequenceRecord
from .ranking import rank_candidates_for_query


@dataclass(frozen=True)
class CandidateBucket:
    exact_ids: List[str]
    transform_ids: List[str]
    similar_ids: List[str]
    records: List[SequenceRecord]


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
) -> CandidateBucket:
    """
    Collect a union of ids from direct candidate filter and similarity ranking,
    capped to keep combination search manageable.
    """
    if deadline_s is not None and time_fn() >= deadline_s:
        return CandidateBucket(exact_ids=[], transform_ids=[], similar_ids=[], records=[])
    qlen = len(query.terms)
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
    seed_ids_order: dict[str, int] = {sid: i for i, sid in enumerate(seed_ids)}
    seed_records: list[SequenceRecord] = []
    from .storage import get_sequence_by_id

    for sid in seed_ids:
        rec = get_sequence_by_id(db_path, sid)
        if rec:
            seed_records.append(rec)

    # Start with invariant-filtered pool (candidate_sequences) truncated.
    # When a hard deadline is provided, stop early and return the partial bucket.
    if skip_prefix_filter and max_records is not None:
        # In "unfiltered" mode, we deliberately avoid using the prefix index. The
        # invariant filter can still return a large set, so keep it bounded with a
        # simple LIMIT. The seed set + expanded fallback handle the harder cases.
        base_records = []
        for rec in candidate_sequences(
            db_path,
            query,
            use_prefix_index=False,
            loosen_nonzero=True,
            variance_band=variance_band,
            growth_band=growth_band,
            limit=max_records,
        ):
            if deadline_s is not None and time_fn() >= deadline_s:
                break
            base_records.append(rec)
    else:
        base_records: list[SequenceRecord] = []
        for rec in candidate_sequences(
            db_path,
            query,
            use_prefix_index=not skip_prefix_filter,
            loosen_nonzero=skip_prefix_filter,
            variance_band=variance_band,
            growth_band=growth_band,
        ):
            if deadline_s is not None and time_fn() >= deadline_s:
                break
            base_records.append(rec)
            if len(base_records) >= exact_limit:
                break
    exact_ids = [r.id for r in base_records]

    # Similarity-ranked set
    sim_top = max_records if (skip_prefix_filter and max_records is not None) else similar_limit
    sim_candidate_limit: int | None = None
    if skip_prefix_filter and max_records is not None:
        # In unfiltered mode, similarity ranking can otherwise end up scanning a very
        # large portion of the DB (expensive and delays combo streaming). Bound the
        # scan to a moderate window; the expanded combo fallback handles the hard cases.
        sim_candidate_limit = max(5000, int(max_records) * 50)
    sim = rank_candidates_for_query(
        query,
        db_path,
        top_k=sim_top,
        use_prefix_index=not skip_prefix_filter,
        loosen_nonzero=skip_prefix_filter,
        min_corr=None,
        max_mse=None,
        deadline_s=deadline_s,
        time_fn=time_fn,
        candidate_limit=sim_candidate_limit,
    )
    sim_ids = [c.record.id for c in sim]

    # Transform ids will be added by transform search; placeholder empty for now
    transform_ids: List[str] = []

    # Union records by id
    id_set = {}
    for r in seed_records:
        id_set[r.id] = r
    for r in base_records:
        id_set[r.id] = r
    for c in sim:
        if c.record.id not in id_set:
            id_set[c.record.id] = c.record

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

        # 1) Seeds first (if present in this DB)
        for sid in seed_ids:
            _add(sid)
            if len(selected) >= max_records:
                break

        if len(selected) < max_records:
            rem = max_records - len(selected)
            # Keep ~1/3 exact-ish + ~2/3 similarity-ish by default.
            exact_budget = max(0, rem // 3)
            sim_budget = rem - exact_budget

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

    if fill_unfiltered and max_records is not None and len(bucket_records) < max_records:
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
            if len(bucket_records) >= max_records:
                break

    return CandidateBucket(
        exact_ids=exact_ids,
        transform_ids=transform_ids,
        similar_ids=sim_ids,
        records=bucket_records,
    )
