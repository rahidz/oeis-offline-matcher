from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, List, Sequence
import math

from .matcher import DBExactMatcher, match_exact, candidate_sequences
from .models import Match, SequenceQuery, SequenceRecord
from .storage import iter_sequences, iter_sequences_by_prefix, invariant_stats
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
        if name == "ratio_int":
            return True
        if name.startswith("movsum("):
            return True
        if name == "gcd_norm":
            return True
        if name in {
            "inv_binomial",
            "inv_euler_ogf",
            "inv_stirling1",
            "inv_stirling2",
            "ogf_inv",
            "series_reversion",
        }:
            # Inverse transforms can legitimately reduce variance/diversity
            # when undoing a previously expansive map.
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
        elif name == "alt_sign":
            expr = f"(-1)^n\\,{expr}" if latex else f"(-1)^n*{expr}"
        elif name.startswith("affine("):
            vals = name[name.index("(") + 1 : -1]
            k, b = vals.split(",")
            mult = f"{k}\\," if latex else f"{k}*"
            expr = f"{mult}{paren(expr)} + {b}"
        elif name == "abs":
            expr = f"\\left|{expr}\\right|" if latex else f"|{expr}|"
        elif name == "gcd_norm":
            expr = f"{expr}/\\gcd" if latex else f"{expr}/gcd"
        elif name == "ratio_int":
            expr = f"\\Delta\\log {expr}" if latex else f"ratio({expr})"
        elif name == "euler_ogf":
            expr = f"\\mathcal{{E}}\\,{expr}" if latex else f"EulerOGF({expr})"
        elif name == "inv_euler_ogf":
            expr = f"\\mathcal{{E}}^{{-1}}\\,{expr}" if latex else f"InvEulerOGF({expr})"
        elif name == "stirling1":
            expr = f"\\mathbf{{S}}_1\\,{expr}" if latex else f"Stirling1({expr})"
        elif name == "stirling2":
            expr = f"\\mathbf{{S}}_2\\,{expr}" if latex else f"Stirling2({expr})"
        elif name == "inv_stirling1":
            expr = f"\\mathbf{{S}}_1^{{-1}}\\,{expr}" if latex else f"InvStirling1({expr})"
        elif name == "inv_stirling2":
            expr = f"\\mathbf{{S}}_2^{{-1}}\\,{expr}" if latex else f"InvStirling2({expr})"
        elif name == "ogf_inv":
            expr = f"\\mathrm{{OGFInv}}\\,{expr}" if latex else f"OGFInv({expr})"
        elif name == "series_reversion":
            expr = f"\\mathrm{{Rev}}\\,{expr}" if latex else f"Rev({expr})"
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
    allow_constant_outputs: bool = False,
    on_match: Callable[[Match], None] | None = None,
) -> List[Match]:
    """
    Apply transform chains to the query and run exact matcher on each transformed query.
    Returns matches annotated with the transform description.
    """
    if any(t is None for t in query.terms):
        return []
    transforms = list(transforms or default_transforms(allow_binomial=allow_binomial, allow_euler=allow_euler))
    # Avoid recomputing the first transform in every depth-2 chain by caching
    # single-step outputs and then applying the second transform to the cached
    # intermediate.
    #
    # This matters most in `--preset deep/max` where the transform vocabulary
    # is large but `max_depth` is typically 2.
    def _allow_pair(t1: Transform, t2: Transform) -> bool:
        n1, n2 = t1.name, t2.name
        # Drop immediate idempotent/involution repeats that do not add information.
        if n1 == n2 and n1 in {
            "abs",
            "reverse",
            "gcd_norm",
            "alt_sign",
            "ratio_int",
            "euler_ogf",
            "inv_euler_ogf",
            "stirling1",
            "stirling2",
            "inv_stirling1",
            "inv_stirling2",
            "ogf_inv",
            "series_reversion",
        }:
            return False
        # Drop immediate inverse-cancel pairs for heavy transforms.
        if (n1, n2) in {
            ("euler_ogf", "inv_euler_ogf"),
            ("inv_euler_ogf", "euler_ogf"),
            ("stirling1", "inv_stirling1"),
            ("inv_stirling1", "stirling1"),
            ("stirling2", "inv_stirling2"),
            ("inv_stirling2", "stirling2"),
        }:
            return False
        # Index selectors are strong reducers; chaining many of them explodes
        # equivalent families with little explanatory gain.
        if n1.startswith("index_") and n2.startswith("index_"):
            return False
        if n1.startswith("index_powk(") and n2.startswith("index_"):
            return False
        if n1.startswith("index_") and n2.startswith("index_powk("):
            return False
        # Chaining p-adic valuations rarely yields useful additional structure.
        if n1.startswith("vp(") and n2.startswith("vp("):
            return False
        return True

    def _iter_chains_with_outputs() -> Iterable[tuple[list[Transform], list[int], str]]:
        if max_depth <= 0:
            return
        q0 = list(query.terms)
        if max_depth == 1:
            for t1 in transforms:
                out1 = t1.apply(q0)
                yield [t1], out1, t1.name
            return
        if max_depth == 2:
            # Cache the 1-step outputs once per transform.
            level1: list[tuple[Transform, list[int]]] = []
            for t1 in transforms:
                out1 = t1.apply(q0)
                level1.append((t1, out1))
                yield [t1], out1, t1.name
            for t1, out1 in level1:
                for t2 in transforms:
                    if not _allow_pair(t1, t2):
                        continue
                    out2 = t2.apply(out1) if out1 else []
                    yield [t1, t2], out2, f"{t1.name} ∘ {t2.name}"
            return

        # Fallback: higher depths are expected to be rare / explicitly opt-in.
        for chain in enumerate_chains(transforms, max_depth):
            ok = True
            for t1, t2 in zip(chain, chain[1:]):
                if not _allow_pair(t1, t2):
                    ok = False
                    break
            if not ok:
                continue
            out, desc = apply_chain(query.terms, chain)
            yield chain, out, desc

    if snippet_len is None:
        snippet_len = len(query.terms) if query.terms else None

    # Keep only the best match per (id, match_type) to avoid storing and scoring
    # huge intermediate result lists when running in full_scan mode.
    best_by_key: dict[tuple[str, str], Match] = {}
    seen_keys: set[tuple] = set()
    all_zero_query = all(v == 0 for v in query.terms)
    q_terms_no_none = [v for v in query.terms if v is not None]
    q_distinct = len(set(q_terms_no_none))
    q_var = _variance(q_terms_no_none) if q_terms_no_none else None
    all_same_query = len(set(query.terms)) == 1 if query.terms else False
    q_len = len(q_terms_no_none)
    q_nonzero = sum(1 for v in q_terms_no_none if v != 0)
    q_nonzero_ratio = (q_nonzero / q_len) if q_len else 0.0
    seen_transformed: set[tuple] = set()

    if time_fn is None:
        import time

        time_fn = time.perf_counter
    t_start = time_fn()
    inv_stats = invariant_stats(Path(db_path))

    # For prefix-only transform searches (most common), reuse a single DB connection
    # for exact matching so we avoid reconnecting and parsing candidate sequences
    # for every transform chain.
    db_conn = None
    db_matcher: DBExactMatcher | None = None
    if not query.allow_subsequence and len(query.terms) >= 5:
        import sqlite3

        db_conn = sqlite3.connect(str(Path(db_path)))
        db_matcher = DBExactMatcher(db_conn)

    one_step_total = len(transforms) if max_depth >= 1 else 0
    one_step_done = 0

    try:
        for chain, transformed_terms, desc in _iter_chains_with_outputs():
            if len(chain) == 1:
                one_step_done += 1
            if len(transformed_terms) < query.min_match_length:
                continue
            allow_low_diversity = _allows_low_diversity(chain)
            chain_has_rle = any(t.name == "rle_len" for t in chain)

            t_distinct = len(set(transformed_terms)) if transformed_terms else 0
            t_var = _variance(transformed_terms)
            t_is_arith, t_arith_step = _is_simple_arith_prog(transformed_terms) if transformed_terms else (False, None)
            rarity = _invariant_rarity_bonus(transformed_terms, inv_stats)
            chain_has_cumprod = any(t.name == "cumprod" for t in chain)

            # Guard against degenerate cumprod collapses (e.g. diff ∘ cumprod
            # producing 1,0,0,...) on otherwise non-sparse queries.
            if chain_has_cumprod and not allow_constant_outputs and q_distinct > 2 and q_len >= 6 and q_nonzero_ratio >= 0.5:
                t_nonzero = sum(1 for v in transformed_terms if v != 0)
                t_nonzero_ratio = t_nonzero / len(transformed_terms)
                if t_nonzero_ratio <= 0.20 and t_distinct <= 3:
                    continue

            # Drop low-diversity transforms unless the query is equally low-diversity.
            if t_distinct <= 2 and q_distinct > 2 and not allow_low_diversity and not allow_constant_outputs:
                continue

            # Drop very-low-variance transforms relative to query variance (noise collapse).
            if (
                q_var
                and t_var
                and q_var > 0
                and t_var < 0.05 * q_var
                and q_distinct > 2
                and not allow_low_diversity
                and not allow_constant_outputs
            ):
                continue

            if transformed_terms and len(set(transformed_terms)) == 1:
                const_val = transformed_terms[0]

                # Global guard: drop constants unless explicitly allowed or the
                # original query is itself constant. This prevents noisy chains
                # (e.g., movsum→v2) from flooding results with all-ones matches.
                if not allow_constant_outputs and not all_same_query:
                    # Some transforms legitimately collapse structure to constants
                    # (e.g., diff of an arithmetic progression → all ones). Allow
                    # those through while still dropping constants from arbitrary
                    # noisy chains.
                    allows_constants = any(
                        t.name.startswith("diff") or t.name in {"partial_sum", "ratio_int"}
                        for t in chain
                    )
                    if not (allow_low_diversity and allows_constants):
                        continue

                # Retain the previous zero/length safeguards when the guard is
                # disabled; they are cheap and avoid degenerate hits.
                if not allow_constant_outputs and const_val == 0:
                    continue
                if len(transformed_terms) < query.min_match_length:
                    continue

            # Heuristic guard: RLE collapsing random data to naturals/arith progressions
            if chain_has_rle and transformed_terms:
                ones_ratio = transformed_terms.count(1) / len(transformed_terms)
                if q_distinct > 3:
                    # Mostly ones (typical of rle on alternating data) → drop
                    if ones_ratio > 0.6:
                        continue
                    # Simple arithmetic with step ±1 starting at 1 (e.g., naturals) → drop
                    if t_is_arith and abs(t_arith_step or 0) == 1 and transformed_terms[0] == 1:
                        continue

            key_terms = tuple(transformed_terms)
            if key_terms in seen_transformed:
                continue
            seen_transformed.add(key_terms)

            noisy_ops = {"popcount", "xor_index", "rle_len", "rle_dec"}
            noisy_prefixes = ("digitsum", "decimate", "mod(", "concat(", "log", "exp")
            chain_noisy = any((t.name in noisy_ops) or t.name.startswith(noisy_prefixes) for t in chain)
            if chain_noisy:
                if len(transformed_terms) < max(query.min_match_length, 6):
                    continue
                if len(set(transformed_terms)) < 4:
                    continue
                # Additional guard: simple arithmetic outputs from noisy chains often mean spurious matches.
                if t_is_arith and abs(t_arith_step or 0) <= 1 and q_distinct > 3:
                    continue

            if max_time_s is not None and (time_fn() - t_start) > max_time_s:
                return _trim_transform_results(list(best_by_key.values()), limit)

            t_query = SequenceQuery(
                terms=transformed_terms,
                min_match_length=query.min_match_length,
                allow_subsequence=query.allow_subsequence,
            )

            if db_matcher is not None and (not query.allow_subsequence) and len(transformed_terms) >= 5:
                matches = db_matcher.match(t_query, limit=limit, snippet_len=snippet_len)
            else:
                seq_iter = _sequence_iter_for_terms(
                    db_path,
                    transformed_terms,
                    query.allow_subsequence,
                    variance_band=variance_band,
                    growth_band=growth_band,
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
                    rarity_bonus=rarity,
                    allow_low_diversity=allow_low_diversity,
                    chain_noisy=chain_noisy,
                    t_is_arith=t_is_arith,
                    t_arith_step=t_arith_step,
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

                best_key = (with_desc.id, with_desc.match_type)
                prev = best_by_key.get(best_key)
                replace_best = False
                if prev is None or prev.score is None:
                    replace_best = True
                elif with_desc.score is not None:
                    # Prefer higher score; tie-break to simpler chain to keep results stable.
                    eps = 1e-12
                    if with_desc.score > (prev.score + eps):
                        replace_best = True
                    elif abs(with_desc.score - prev.score) <= eps:
                        new_c = with_desc.transform_desc.count("∘") if with_desc.transform_desc else 0
                        old_c = prev.transform_desc.count("∘") if prev.transform_desc else 0
                        if new_c < old_c:
                            replace_best = True
                        elif new_c == old_c:
                            if (with_desc.transform_desc or "") < (prev.transform_desc or ""):
                                replace_best = True

                if replace_best:
                    best_by_key[best_key] = with_desc
                    if on_match is not None:
                        on_match(with_desc)

                if (not full_scan) and limit is not None and len(best_by_key) >= limit:
                    # In non-full-scan mode, avoid returning after the very first transform
                    # family floods results (e.g. scale/shift on the full DB). Always run
                    # through all 1-step transforms first so we keep classic explanations
                    # (diff, partial_sum, etc.) in play.
                    if one_step_done >= one_step_total:
                        return _trim_transform_results(list(best_by_key.values()), limit)

        return _trim_transform_results(list(best_by_key.values()), limit)
    finally:
        if db_conn is not None:
            db_conn.close()


def _sorted_transform_results(results: List[Match]) -> List[Match]:
    return sorted(
        results,
        key=lambda m: (
            -(m.score if m.score is not None else 0),
            m.transform_desc.count("∘") if m.transform_desc else 0,
            0 if m.match_type == "prefix" else 1,
            m.offset,
            m.id,
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

    def _family_key(desc: str | None) -> str:
        """
        Collapse transform descriptions like "scale(-1)" or "scale(2) ∘ diff"
        into a stable family key ("scale", "scale ∘ diff") so we can cap
        flooding by a single transform family.
        """
        if not desc:
            return ""
        parts = [p.strip() for p in desc.split("∘")]
        base: list[str] = []
        for p in parts:
            if not p:
                continue
            head = p.split("(", 1)[0].strip()
            base.append(head or p)
        return " ∘ ".join(base)

    deduped: List[Match] = []
    if limit is None:
        # Keep stable best-per-id behavior.
        for m in sorted_results:
            key = (m.id, m.match_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(m)
        return deduped

    # Pass 1: cap per transform family to avoid floods like "scale(2)" producing
    # dozens of nearly-identical hits. This improves result diversity and keeps
    # meaningful transforms (diff/psum/etc.) visible even on the full OEIS DB.
    family_cap = max(2, int(math.ceil(limit / 8)))
    fam_counts: dict[str, int] = {}
    for m in sorted_results:
        key = (m.id, m.match_type)
        if key in seen:
            continue
        fam = _family_key(m.transform_desc)
        if fam and fam_counts.get(fam, 0) >= family_cap:
            continue
        seen.add(key)
        deduped.append(m)
        if fam:
            fam_counts[fam] = fam_counts.get(fam, 0) + 1
        if len(deduped) >= limit:
            return deduped

    # Pass 2: if we're still under limit, fill with remaining best hits ignoring
    # family caps (ensures we still return close to limit in "sparse" cases).
    for m in sorted_results:
        key = (m.id, m.match_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
        if len(deduped) >= limit:
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
    rarity_bonus: float = 0.0,
    allow_low_diversity: bool = False,
    chain_noisy: bool = False,
    t_is_arith: bool = False,
    t_arith_step: int | None = None,
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

    # Degeneracy penalties: prefer explanations that preserve "shape" unless
    # the chain is known to legitimately collapse diversity (diff/psum/etc.).
    penalty = 1.0

    if (not allow_low_diversity) and q_distinct and t_distinct and q_distinct >= 6:
        collapse_ratio = t_distinct / q_distinct if q_distinct > 0 else 1.0
        if collapse_ratio < 0.15:
            penalty *= 0.70
        elif collapse_ratio < 0.25:
            penalty *= 0.80
        elif collapse_ratio < 0.50:
            penalty *= 0.90

    if chain_noisy:
        # Noisy ops matching "simple" outputs tends to be spurious.
        if t_is_arith and abs(t_arith_step or 0) <= 2 and (q_distinct or 0) > 3:
            penalty *= 0.75
        if t_distinct and t_distinct < 6 and (q_distinct or 0) >= 10:
            penalty *= 0.85

    if (not allow_low_diversity) and q_var and t_var and q_var > 0 and t_var > 0:
        vr = t_var / q_var
        if vr < 0.20 or vr > 5.0:
            penalty *= 0.85

    score *= penalty

    # Popularity bonus (keywords): modest lift for core/nice/easy tags
    if pop_bonus > 0:
        score *= 1.0 + 0.05 * min(pop_bonus, 3.0)

    # Rarity-of-invariants bonus: if the transformed query has rare sign/diff-sign
    # patterns in the DB, treat matches as slightly more significant.
    if rarity_bonus > 0:
        score *= 1.0 + 0.03 * min(rarity_bonus, 6.0)

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
        elif name == "alt_sign":
            weight += 0.5
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
        elif name == "inv_binomial":
            weight += 1.7
        elif name == "euler":
            weight += 1.7
        elif name == "euler_ogf":
            weight += 2.2
        elif name == "inv_euler_ogf":
            weight += 2.4
        elif name == "stirling1":
            weight += 1.9
        elif name == "stirling2":
            weight += 1.9
        elif name == "inv_stirling1":
            weight += 2.0
        elif name == "inv_stirling2":
            weight += 2.0
        elif name == "ogf_inv":
            weight += 2.5
        elif name == "series_reversion":
            weight += 2.7
        elif name == "rle_len":
            weight += 1.9
        elif name == "mobius":
            weight += 1.7
        elif name in ("omega", "bigomega", "tau", "sigma", "phi", "v2", "lpf", "gpf", "rad", "liouville"):
            weight += 1.3
        elif name == "squarefree":
            weight += 1.1
        elif name.startswith("vp("):
            weight += 1.3
        elif name == "ratio_int":
            weight += 1.2
        elif name in ("index_square", "prime_index", "index_pow2", "index_factorial", "index_triangular", "index_fibonacci"):
            weight += 1.1
        elif name.startswith("index_powk("):
            weight += 1.2
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


def _sign_pattern(values: list[int]) -> str:
    if not values:
        return "empty"
    all_nonneg = all(v >= 0 for v in values)
    all_nonpos = all(v <= 0 for v in values)
    if all_nonneg:
        return "nonneg"
    if all_nonpos:
        return "nonpos"
    alt = all(values[i] == 0 or values[i + 1] == 0 or (values[i] > 0) != (values[i + 1] > 0) for i in range(len(values) - 1))
    if alt:
        return "alternating"
    return "mixed"


def _first_diff_sign(values: list[int]) -> str:
    if len(values) < 2:
        return "na"
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    zero = len(diffs) - pos - neg
    if pos == len(diffs):
        return "pos"
    if neg == len(diffs):
        return "neg"
    if pos > 0 and neg == 0:
        return "nonneg"
    if neg > 0 and pos == 0:
        return "nonpos"
    if zero == len(diffs):
        return "flat"
    return "mixed"


def _invariant_rarity_bonus(values: list[int], stats: dict) -> float:
    """
    Compute a small "rarity" score based on how common the transformed query's
    coarse invariants are across the DB.

    Returns a nonnegative float; larger means rarer.
    """
    total = int(stats.get("total") or 0)
    if total <= 0 or not values:
        return 0.0
    sp = _sign_pattern(values)
    fd = _first_diff_sign(values)
    sp_counts = stats.get("sign_pattern") or {}
    fd_counts = stats.get("first_diff_sign") or {}

    bonus = 0.0
    sp_n = int(sp_counts.get(sp) or 0)
    fd_n = int(fd_counts.get(fd) or 0)
    if sp_n > 0:
        bonus += math.log(total / sp_n)
    if fd_n > 0:
        bonus += math.log(total / fd_n)
    # Average across the two invariants to keep scale stable.
    return bonus / 2.0 if bonus > 0 else 0.0
