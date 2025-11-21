from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .build_index import build_index
from .matcher import match_exact, candidate_sequences
from .ranking import rank_candidates_for_query
from .query import parse_query
from .storage import iter_sequences, iter_sequences_by_prefix
from .transform_search import search_transform_matches
from .transforms import default_transforms


def main(argv=None):
    argv = argv or sys.argv[1:]

    cfg = load_config()
    default_stripped = cfg["paths"]["stripped"]
    default_names = cfg["paths"]["names"]
    default_db = cfg["paths"]["db"]
    default_max_terms = cfg["limits"]["max_terms"]
    default_limit = cfg["limits"]["max_results"]

    parser = argparse.ArgumentParser(prog="oeis", description="Offline OEIS matcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build-index", help="Build SQLite index from OEIS raw exports.")
    p_build.add_argument("--stripped", default=default_stripped, help="Path to stripped.gz")
    p_build.add_argument("--names", default=default_names, help="Path to names.gz")
    p_build.add_argument("--db", default=default_db, help="Output SQLite path")
    p_build.add_argument("--max-terms", type=int, default=default_max_terms, help="Max terms to store per sequence")

    p_match = sub.add_parser("match", help="Match a sequence against OEIS.")
    p_match.add_argument("sequence", help="Comma or space separated integers")
    p_match.add_argument("--db", default=default_db, help="SQLite index path")
    p_match.add_argument("--subsequence", action="store_true", help="Allow subsequence (not just prefix) matches")
    p_match.add_argument("--limit", type=int, default=default_limit, help="Max matches to return")
    p_match.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_match.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_match.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit in text/JSON output")

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
    p_tsearch.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_tsearch.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")

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
    p_analyze.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_analyze.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")
    p_analyze.add_argument("--similar", type=int, default=0, help="Return top N similarity-ranked candidates (scale+offset).")

    args = parser.parse_args(argv)

    if args.cmd == "build-index":
        stats = build_index(Path(args.stripped), Path(args.names), Path(args.db), max_terms=args.max_terms)
        print(f"Inserted {stats['inserted']} sequences into {stats['db']}")
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
        if args.as_json:
            out = [
                {
                    "id": m.id,
                    "name": m.name,
                    "match_type": m.match_type,
                    "offset": m.offset,
                    "length": m.length,
                    **({"terms": m.snippet} if m.snippet is not None else {}),
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
                print(f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{snippet}")
        return 0

    if args.cmd == "tsearch":
        query = parse_query(
            args.sequence,
            min_match_length=args.min_match_length,
            allow_subsequence=args.subsequence,
        )

        scale_vals = _parse_int_list(args.scale_values)
        shift_vals = _parse_int_list(args.shift_values)
        beta_vals = _parse_int_list(args.beta_values)
        decimate_params = _parse_decimate(args.decimate)
        transforms = default_transforms(
            scale_values=scale_vals,
            beta_values=beta_vals,
            shift_values=shift_vals,
            allow_diff=not args.no_diff,
            allow_partial_sum=not args.no_partial_sum,
            allow_abs=not args.no_abs,
            allow_gcd_norm=not args.no_gcd_norm,
            decimate_params=decimate_params,
        )

        matches = search_transform_matches(
            query,
            Path(args.db),
            max_depth=args.max_depth,
            transforms=transforms,
            limit=args.limit,
            snippet_len=args.show_terms,
        )

        if args.as_json:
            out = [
                {
                    "id": m.id,
                    "name": m.name,
                    "match_type": m.match_type,
                    "offset": m.offset,
                    "length": m.length,
                    "transform": m.transform_desc,
                    **({"terms": m.snippet} if m.snippet is not None else {}),
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
                tdesc = f" via {m.transform_desc}" if m.transform_desc else ""
                print(f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{snippet}")
        return 0

    if args.cmd == "analyze":
        query = parse_query(
            args.sequence,
            min_match_length=args.min_match_length,
            allow_subsequence=args.subsequence,
        )
        db_path = Path(args.db)

        # Exact matches
        exact_iter = candidate_sequences(db_path, query)
        exact_matches = match_exact(
            query,
            exact_iter,
            limit=args.limit,
            snippet_len=args.show_terms,
        )

        # Transform matches
        scale_vals = _parse_int_list(args.scale_values)
        shift_vals = _parse_int_list(args.shift_values)
        beta_vals = _parse_int_list(args.beta_values)
        decimate_params = _parse_decimate(args.decimate)
        transforms = default_transforms(
            scale_values=scale_vals,
            beta_values=beta_vals,
            shift_values=shift_vals,
            allow_diff=not args.no_diff,
            allow_partial_sum=not args.no_partial_sum,
            allow_abs=not args.no_abs,
            allow_gcd_norm=not args.no_gcd_norm,
            decimate_params=decimate_params,
        )

        t_matches = search_transform_matches(
            query,
            db_path,
            max_depth=args.max_depth,
            transforms=transforms,
            limit=args.tlimit,
            snippet_len=args.show_terms,
        )

        sim_matches = []
        if args.similar and args.similar > 0:
            sim_matches = rank_candidates_for_query(query, db_path, top_k=args.similar)

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
                if m.snippet is not None:
                    row["terms"] = m.snippet
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
            }
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
                tdesc = f" via {m.transform_desc}" if m.transform_desc else ""
                score = f" score={m.score:.2f}" if m.score is not None else ""
                print(f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{score}{snippet}")

            if sim_matches:
                print("\nSimilarity candidates:")
                for c in sim_matches:
                    print(
                        f"  {c.record.id} corr={c.corr:.3f} mse={c.mse:.3g} scale={c.scale:.3g} offset={c.offset:.3g} - {c.record.name}"
                    )
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


if __name__ == "__main__":
    raise SystemExit(main())
