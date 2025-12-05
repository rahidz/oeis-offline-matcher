from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

from .matcher import match_exact, candidate_sequences
from .models import Match, SequenceQuery, SequenceRecord
from .storage import iter_sequences, iter_sequences_by_prefix
from .transforms import Transform, apply_chain, default_transforms, enumerate_chains, describe_chain
from .storage import SequenceRecord as _SeqRec  # type alias for hints

def _popularity_bonus(keywords: list[str] | None, weights: dict[str, float] | None) -> float:
    if not keywords or not weights:
        return 0.0
    return sum(weights.get(k, 0.0) for k in keywords)

def _variance(values: list[int]) -> float | None:
    if len(values) < 2:
        return None
    try:
        m = sum(values) / len(values)
        return sum((v - m) ** 2 for v in values) / len(values)
    except OverflowError:
        # Extremely large integers (e.g., from exp transforms). Skip variance-based heuristics.
        return None


def _is_simple_arith_prog(seq: list[int]) -> tuple[bool, int | None]:
    """
    Returns (is_arith, step). Treats length<2 as not arithmetic.
    """
    if len(seq) < 2:
        return False, None
    step = seq[1] - seq[0]
    for a, b in zip(seq, seq[1:]):
        if b - a != step:
            return False, None
    return True, step


def _sequence_iter_for_terms(
    db_path: Path,
    terms: List[int],
    allow_subsequence: bool,
    *,
    variance_band: float | None = None,
    growth_band: float | None = None,
) -> Iterable[SequenceRecord]:
    dummy_query = SequenceQuery(terms=terms, min_match_length=3, allow_subsequence=allow_subsequence)
    return candidate_sequences(db_path, dummy_query, loosen_nonzero=True, variance_band=variance_band, growth_band=growth_band)


def _allows_low_diversity(chain: Sequence[Transform]) -> bool:
    """
    Some transforms naturally collapse diversity (e.g., diff of an arithmetic
    progression → constant). Permit these to pass the diversity/constant
    filters so we still surface meaningful hits like diff(n) = 1.
    """
    for t in chain:
        name = t.name
        if name.startswith("diff"):
            return True
        if name == "partial_sum":
            return True
        if name.startswith("movsum("):
            return True
        if name == "gcd_norm":
            return True
    return False


def _render_symbolic_chain(chain: Sequence[Transform], *, latex: bool = False) -> str:
    """
    Render a transform chain applied to a(n) into a compact symbolic string.
    Uses a simple heuristic mapping for common transforms; falls back to name(expr).
    """
    expr = "a_n" if latex else "a(n)"

    def paren(s: str) -> str:
        if latex:
            return f"\\left({s}\\right)"
        return f"({s})"

    for t in chain:
        name = t.name
        if name == "diff":
            expr = f"\\Delta {expr}" if latex else f"Δ {expr}"
        elif name.startswith("diff^"):
            k = name.split("^", 1)[1]
            expr = (f"\\Delta^{{{k}}} {expr}") if latex else f"Δ^{k} {expr}"
        elif name == "partial_sum":
            expr = f"\\Sigma {expr}" if latex else f"Σ {expr}"
        elif name.startswith("shift("):
            k = int(name[name.index("(") + 1 : -1])
            sign = f"{k:+d}"
            if latex:
                if expr.startswith("a_"):
                    expr = f"a_{{n{sign}}}"
                else:
                    expr = f"{expr}\\big|_{{n\\to n{sign}}}"
            else:
                if expr.startswith("a("):
                    expr = f"a(n{sign})"
                else:
                    expr = f"{expr}[n{sign}]"
        elif name.startswith("scale("):
            k = name[name.index("(") + 1 : -1]
            expr = f"{k}\\,{expr}" if latex else f"{k}*{expr}"
        elif name.startswith("affine("):
            vals = name[name.index("(") + 1 : -1]
            k, b = vals.split(",")
            mult = f"{k}\\," if latex else f"{k}*"
            expr = f"{mult}{paren(expr)} + {b}"
        elif name == "abs":
            expr = f"\\left|{expr}\\right|" if latex else f"|{expr}|"
        elif name == "gcd_norm":
            expr = f"{expr}/\\gcd" if latex else f"{expr}/gcd"
        elif name.startswith("movsum("):
            expr = (f"\\mathrm{{movsum}}({name[name.index('(')+1:-1]},{expr})") if latex else f"movsum({expr})"
        else:
            if latex:
                expr = f"\\mathrm{{{name}}}({expr})"
            else:
                expr = f"{name}({expr})"
    return expr


def search_transform_matches(
    query: SequenceQuery,
    db_path: Path,
    *,
    max_depth: int = 2,
    transforms: Sequence[Transform] | None = None,
    limit: int | None = 20,
    snippet_len: int | None = None,
    full_scan: bool = False,
    max_time_s: float | None = None,
    time_fn=None,
    min_score: float | None = None,
    max_complexity: float | None = None,
    variance_band: float | None = None,
    growth_band: float | None = None,
    allow_binomial: bool = False,
    allow_euler: bool = False,
    popularity_weights: dict[str, float] | None = None,
) -> List[Match]:
    """
    Apply transform chains to the query and run exact matcher on each transformed query.
    Returns matches annotated with the transform description.
    """
    if any(t is None for t in query.terms):
        return []
    transforms = list(transforms or default_transforms(allow_binomial=allow_binomial, allow_euler=allow_euler))
    chains = enumerate_chains(transforms, max_depth)

    if snippet_len is None:
        snippet_len = len(query.terms) if query.terms else None

    results: List[Match] = []
    seen_keys = set()
    all_zero_query = all(v == 0 for v in query.terms)
    q_terms_no_none = [v for v in query.terms if v is not None]
    q_distinct = len(set(q_terms_no_none))
    q_var = _variance(q_terms_no_none) if q_terms_no_none else None
    all_same_query = len(set(query.terms)) == 1 if query.terms else False
    q_len = len(q_terms_no_none)
    seen_transformed: set[tuple] = set()
    if time_fn is None:
        import time
        time_fn = time.perf_counter
    t_start = time_fn()

    for chain in chains:
        transformed_terms, desc = apply_chain(query.terms, chain)
        if len(transformed_terms) < query.min_match_length:
            continue
        allow_low_diversity = _allows_low_diversity(chain)
        chain_has_rle = any(t.name == "rle_len" for t in chain)

        t_distinct = len(set(transformed_terms)) if transformed_terms else 0
        t_var = _variance(transformed_terms)

        # Drop low-diversity transforms unless the query is equally low-diversity.
        if t_distinct <= 2 and q_distinct > 2 and not allow_low_diversity:
            continue

        # Drop very-low-variance transforms relative to query variance (noise collapse).
        if q_var and t_var and q_var > 0 and t_var < 0.05 * q_var and q_distinct > 2:
            continue

        if transformed_terms and len(set(transformed_terms)) == 1:
            const_val = transformed_terms[0]
            # Always drop all-zero constants; they are almost always noise.
            if const_val == 0:
                continue
            # Skip very short constant runs.
            if len(transformed_terms) < query.min_match_length:
                continue
            # Drop constant transforms when the original query is not constant
            # to reduce spurious hits (e.g., rle collapsing to all-ones).
            if not all_same_query and not allow_low_diversity:
                continue

        # Heuristic guard: RLE collapsing random data to naturals/arith progressions
        if chain_has_rle and transformed_terms:
            is_arith, step = _is_simple_arith_prog(transformed_terms)
            ones_ratio = transformed_terms.count(1) / len(transformed_terms)
            if q_distinct > 3:
                # Mostly ones (typical of rle on alternating data) → drop
                if ones_ratio > 0.6:
                    continue
                # Simple arithmetic with step ±1 starting at 1 (e.g., naturals) → drop
                if is_arith and abs(step or 0) == 1 and transformed_terms[0] == 1:
                    continue

        key_terms = tuple(transformed_terms)
        if key_terms in seen_transformed:
            continue
        seen_transformed.add(key_terms)

        noisy_ops = {"popcount", "xor_index", "rle_len", "rle_dec"}
        noisy_prefixes = ("digitsum", "decimate", "mod(", "concat(", "log", "exp")
        if any((t.name in noisy_ops) or t.name.startswith(noisy_prefixes) for t in chain):
            if len(transformed_terms) < max(query.min_match_length, 6):
                continue
            if len(set(transformed_terms)) < 4:
                continue
            # Additional guard: simple arithmetic outputs from noisy chains often mean spurious matches.
            is_arith, step = _is_simple_arith_prog(transformed_terms)
            if is_arith and abs(step or 0) <= 1 and q_distinct > 3:
                continue

        if max_time_s is not None and (time_fn() - t_start) > max_time_s:
            return _trim_transform_results(results, limit)

        t_query = SequenceQuery(
            terms=transformed_terms,
            min_match_length=query.min_match_length,
            allow_subsequence=query.allow_subsequence,
        )

        seq_iter = _sequence_iter_for_terms(
            db_path, transformed_terms, query.allow_subsequence, variance_band=variance_band, growth_band=growth_band
        )
        matches = match_exact(t_query, seq_iter, limit=limit, snippet_len=snippet_len)
        for m in matches:
            key = (m.id, desc, m.match_type, m.offset, m.length)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            comp = _chain_complexity(chain)
            if max_complexity is not None and comp > max_complexity:
                continue
            pop_bonus = _popularity_bonus(m.keywords, popularity_weights) if popularity_weights else 0.0
            score = _score_match(
                m,
                chain,
                precomputed_comp=comp,
                q_distinct=q_distinct,
                t_distinct=t_distinct,
                q_var=q_var,
                t_var=t_var,
                q_len=q_len,
                pop_bonus=pop_bonus,
            )
            if min_score is not None and score < min_score:
                continue
            human, latex = describe_chain(chain)
            sym = _render_symbolic_chain(chain, latex=False)
            sym_latex = _render_symbolic_chain(chain, latex=True)
            offset_str = "" if m.offset == 0 else f"+{m.offset}" if m.offset > 0 else f"{m.offset}"
            lhs = f"{m.id}(n{offset_str})"
            lhs_latex = f"\\mathrm{{{m.id}}}(n{offset_str})"
            symbolic = f"{lhs} = {sym}"
            symbolic_latex = f"{lhs_latex} = {sym_latex}"
            t_snip = transformed_terms[:snippet_len] if snippet_len else None
            with_desc = replace(
                m,
                transform_desc=desc,
                score=score,
                explanation=human,
                latex=latex,
                symbolic=symbolic,
                symbolic_latex=symbolic_latex,
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


def _score_match(m: Match, chain: Sequence[Transform], precomputed_comp: float | None = None) -> float:
    raise NotImplementedError("Use extended _score_match_with_stats")


def _score_match(
    m: Match,
    chain: Sequence[Transform],
    *,
    precomputed_comp: float | None = None,
    q_distinct: int | None = None,
    t_distinct: int | None = None,
    q_var: float | None = None,
    t_var: float | None = None,
    q_len: int | None = None,
    pop_bonus: float = 0.0,
) -> float:
    """
    Heuristic score: matched length divided by (1 + complexity),
    with small bonuses for diversity and variance alignment.
    """
    comp = precomputed_comp if precomputed_comp is not None else _chain_complexity(chain)
    base = m.length
    score = base / (1.0 + comp)

    # Coverage bonus: prefer matches that cover more of the query (up to +20%)
    if q_len and q_len > 0:
        coverage = min(1.0, base / q_len)
        score *= 0.8 + 0.2 * coverage

    # Distinct-count alignment bonus (caps at +10%)
    if q_distinct and t_distinct and q_distinct > 0 and t_distinct > 0:
        diversity_ratio = min(t_distinct, q_distinct) / max(t_distinct, q_distinct)
        score *= 1.0 + 0.1 * diversity_ratio

    # Variance alignment bonus (caps at +5%)
    if q_var and t_var and q_var > 0 and t_var > 0:
        var_ratio = min(t_var, q_var) / max(t_var, q_var)
        score *= 1.0 + 0.05 * var_ratio

    # Popularity bonus (keywords): modest lift for core/nice/easy tags
    if pop_bonus > 0:
        score *= 1.0 + 0.05 * min(pop_bonus, 3.0)

    # Offset alignment bonus (prefix matches aligning to sequence offset start)
    if m.match_type == "prefix" and m.seq_offset and m.seq_offset[0] is not None:
        if m.offset == m.seq_offset[0]:
            score *= 1.05
        elif m.offset > m.seq_offset[0]:
            score *= 0.97

    # Formula presence: tiny bonus
    if m.has_formula:
        score *= 1.02

    return score


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
        elif name.startswith("mod("):
            weight += 0.9
        elif name == "xor_index":
            weight += 1.3
        elif name == "reverse":
            weight += 0.5
        elif name in ("even_terms", "odd_terms"):
            weight += 0.8
        elif name.startswith("movsum("):
            weight += 1.0
        elif name == "binomial":
            weight += 1.6
        elif name == "rle_len":
            weight += 1.9
        elif name == "mobius":
            weight += 1.7
        elif name.startswith("concat("):
            weight += 1.4
        elif name.startswith("log"):
            weight += 1.5
        elif name.startswith("exp"):
            weight += 1.8
        elif name == "rle_dec":
            weight += 1.9
        else:
            weight += 1.0
    return weight
