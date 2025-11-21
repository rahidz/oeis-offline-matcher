from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

from .matcher import match_exact, candidate_sequences
from .models import Match, SequenceQuery, SequenceRecord
from .storage import iter_sequences, iter_sequences_by_prefix
from .transforms import Transform, apply_chain, default_transforms, enumerate_chains


def _sequence_iter_for_terms(db_path: Path, terms: List[int], allow_subsequence: bool) -> Iterable[SequenceRecord]:
    dummy_query = SequenceQuery(terms=terms, min_match_length=3, allow_subsequence=allow_subsequence)
    return candidate_sequences(db_path, dummy_query)


def search_transform_matches(
    query: SequenceQuery,
    db_path: Path,
    *,
    max_depth: int = 2,
    transforms: Sequence[Transform] | None = None,
    limit: int = 20,
    snippet_len: int | None = None,
) -> List[Match]:
    """
    Apply transform chains to the query and run exact matcher on each transformed query.
    Returns matches annotated with the transform description.
    """
    transforms = list(transforms or default_transforms())
    chains = enumerate_chains(transforms, max_depth)

    results: List[Match] = []
    seen_keys = set()

    for chain in chains:
        transformed_terms, desc = apply_chain(query.terms, chain)
        if len(transformed_terms) < query.min_match_length:
            continue

        t_query = SequenceQuery(
            terms=transformed_terms,
            min_match_length=query.min_match_length,
            allow_subsequence=query.allow_subsequence,
        )

        seq_iter = _sequence_iter_for_terms(db_path, transformed_terms, query.allow_subsequence)
        matches = match_exact(t_query, seq_iter, limit=limit, snippet_len=snippet_len)
        for m in matches:
            key = (m.id, desc, m.match_type, m.offset, m.length)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            score = _score_match(m, chain)
            with_desc = replace(m, transform_desc=desc, score=score)
            results.append(with_desc)
            if len(results) >= limit:
                return _sorted_transform_results(results)

    return _sorted_transform_results(results)


def _sorted_transform_results(results: List[Match]) -> List[Match]:
    return sorted(
        results,
        key=lambda m: (
            -(m.score if m.score is not None else 0),
            m.transform_desc.count("∘") if m.transform_desc else 0,
            0 if m.match_type == "prefix" else 1,
            m.offset,
        ),
    )


def _score_match(m: Match, chain: Sequence[Transform]) -> float:
    """
    Heuristic score: matched length divided by (1 + complexity penalty).
    """
    comp = _chain_complexity(chain)
    base = m.length
    return base / (1.0 + comp)


def _chain_complexity(chain: Sequence[Transform]) -> float:
    weight = 0.0
    for t in chain:
        name = t.name
        if name.startswith("scale("):
            weight += 0.6
        elif name.startswith("affine("):
            weight += 1.0
        elif name.startswith("shift("):
            weight += 0.4
        elif name == "diff":
            weight += 1.2
        elif name == "partial_sum":
            weight += 1.1
        elif name.startswith("decimate"):
            weight += 1.5
        elif name == "gcd_norm":
            weight += 0.3
        elif name == "abs":
            weight += 0.2
        else:
            weight += 1.0
    return weight
