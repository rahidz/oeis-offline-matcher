from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from .matcher import candidate_sequences
from .models import Match, SequenceQuery, SequenceRecord
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
) -> List[ScoredCandidate]:
    """
    Filter candidates by invariants, then rank by correlation and MSE after scale/offset fit.
    """
    if any(t is None for t in query.terms):
        return []
    seq_iter = candidate_sequences(db_path, query, use_prefix_index=use_prefix_index, loosen_nonzero=loosen_nonzero)
    scored: List[ScoredCandidate] = []
    q_terms = query.terms
    q_len = len(q_terms)

    for rec in seq_iter:
        if min_len and rec.length < min_len:
            continue
        try:
            mse, a, b = mse_after_scale_offset(q_terms, rec.terms)
            corr_val = correlation(q_terms, rec.terms)
        except OverflowError:
            # Extremely large magnitudes can overflow float ops; skip such candidates.
            continue
        scored.append(ScoredCandidate(record=rec, corr=corr_val, mse=mse, scale=a, offset=b))

    scored.sort(key=lambda c: (-c.corr, c.mse))
    return scored[:top_k]
