from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PRESETS = {
    "fast": {
        "max_depth": 1,
        "limit": 5,
        "tlimit": 5,
        "scale_values": "-2,-1,2",
        "shift_values": "1",
        "beta_values": "",
        "decimate": "",
        "extra_transforms": "",
        "similar": 0,
        "combos": 0,
        "combo_candidates": 20,
        "combo_coeffs": "-2,-1,1,2",
        "combo_max_shift": 0,
        "combo_max_checks": 100000,
        "combo_max_time": 0.8,
        "triples": 0,
        "triple_candidates": 15,
        "triple_max_checks": 120000,
        "triple_max_time": 0.8,
    },
    "deep": {
        "max_depth": 2,
        "limit": 15,
        "tlimit": 60,
        "scale_values": "-4,-3,-2,-1,2,3,4",
        "shift_values": "1,2,3",
        "beta_values": "-2,-1,1,2",
        "decimate": "2,3:1",
        "extra_transforms": "diff2,cumprod,reverse,evenodd,movsum2",
        "similar": 10,
        "combos": 10,
        "combo_candidates": 60,
        "combo_coeffs": "-3,-2,-1,1,2,3",
        "combo_max_shift": 2,
        "combo_max_checks": 400000,
        "combo_max_time": 3.0,
        "triples": 4,
        "triple_candidates": 30,
        "triple_max_checks": 350000,
        "triple_max_time": 3.0,
    },
    "max": {
        # “Find all the things”: wide transform search + combos/triples, generous caps and ~10 min timeouts.
        "max_depth": 2,
        "limit": 25,
        "tlimit": 80,
        "scale_values": "-5,-4,-3,-2,-1,2,3,4,5",
        "shift_values": "1,2,3,4",
        "beta_values": "-3,-2,-1,1,2,3",
        "decimate": "2,3:1,4:1",
        "extra_transforms": "diff2,cumprod,reverse,evenodd,movsum2",
        "similar": 20,
        "combos": 20,
        "combo_candidates": 250,
        "combo_coeffs": "-5,-4,-3,-2,-1,1,2,3,4,5",
        "combo_max_shift": 3,
        "combo_max_checks": 2_000_000,
        "combo_max_time": 600.0,
        "triples": 10,
        "triple_candidates": 200,
        "triple_max_checks": 2_000_000,
        "triple_max_time": 600.0,
    },
}


def _apply_preset(args, preset_name: str):
    preset = PRESETS.get(preset_name)
    if not preset:
        return args
    for key, val in preset.items():
        if hasattr(args, key):
            setattr(args, key, val)
    return args


def _choose_snippet_len(query_terms: list[int | None], show_terms: int | None) -> int | None:
    if show_terms is not None:
        return show_terms
    if not query_terms:
        return None
    return min(len(query_terms), 20)


def _fmt_terms(terms: list[int] | None, limit: int = 20) -> str:
    if not terms:
        return ""
    clipped = terms[:limit]
    txt = ",".join(str(t) for t in clipped)
    if len(terms) > limit:
        txt += ",…"
    return txt

from .combination_search import search_two_sequence_combinations, search_three_sequence_combinations, resolve_component_transforms
from .config import load_config
from .build_index import build_index
from .matcher import match_exact, candidate_sequences
from .ranking import rank_candidates_for_query
from .candidates import get_candidate_bucket
from .query import parse_query
from .transform_search import search_transform_matches
from .transforms import default_transforms
from .sync import DEFAULT_NAMES_URL, DEFAULT_OEISDATA_REPO, DEFAULT_STRIPPED_URL, sync_data


def main(argv=None):
    argv = argv or sys.argv[1:]

    cfg = load_config()
    default_stripped = cfg["paths"]["stripped"]
    default_names = cfg["paths"]["names"]
    default_keywords = cfg["paths"]["keywords"]
    default_db = cfg["paths"]["db"]
    default_max_terms = cfg["limits"]["max_terms"]
    default_limit = cfg["limits"]["max_results"]

    parser = argparse.ArgumentParser(prog="oeis", description="Offline OEIS matcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build-index", help="Build SQLite index from OEIS raw exports.")
    p_build.add_argument("--stripped", default=default_stripped, help="Path to stripped.gz")
    p_build.add_argument("--names", default=default_names, help="Path to names.gz")
    p_build.add_argument("--keywords", default=default_keywords, help="Path to keywords file (optional)")
    p_build.add_argument("--db", default=default_db, help="Output SQLite path")
    p_build.add_argument("--oeisdata", default="data/raw/oeisdata", help="Optional path to oeisdata clone for keywords/metadata")
    p_build.add_argument("--max-terms", type=int, default=default_max_terms, help="Max terms to store per sequence")

    p_sync = sub.add_parser("sync", help="Download OEIS exports into data/raw.")
    p_sync.add_argument("--stripped-url", default=DEFAULT_STRIPPED_URL, help="URL for stripped.gz")
    p_sync.add_argument("--names-url", default=DEFAULT_NAMES_URL, help="URL for names.gz")
    p_sync.add_argument("--keywords-url", default="", help="Optional URL for keywords file")
    p_sync.add_argument("--stripped", default=default_stripped, help="Destination path for stripped.gz")
    p_sync.add_argument("--names", default=default_names, help="Destination path for names.gz")
    p_sync.add_argument("--keywords", default=default_keywords, help="Destination path for keywords (if downloaded)")
    p_sync.add_argument("--force", action="store_true", help="Re-download even if files already exist")
    p_sync.add_argument("--clone-oeisdata", action="store_true", help="Also clone oeisdata mirror for metadata/keywords")
    p_sync.add_argument("--oeisdata-url", default=DEFAULT_OEISDATA_REPO, help="Repo URL for oeisdata clone")
    p_sync.add_argument("--oeisdata", default="data/raw/oeisdata", help="Destination path for oeisdata clone")

    p_match = sub.add_parser("match", help="Match a sequence against OEIS.")
    p_match.add_argument("sequence", help="Comma or space separated integers")
    p_match.add_argument("--db", default=default_db, help="SQLite index path")
    p_match.add_argument("--subsequence", action="store_true", help="Allow subsequence (not just prefix) matches")
    p_match.add_argument("--limit", type=int, default=default_limit, help="Max matches to return")
    p_match.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_match.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_match.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit in text/JSON output")
    p_match.add_argument("--similar", type=int, default=0, help="Also show top N similarity candidates (scale+offset).")
    p_match.add_argument("--no-subsequence-fallback", action="store_true", help="Do not auto-try subsequence if no prefix hit")

    p_tsearch = sub.add_parser("tsearch", help="Transform-based search for sequence matches.")
    p_tsearch.add_argument("sequence", help="Comma or space separated integers")
    p_tsearch.add_argument("--db", default=default_db, help="SQLite index path")
    p_tsearch.add_argument("--subsequence", action="store_true", help="Allow subsequence matches")
    p_tsearch.add_argument("--limit", type=int, default=default_limit, help="Max matches to return")
    p_tsearch.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_tsearch.add_argument("--max-depth", type=int, default=2, help="Max transform chain depth")
    p_tsearch.add_argument("--scale-values", default="-3,-2,-1,2,3", help="Comma-separated scale factors (exclude 0,1)")
    p_tsearch.add_argument("--shift-values", default="1,2", help="Comma-separated forward shifts (drop first k terms)")
    p_tsearch.add_argument("--beta-values", default="", help="Comma-separated additive constants for affine transforms")
    p_tsearch.add_argument("--decimate", default="", help="Comma-separated decimation params c or c:d (e.g., 2 or 3:1)")
    p_tsearch.add_argument("--no-diff", action="store_true", help="Disable difference transform")
    p_tsearch.add_argument("--no-partial-sum", action="store_true", help="Disable partial sum transform")
    p_tsearch.add_argument("--no-abs", action="store_true", help="Disable abs transform")
    p_tsearch.add_argument("--no-gcd-norm", action="store_true", help="Disable gcd normalization transform")
    p_tsearch.add_argument("--extra-transforms", default="", help="Comma list: diff2,cumprod,popcount,digitsum,reverse,evenodd,movsum2")
    p_tsearch.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_tsearch.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")
    p_tsearch.add_argument("--preset", choices=list(PRESETS.keys()), help="Preset for search depth/limits (fast|deep)")

    p_combo = sub.add_parser("combo", help="Search integer linear combinations of two sequences.")
    p_combo.add_argument("sequence", help="Comma or space separated integers")
    p_combo.add_argument("--db", default=default_db, help="SQLite index path")
    p_combo.add_argument("--coeffs", default="-3,-2,-1,1,2,3", help="Comma-separated integer coefficients to try")
    p_combo.add_argument("--max-shift", type=int, default=0, help="Maximum forward shift (drop first k terms)")
    p_combo.add_argument("--max-shift-back", type=int, default=0, help="Maximum backward shift (negative indices)")
    p_combo.add_argument("--limit", type=int, default=default_limit, help="Max combination matches to return")
    p_combo.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_combo.add_argument("--candidates", type=int, default=40, help="Max candidate sequences to consider")
    p_combo.add_argument("--max-checks", type=int, default=200_000, help="Max coefficient/shift combinations to evaluate")
    p_combo.add_argument("--max-time", type=float, default=None, help="Max wall time (seconds) for combo search")
    p_combo.add_argument("--max-combinations", type=int, default=None, help="Max combination evaluations to attempt (pairs)")
    p_combo.add_argument("--triples", type=int, default=0, help="Return up to N three-sequence combinations")
    p_combo.add_argument("--triple-candidates", type=int, default=25, help="Max candidates for triple search")
    p_combo.add_argument("--triple-max-checks", type=int, default=300_000, help="Max evaluations for triple search")
    p_combo.add_argument("--triple-max-time", type=float, default=None, help="Max wall time (seconds) for triple search")
    p_combo.add_argument("--triple-max-combinations", type=int, default=None, help="Max combination evaluations to attempt (triples)")
    p_combo.add_argument("--component-transforms", default="id", help="Comma-separated per-sequence transforms: id,diff,partial_sum")
    p_combo.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_combo.add_argument("--combo-unfiltered", action="store_true", help="Skip prefix index when building combo candidate pool (use invariant/length filter instead)")

    p_analyze = sub.add_parser("analyze", help="Run exact + transform search pipeline.")
    p_analyze.add_argument("sequence", help="Comma or space separated integers")
    p_analyze.add_argument("--db", default=default_db, help="SQLite index path")
    p_analyze.add_argument("--subsequence", action="store_true", help="Allow subsequence matches")
    p_analyze.add_argument("--limit", type=int, default=default_limit, help="Max exact matches")
    p_analyze.add_argument("--tlimit", type=int, default=default_limit, help="Max transform matches")
    p_analyze.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_analyze.add_argument("--max-depth", type=int, default=2, help="Max transform chain depth")
    p_analyze.add_argument("--scale-values", default="-3,-2,-1,2,3", help="Comma-separated scale factors (exclude 0,1)")
    p_analyze.add_argument("--beta-values", default="", help="Comma-separated additive constants for affine transforms")
    p_analyze.add_argument("--shift-values", default="1,2", help="Comma-separated forward shifts (drop first k terms)")
    p_analyze.add_argument("--decimate", default="", help="Comma-separated decimation params c or c:d")
    p_analyze.add_argument("--no-diff", action="store_true", help="Disable difference transform")
    p_analyze.add_argument("--no-partial-sum", action="store_true", help="Disable partial sum transform")
    p_analyze.add_argument("--no-abs", action="store_true", help="Disable abs transform")
    p_analyze.add_argument("--no-gcd-norm", action="store_true", help="Disable gcd normalization transform")
    p_analyze.add_argument("--extra-transforms", default="", help="Comma list: diff2,cumprod,popcount,digitsum,reverse,evenodd,movsum2")
    p_analyze.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_analyze.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")
    p_analyze.add_argument("--similar", type=int, default=0, help="Return top N similarity-ranked candidates (scale+offset).")
    p_analyze.add_argument("--combos", type=int, default=0, help="Return up to N two-sequence combinations (experimental)")
    p_analyze.add_argument("--combo-candidates", type=int, default=40, help="Max candidate sequences to consider for combos")
    p_analyze.add_argument("--combo-coeffs", default="-3,-2,-1,1,2,3", help="Comma-separated integer coefficients to try in combos")
    p_analyze.add_argument("--combo-max-shift", type=int, default=0, help="Maximum forward shift for combo search")
    p_analyze.add_argument("--combo-max-shift-back", type=int, default=0, help="Maximum backward shift for combo search")
    p_analyze.add_argument("--combo-max-checks", type=int, default=200_000, help="Max coefficient/shift combinations to evaluate for combos")
    p_analyze.add_argument("--combo-max-time", type=float, default=None, help="Max wall time (seconds) for combo search")
    p_analyze.add_argument("--combo-max-combinations", type=int, default=None, help="Max combination evaluations (pairs)")
    p_analyze.add_argument("--combo-component-transforms", default="id", help="Per-sequence transforms for combos: id,diff,partial_sum")
    p_analyze.add_argument("--triples", type=int, default=0, help="Return up to N three-sequence combinations (experimental, slow)")
    p_analyze.add_argument("--triple-candidates", type=int, default=25, help="Max candidate sequences to consider for triple combos")
    p_analyze.add_argument("--triple-max-checks", type=int, default=300_000, help="Max evaluations for triple combos")
    p_analyze.add_argument("--triple-max-time", type=float, default=None, help="Max wall time (seconds) for triple combos")
    p_analyze.add_argument("--triple-max-combinations", type=int, default=None, help="Max combination evaluations (triples)")
    p_analyze.add_argument("--combo-unfiltered", action="store_true", help="Skip prefix index when building combo candidate pool (use invariant/length filter instead)")
    p_analyze.add_argument("--no-subsequence-fallback", action="store_true", help="Do not auto-try subsequence if no prefix hit")
    p_analyze.add_argument("--preset", choices=list(PRESETS.keys()), help="Preset for search depth/limits (fast|deep)")
    p_analyze.add_argument("--timings", action="store_true", help="Include per-stage timing diagnostics")

    args = parser.parse_args(argv)

    if args.cmd == "build-index":
        stats = build_index(
            Path(args.stripped),
            Path(args.names),
            Path(args.keywords),
            Path(args.db),
            max_terms=args.max_terms,
            oeisdata_root=Path(args.oeisdata),
        )
        print(f"Inserted {stats['inserted']} sequences into {stats['db']}")
        return 0

    if args.cmd == "sync":
        stats = sync_data(
            stripped_url=args.stripped_url,
            names_url=args.names_url,
            keywords_url=args.keywords_url or None,
            stripped_path=Path(args.stripped),
            names_path=Path(args.names),
            keywords_path=Path(args.keywords),
            force=args.force,
            clone_oeisdata=args.clone_oeisdata,
            oeisdata_path=Path(args.oeisdata),
            oeisdata_url=args.oeisdata_url,
        )
        for label in ("stripped", "names", "keywords", "oeisdata"):
            if label in stats:
                s = stats[label]
                size = f" ({s.get('bytes', 0)} bytes)" if "bytes" in s else ""
                print(f"{label}: {s['status']}{size} -> {s['path']}")
        print("Note: OEIS data is CC BY-SA 4.0; include attribution when redistributing.")
        return 0

    if args.cmd == "match":
        query = parse_query(
            args.sequence,
            min_match_length=args.min_match_length,
            allow_subsequence=args.subsequence,
        )
        db_path = Path(args.db)
        seq_iter = candidate_sequences(db_path, query)
        matches = match_exact(query, seq_iter, limit=args.limit, snippet_len=args.show_terms)
        fallback_used = False
        if not matches and not args.subsequence and not args.no_subsequence_fallback:
            fq = parse_query(
                args.sequence,
                min_match_length=args.min_match_length,
                allow_subsequence=True,
            )
            seq_iter = candidate_sequences(db_path, fq)
            matches = match_exact(fq, seq_iter, limit=args.limit, snippet_len=args.show_terms)
            fallback_used = True
        sim_matches = rank_candidates_for_query(query, db_path, top_k=args.similar) if args.similar else []
        if args.as_json:
            out = [
                {
                    "id": m.id,
                    "name": m.name,
                    "match_type": m.match_type,
                    "offset": m.offset,
                    "length": m.length,
                    **({"terms": m.snippet} if m.snippet is not None else {}),
                    **({"score": m.score} if m.score is not None else {}),
                }
                for m in matches
            ]
            sim = [
                {
                    "id": c.record.id,
                    "name": c.record.name,
                    "corr": c.corr,
                    "mse": c.mse,
                    "scale": c.scale,
                    "offset": c.offset,
                }
                for c in sim_matches
            ]
            payload = {"query": query.terms, "matches": out, "similarity": sim}
            if fallback_used:
                payload["diagnostics"] = {"subsequence_fallback": True}
            print(json.dumps(payload, indent=2))
        else:
            if not matches:
                print("No matches found.")
            for m in matches:
                name = f" - {m.name}" if m.name else ""
                snippet = ""
                if m.snippet is not None:
                    snippet = " terms=" + ",".join(str(t) for t in m.snippet)
                score = f" score={m.score:.2f}" if m.score is not None else ""
                print(f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{score}{snippet}")
            if sim_matches:
                print("\nSimilarity candidates:")
                for c in sim_matches:
                    print(
                        f"  {c.record.id} corr={c.corr:.3f} mse={c.mse:.3g} scale={c.scale:.3g} offset={c.offset:.3g} - {c.record.name}"
                    )
            if fallback_used and not matches:
                print("\n(Fell back to subsequence search)")
        return 0

    if args.cmd == "tsearch":
        if args.preset:
            args = _apply_preset(args, args.preset)

        query = parse_query(
            args.sequence,
            min_match_length=args.min_match_length,
            allow_subsequence=args.subsequence,
        )

        scale_vals = _parse_int_list(args.scale_values)
        shift_vals = _parse_int_list(args.shift_values)
        beta_vals = _parse_int_list(args.beta_values)
        decimate_params = _parse_decimate(args.decimate)
        extras = _parse_extra_transforms(args.extra_transforms)
        transforms = default_transforms(
            scale_values=scale_vals,
            beta_values=beta_vals,
            shift_values=shift_vals,
            allow_diff=not args.no_diff,
            diff_orders=(1, 2) if (not args.no_diff and extras["diff2"]) else (1,),
            allow_partial_sum=not args.no_partial_sum,
            allow_cumprod=extras["cumprod"],
            allow_abs=not args.no_abs,
            allow_gcd_norm=not args.no_gcd_norm,
            decimate_params=decimate_params,
            allow_reverse=extras["reverse"],
            allow_even_odd=extras["evenodd"],
            moving_sum_windows=(2,) if extras["movsum2"] else (),
            allow_popcount=extras["popcount"],
            allow_digit_sum=extras["digitsum"],
        )

        snip = _choose_snippet_len(query.terms, args.show_terms)
        if args.limit and args.limit > 0:
            matches = search_transform_matches(
                query,
                Path(args.db),
                max_depth=args.max_depth,
                transforms=transforms,
                limit=args.limit,
                snippet_len=snip,
                full_scan=args.preset == "deep",
            )
        else:
            matches = []

        if args.as_json:
            out = [
                {
                    "id": m.id,
                    "name": m.name,
                    "match_type": m.match_type,
                    "offset": m.offset,
                    "length": m.length,
                    "transform": m.transform_desc,
                    **({"explanation": m.explanation} if m.explanation else {}),
                    **({"latex": m.latex} if m.latex else {}),
                    **({"terms": m.snippet} if m.snippet is not None else {}),
                    **({"transformed_terms": m.transformed_terms} if m.transformed_terms is not None else {}),
                }
                for m in matches
            ]
            print(json.dumps({"query": query.terms, "matches": out}, indent=2))
        else:
            if not matches:
                print("No matches found.")
            for m in matches:
                name = f" - {m.name}" if m.name else ""
                snippet = ""
                if m.snippet is not None:
                    snippet = " terms=" + ",".join(str(t) for t in m.snippet)
                if m.transformed_terms is not None:
                    snippet += " transformed=" + ",".join(str(t) for t in m.transformed_terms)
                expl = m.explanation or m.transform_desc or ""
                tdesc = f" via {expl}" if expl else ""
                print(f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{snippet}")
        return 0

    if args.cmd == "combo":
        query = parse_query(
            args.sequence,
            min_match_length=args.min_match_length,
            allow_subsequence=False,
        )
        db_path = Path(args.db)
        coeffs = _parse_int_list(args.coeffs)
        triple_candidates = args.triple_candidates or args.candidates
        cap = max(args.candidates, triple_candidates)
        bucket = get_candidate_bucket(
            query,
            db_path,
            exact_limit=cap,
            similar_limit=cap,
            max_records=cap,
            fill_unfiltered=True,
            skip_prefix_filter=args.combo_unfiltered,
        )
        comp_transforms = resolve_component_transforms(_parse_transform_names(args.component_transforms))
        snip = _choose_snippet_len(query.terms, args.show_terms)
        combos = search_two_sequence_combinations(
            query,
            bucket.records,
            coeffs=coeffs,
            max_shift=args.max_shift,
            max_shift_back=args.max_shift_back,
            limit=args.limit,
            max_candidates=args.candidates,
            max_checks=args.max_checks,
            max_time_s=args.max_time,
            max_combinations=args.max_combinations,
            component_transforms=comp_transforms,
            snippet_len=snip,
        )
        triples = []
        if args.triples:
            triples = search_three_sequence_combinations(
                query,
                bucket.records,
                coeffs=coeffs,
                max_shift=args.max_shift,
                max_shift_back=args.max_shift_back,
                limit=args.triples,
                max_candidates=triple_candidates,
                max_checks=args.triple_max_checks,
                max_time_s=args.triple_max_time,
                max_combinations=args.triple_max_combinations,
                component_transforms=comp_transforms,
                snippet_len=snip,
            )
        if args.as_json:
            out = [
                {
                    "ids": list(m.ids),
                    "names": list(m.names),
                    "coeffs": list(m.coeffs),
                    "shifts": list(m.shifts),
                    "length": m.length,
                    "score": m.score,
                    "expression": m.expression,
                    **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                    **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                    **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                }
                for m in combos
            ]
            out3 = [
                {
                    "ids": list(m.ids),
                    "names": list(m.names),
                    "coeffs": list(m.coeffs),
                    "shifts": list(m.shifts),
                    "length": m.length,
                    "score": m.score,
                    "expression": m.expression,
                    **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                    **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                    **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                }
                for m in triples
            ]
            print(json.dumps({"query": query.terms, "combinations": out, "triple_combinations": out3}, indent=2))
        else:
            if not combos:
                print("No combinations found.")
            for m in combos:
                n1 = f" - {m.names[0]}" if m.names[0] else ""
                n2 = f" - {m.names[1]}" if m.names[1] else ""
                extra = ""
                if m.component_terms:
                    t1 = _fmt_terms(m.component_terms[0])
                    t2 = _fmt_terms(m.component_terms[1])
                    extra = f" terms1={t1} terms2={t2}"
                if m.combined_terms:
                    extra += f" result={_fmt_terms(m.combined_terms)}"
                print(f"{m.expression} len={m.length} score={m.score:.2f} [{m.ids[0]}{n1}; {m.ids[1]}{n2}]{extra}")
            if triples:
                print("\nTriple combinations:")
                for m in triples:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = " " + " ".join(f"terms{i+1}={_fmt_terms(ts)}" for i, ts in enumerate(m.component_terms))
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"{m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
        return 0

    if args.cmd == "analyze":
        if args.preset:
            args = _apply_preset(args, args.preset)

        import time
        timings: dict[str, float] = {}
        t_start = time.perf_counter()

        query = parse_query(
            args.sequence,
            min_match_length=args.min_match_length,
            allow_subsequence=args.subsequence,
        )
        db_path = Path(args.db)

        # Exact matches (with optional fallback to subsequence)
        t0 = time.perf_counter()
        exact_iter = candidate_sequences(db_path, query)
        exact_matches = match_exact(query, exact_iter, limit=args.limit, snippet_len=args.show_terms)
        fallback_used = False
        if not exact_matches and not args.subsequence and not args.no_subsequence_fallback:
            fb_query = parse_query(
                args.sequence,
                min_match_length=args.min_match_length,
                allow_subsequence=True,
            )
            exact_iter = candidate_sequences(db_path, fb_query)
            exact_matches = match_exact(fb_query, exact_iter, limit=args.limit, snippet_len=args.show_terms)
            fallback_used = True
        if args.timings:
            timings["exact_ms"] = 1000 * (time.perf_counter() - t0)

        # Transform matches
        scale_vals = _parse_int_list(args.scale_values)
        shift_vals = _parse_int_list(args.shift_values)
        beta_vals = _parse_int_list(args.beta_values)
        decimate_params = _parse_decimate(args.decimate)
        extras = _parse_extra_transforms(args.extra_transforms)
        transforms = default_transforms(
            scale_values=scale_vals,
            beta_values=beta_vals,
            shift_values=shift_vals,
            allow_diff=not args.no_diff,
            diff_orders=(1, 2) if (not args.no_diff and extras["diff2"]) else (1,),
            allow_partial_sum=not args.no_partial_sum,
            allow_cumprod=extras["cumprod"],
            allow_abs=not args.no_abs,
            allow_gcd_norm=not args.no_gcd_norm,
            decimate_params=decimate_params,
            allow_reverse=extras["reverse"],
            allow_even_odd=extras["evenodd"],
            moving_sum_windows=(2,) if extras["movsum2"] else (),
            allow_popcount=extras["popcount"],
            allow_digit_sum=extras["digitsum"],
        )

        combo_snip = _choose_snippet_len(query.terms, args.show_terms)
        if args.tlimit and args.tlimit > 0:
            t_matches = search_transform_matches(
                query,
                db_path,
                max_depth=args.max_depth,
                transforms=transforms,
                limit=args.tlimit,
                snippet_len=combo_snip,
                full_scan=args.preset in ("deep", "max"),
            )
        else:
            t_matches = []
        t1 = time.perf_counter()
        if args.timings:
            timings["transform_ms"] = 1000 * (t1 - t0) - timings.get("exact_ms", 0.0)

        sim_matches = rank_candidates_for_query(query, db_path, top_k=args.similar) if args.similar else []
        t2 = time.perf_counter()
        if args.timings and args.similar:
            timings["similarity_ms"] = 1000 * (t2 - t1)
        combo_matches = []
        triple_matches: list = []
        if args.combos or args.triples:
            combo_coeffs = _parse_int_list(args.combo_coeffs)
            triple_candidates = args.triple_candidates or args.combo_candidates
            cap = max(args.combo_candidates, triple_candidates)
            comp_transforms = resolve_component_transforms(_parse_transform_names(args.combo_component_transforms))
            combo_snip = _choose_snippet_len(query.terms, args.show_terms)
            bucket = get_candidate_bucket(
                query,
                db_path,
                exact_limit=cap,
                similar_limit=cap,
                max_records=cap,
                fill_unfiltered=True,
                skip_prefix_filter=args.combo_unfiltered,
            )

            if args.combos:
                combo_start = time.perf_counter()
                combo_matches = search_two_sequence_combinations(
                    query,
                    bucket.records,
                    coeffs=combo_coeffs,
                    max_shift=args.combo_max_shift,
                    max_shift_back=args.combo_max_shift_back,
                    limit=args.combos,
                    max_candidates=args.combo_candidates,
                    max_checks=args.combo_max_checks,
                    max_time_s=args.combo_max_time,
                    max_combinations=args.combo_max_combinations,
                    component_transforms=comp_transforms,
                    snippet_len=combo_snip,
                )
                combo_end = time.perf_counter()
            else:
                combo_start = combo_end = None

            if args.triples:
                triple_start = time.perf_counter()
                triple_matches = search_three_sequence_combinations(
                    query,
                    bucket.records,
                    coeffs=combo_coeffs,
                    max_shift=args.combo_max_shift,
                    max_shift_back=args.combo_max_shift_back,
                    limit=args.triples,
                    max_candidates=triple_candidates,
                    max_checks=args.triple_max_checks,
                    max_time_s=args.triple_max_time,
                    max_combinations=args.triple_max_combinations,
                    component_transforms=comp_transforms,
                    snippet_len=combo_snip,
                )
                triple_end = time.perf_counter()
            else:
                triple_start = triple_end = None

            if args.timings:
                if combo_start is not None and combo_end is not None:
                    timings["combination_ms"] = 1000 * (combo_end - combo_start)
                if triple_start is not None and triple_end is not None:
                    timings["triple_ms"] = 1000 * (triple_end - triple_start)

        if args.as_json:
            def _mrow(m):
                row = {
                    "id": m.id,
                    "name": m.name,
                    "match_type": m.match_type,
                    "offset": m.offset,
                    "length": m.length,
                    "score": m.score,
                }
                if m.transform_desc:
                    row["transform"] = m.transform_desc
                if m.explanation:
                    row["explanation"] = m.explanation
                if m.latex:
                    row["latex"] = m.latex
                if m.snippet is not None:
                    row["terms"] = m.snippet
                if m.transformed_terms is not None:
                    row["transformed_terms"] = m.transformed_terms
                return row

            payload = {
                "query": query.terms,
                "exact_matches": [_mrow(m) for m in exact_matches],
                "transform_matches": [_mrow(m) for m in t_matches],
                "similarity": [
                    {
                        "id": c.record.id,
                        "name": c.record.name,
                        "corr": c.corr,
                        "mse": c.mse,
                        "scale": c.scale,
                        "offset": c.offset,
                    }
                    for c in sim_matches
                ],
                "combinations": [
                    {
                        "ids": list(m.ids),
                        "names": list(m.names),
                        "coeffs": list(m.coeffs),
                        "shifts": list(m.shifts),
                        "length": m.length,
                        "score": m.score,
                        "expression": m.expression,
                        **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                        **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                        **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                    }
                    for m in combo_matches
                ],
                "triple_combinations": [
                    {
                        "ids": list(m.ids),
                        "names": list(m.names),
                        "coeffs": list(m.coeffs),
                        "shifts": list(m.shifts),
                        "length": m.length,
                        "score": m.score,
                        "expression": m.expression,
                        **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                        **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                        **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                    }
                    for m in triple_matches
                ],
            }
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                payload["diagnostics"] = {"timings_ms": timings}
            print(json.dumps(payload, indent=2))
        else:
            print("Exact matches:")
            if not exact_matches:
                print("  (none)")
            for m in exact_matches:
                name = f" - {m.name}" if m.name else ""
                snippet = f" terms={','.join(str(t) for t in m.snippet)}" if m.snippet else ""
                score = f" score={m.score:.2f}" if m.score is not None else ""
                print(f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{score}{snippet}")

            print("\nTransform matches:")
            if not t_matches:
                print("  (none)")
            for m in t_matches:
                name = f" - {m.name}" if m.name else ""
                snippet = f" terms={','.join(str(t) for t in m.snippet)}" if m.snippet else ""
                if m.transformed_terms:
                    snippet += f" transformed={','.join(str(t) for t in m.transformed_terms)}"
                expl = m.explanation or m.transform_desc or ""
                tdesc = f" via {expl}" if expl else ""
                score = f" score={m.score:.2f}" if m.score is not None else ""
                print(f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{score}{snippet}")

            if sim_matches:
                print("\nSimilarity candidates:")
                for c in sim_matches:
                    print(
                        f"  {c.record.id} corr={c.corr:.3f} mse={c.mse:.3g} scale={c.scale:.3g} offset={c.offset:.3g} - {c.record.name}"
                    )
            if combo_matches:
                print("\nCombination matches:")
                for m in combo_matches:
                    n1 = f" - {m.names[0]}" if m.names[0] else ""
                    n2 = f" - {m.names[1]}" if m.names[1] else ""
                    extra = ""
                    if m.component_terms:
                        extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(
                        f"  {m.expression} len={m.length} score={m.score:.2f} [{m.ids[0]}{n1}; {m.ids[1]}{n2}]{extra}"
                    )
            if triple_matches:
                print("\nTriple combination matches:")
                for m in triple_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = " " + " ".join(f"terms{i+1}={_fmt_terms(ts)}" for i, ts in enumerate(m.component_terms))
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"  {m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                print("\nTimings (ms):")
                for k, v in timings.items():
                    print(f"  {k}: {v:.1f}")
        return 0

    return 1


def _parse_int_list(text: str) -> list[int]:
    parts = [p.strip() for p in text.split(",")]
    out = []
    for p in parts:
        if p == "":
            continue
        try:
            out.append(int(p))
        except ValueError:
            continue
    return out


def _parse_decimate(text: str) -> list[tuple[int, int]]:
    if not text:
        return []
    out: list[tuple[int, int]] = []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    for p in parts:
        if ":" in p:
            c_str, d_str = p.split(":", 1)
            try:
                c = int(c_str)
                d = int(d_str)
                out.append((c, d))
            except ValueError:
                continue
        else:
            try:
                c = int(p)
                out.append((c, 0))
            except ValueError:
                continue
    return out


def _parse_transform_names(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


def _parse_extra_transforms(text: str) -> dict:
    names = {s.strip().lower() for s in text.split(",") if s.strip()}
    return {
        "diff2": "diff2" in names,
        "cumprod": "cumprod" in names,
        "popcount": "popcount" in names,
        "digitsum": "digitsum" in names,
        "reverse": "reverse" in names,
        "evenodd": "evenodd" in names,
        "movsum2": "movsum2" in names,
    }


if __name__ == "__main__":
    raise SystemExit(main())
