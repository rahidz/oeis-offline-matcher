from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

from .matcher import match_exact, candidate_sequences
from .models import Match, SequenceQuery, SequenceRecord
from .storage import iter_sequences, iter_sequences_by_prefix
from .transforms import Transform, apply_chain, default_transforms, enumerate_chains, describe_chain


def _sequence_iter_for_terms(db_path: Path, terms: List[int], allow_subsequence: bool) -> Iterable[SequenceRecord]:
    dummy_query = SequenceQuery(terms=terms, min_match_length=3, allow_subsequence=allow_subsequence)
    return candidate_sequences(db_path, dummy_query)


def search_transform_matches(
    query: SequenceQuery,
    db_path: Path,
    *,
    max_depth: int = 2,
    transforms: Sequence[Transform] | None = None,
    limit: int | None = 20,
    snippet_len: int | None = None,
    full_scan: bool = False,
) -> List[Match]:
    """
    Apply transform chains to the query and run exact matcher on each transformed query.
    Returns matches annotated with the transform description.
    """
    if any(t is None for t in query.terms):
        return []
    transforms = list(transforms or default_transforms())
    chains = enumerate_chains(transforms, max_depth)

    results: List[Match] = []
    seen_keys = set()
    all_zero_query = all(v == 0 for v in query.terms)

    for chain in chains:
        transformed_terms, desc = apply_chain(query.terms, chain)
        if len(transformed_terms) < query.min_match_length:
            continue

        if not all_zero_query and transformed_terms and all(v == 0 for v in transformed_terms):
            # Degenerate transform that collapses everything to zero; usually noise.
            continue

        noisy_ops = {"popcount"}
        noisy_prefixes = ("digitsum", "decimate")
        if any((t.name in noisy_ops) or t.name.startswith(noisy_prefixes) for t in chain):
            if len(transformed_terms) < max(query.min_match_length, 6):
                continue
            if len(set(transformed_terms)) <= 2:
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
            human, latex = describe_chain(chain)
            t_snip = transformed_terms[:snippet_len] if snippet_len else None
            with_desc = replace(
                m,
                transform_desc=desc,
                score=score,
                explanation=human,
                latex=latex,
                transformed_terms=t_snip,
            )
            results.append(with_desc)
            if (not full_scan) and limit is not None and len(results) >= limit:
                return _trim_transform_results(results, limit)

    return _trim_transform_results(results, limit)


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


def _trim_transform_results(results: List[Match], limit: int | None) -> List[Match]:
    """
    Sort results, then keep the best-per-(id, match_type) to avoid flooding
    with many transform variants of the same sequence. Limit applies after
    deduplication.
    """
    sorted_results = _sorted_transform_results(results)
    seen: set[tuple[str, str]] = set()
    deduped: List[Match] = []
    for m in sorted_results:
        key = (m.id, m.match_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


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
        elif name.startswith("diff^"):
            weight += 1.6
        elif name == "partial_sum":
            weight += 1.1
        elif name == "cumprod":
            weight += 1.8
        elif name.startswith("decimate"):
            weight += 1.5
        elif name == "gcd_norm":
            weight += 0.3
        elif name == "abs":
            weight += 0.2
        elif name == "popcount":
            weight += 1.2
        elif name.startswith("digitsum"):
            weight += 1.0
        elif name == "reverse":
            weight += 0.5
        elif name in ("even_terms", "odd_terms"):
            weight += 0.8
        elif name.startswith("movsum("):
            weight += 1.0
        else:
            weight += 1.0
    return weight
