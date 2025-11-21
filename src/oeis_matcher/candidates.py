from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import heapq
from typing import List, Sequence

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
) -> CandidateBucket:
    """
    Collect a union of ids from direct candidate filter and similarity ranking,
    capped to keep combination search manageable.
    """
    qlen = len(query.terms)
    # Start with invariant-filtered pool (candidate_sequences) truncated
    if skip_prefix_filter and max_records is not None:
        # Keep the closest-in-length sequences up to max_records using a bounded heap.
        heap: list[tuple[int, str, SequenceRecord]] = []
        qlen = len(query.terms)
        for rec in candidate_sequences(db_path, query, use_prefix_index=False, loosen_nonzero=True):
            score = abs(rec.length - qlen)
            item = (-score, rec.id, rec)  # worst (largest score) has most-negative value
            if len(heap) < max_records:
                heapq.heappush(heap, item)
            else:
                if item > heap[0]:
                    heapq.heapreplace(heap, item)
        base_records = [h[2] for h in heap]
    else:
        base_records = list(
            candidate_sequences(
                db_path,
                query,
                use_prefix_index=not skip_prefix_filter,
                loosen_nonzero=skip_prefix_filter,
            )
        )
        # Restrict to avoid explosion
        if len(base_records) > exact_limit:
            base_records = base_records[:exact_limit]
    exact_ids = [r.id for r in base_records]

    # Similarity-ranked set
    sim_top = max_records if (skip_prefix_filter and max_records is not None) else similar_limit
    sim = rank_candidates_for_query(
        query,
        db_path,
        top_k=sim_top,
        use_prefix_index=not skip_prefix_filter,
        loosen_nonzero=skip_prefix_filter,
    )
    sim_ids = [c.record.id for c in sim]

    # Transform ids will be added by transform search; placeholder empty for now
    transform_ids: List[str] = []

    # Union records by id
    id_set = {}
    for r in base_records:
        id_set[r.id] = r
    for c in sim:
        if c.record.id not in id_set:
            id_set[c.record.id] = c.record

    bucket_records = list(id_set.values())

    def _length_score(rec: SequenceRecord) -> tuple[int, str]:
        return (abs(rec.length - qlen), rec.id)

    # Prioritize similarity-picked records when we later trim.
    sim_order = {sid: idx for idx, sid in enumerate(sim_ids)}
    priority_ids = set(sim_ids)
    priority_recs = [r for r in bucket_records if r.id in priority_ids]
    priority_recs.sort(key=lambda r: sim_order.get(r.id, 0))
    other_recs = [r for r in bucket_records if r.id not in priority_ids]
    other_recs.sort(key=_length_score)
    bucket_records = priority_recs + other_recs

    if max_records is not None and len(bucket_records) > max_records:
        bucket_records = bucket_records[:max_records]
    chosen_ids = {r.id for r in bucket_records}
    exact_ids = [i for i in exact_ids if i in chosen_ids]
    transform_ids = [i for i in transform_ids if i in chosen_ids]
    sim_ids = [i for i in sim_ids if i in chosen_ids]

    if fill_unfiltered and max_records is not None and len(bucket_records) < max_records:
        from .storage import iter_sequences

        for rec in iter_sequences(db_path):
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
