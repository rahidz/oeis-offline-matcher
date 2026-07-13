from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import heapq
from typing import Callable, List

from .matcher import candidate_sequences
from .models import SequenceQuery, SequenceRecord
from .similarity import correlation, mse_after_scale_offset


@dataclass(frozen=True)
class ScoredCandidate:
    record: SequenceRecord
    corr: float
    mse: float
    scale: float
    offset: float


def rank_candidates_for_query(
    query: SequenceQuery,
    db_path: Path,
    *,
    top_k: int = 50,
    min_len: int | None = None,
    use_prefix_index: bool = True,
    loosen_nonzero: bool = False,
    min_corr: float | None = None,
    max_mse: float | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
    candidate_limit: int | None = None,
) -> List[ScoredCandidate]:
    """
    Filter candidates by invariants, then rank by correlation and MSE after scale/offset fit.
    """
    if deadline_s is not None and time_fn() >= deadline_s:
        return []
    if any(t is None for t in query.terms):
        return []
    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        top_k = 0
    if top_k <= 0:
        return []
    seq_iter = candidate_sequences(
        db_path,
        query,
        use_prefix_index=use_prefix_index,
        loosen_nonzero=loosen_nonzero,
        variance_band=variance_band,
        growth_band=growth_band,
        limit=candidate_limit,
    )
    q_terms = query.terms
    # Keep only the top-k candidates as we stream, to avoid holding/sorting O(N)
    # candidates for wide filters.
    heap: list[tuple[tuple[float, float, str], ScoredCandidate]] = []

    for rec in seq_iter:
        if deadline_s is not None and time_fn() >= deadline_s:
            break
        if min_len and rec.length < min_len:
            continue
        try:
            mse, a, b = mse_after_scale_offset(q_terms, rec.terms)
            corr_val = correlation(q_terms, rec.terms)
        except OverflowError:
            # Extremely large magnitudes can overflow float ops; skip such candidates.
            continue
        if min_corr is not None and corr_val < min_corr:
            continue
        if max_mse is not None and mse > max_mse:
            continue
        cand = ScoredCandidate(record=rec, corr=corr_val, mse=mse, scale=a, offset=b)
        # Higher corr is better; lower mse is better; break ties by id for determinism.
        key = (float(corr_val), -float(mse), rec.id)
        item = (key, cand)
        if len(heap) < top_k:
            heapq.heappush(heap, item)
            continue
        if item[0] > heap[0][0]:
            heapq.heapreplace(heap, item)

    out = [c for _, c in heap]
    out.sort(key=lambda c: (-c.corr, c.mse, c.record.id))
    return out[:top_k]
