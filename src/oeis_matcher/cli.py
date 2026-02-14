from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import math

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
        "transform_min_score": 0.0,
        "transform_max_complexity": None,
        "combo_candidates": 20,
        "combo_coeffs": "-2,-1,1,2",
        "combo_max_shift": 0,
        "combo_max_checks": 100000,
        "combo_max_time": 2.0,
        "transform_max_time": 2.0,
        "total_max_time": 10.0,
        # combo subcommand aliases
        "coeffs": "-2,-1,1,2",
        "candidates": 20,
        "max_shift": 0,
        "max_shift_back": 0,
        "max_checks": 100000,
        "max_time": 2.0,
        "triples": 0,
        "triple_candidates": 15,
        "triple_max_checks": 120000,
        "triple_max_time": 2.0,
        "combo_unfiltered": False,
        "combo_expanded": False,
        "combo_expanded_max_time": 0.0,
        "combo_expanded_anchors": 0,
        "modclass": 0,
        "modclass_moduli": "2,3",
        "modclass_max_time": 0.0,
        # combo subcommand expanded triple/pair fallback
        "expanded": False,
        "expanded_max_time": 0.0,
        "expanded_anchors": 0,
        "stream": False,
    },
    "deep": {
        "max_depth": 2,
        "limit": 15,
        "tlimit": 60,
        "scale_values": "-4,-3,-2,-1,2,3,4",
        "shift_values": "1,2,3",
        "beta_values": "-1,1",
        "decimate": "2,3:1",
        "extra_transforms": "diff2,cumprod,reverse,evenodd,movsum2,binomial,movsum3",
        "similar": 10,
        "combos": 10,
        "transform_min_score": 0.6,
        "transform_max_complexity": 5.5,
        "combo_candidates": 60,
        "combo_coeffs": "-3,-2,-1,1,2,3",
        "combo_max_shift": 2,
        "combo_max_checks": 400000,
        "combo_max_time": 30.0,
        "transform_max_time": 30.0,
        "total_max_time": 120.0,
        # combo subcommand aliases
        "coeffs": "-3,-2,-1,1,2,3",
        "candidates": 60,
        "max_shift": 2,
        "max_shift_back": 0,
        "max_checks": 400000,
        "max_time": 30.0,
        "triples": 4,
        "triple_candidates": 30,
        "triple_max_checks": 350000,
        "triple_max_time": 30.0,
        "combo_unfiltered": False,
        "combo_expanded": False,
        "combo_expanded_max_time": 0.0,
        "combo_expanded_anchors": 0,
        "modclass": 0,
        "modclass_moduli": "2,3",
        "modclass_max_time": 0.0,
        # combo subcommand expanded triple/pair fallback
        "expanded": False,
        "expanded_max_time": 0.0,
        "expanded_anchors": 0,
        "stream": False,
    },
    "max": {
        # “Find all the things”: wide transform search + combos/triples, generous caps and long timeouts.
        "max_depth": 2,
        "limit": 25,
        "tlimit": 80,
        "scale_values": "-5,-4,-3,-2,-1,2,3,4,5",
        "shift_values": "-1,1,2,3,4",
        "beta_values": "-3,-2,-1,1,2,3",
        "decimate": "2,3:1,4:1",
        "extra_transforms": "diff2,cumprod,reverse,evenodd,movsum2,movsum3,movsum4,binomial,euler,mobius,digitsum10,popcount,mod2,xorindex,rle,rledec,concat,log2,loge,exp2,omega,bigomega,tau,sigma,phi,v2,indexsquare,primeindex,indexpow2,indexfactorial",
        "similar": 20,
        "combos": 20,
        "transform_min_score": 0.8,
        "transform_max_complexity": 7.0,
        "combo_candidates": 250,
        "combo_coeffs": "-5,-4,-3,-2,-1,1,2,3,4,5",
        "combo_max_shift": 5,
        # Allow a small amount of backward shift for combo discovery (enables
        # identities like Lucas from shifted Fibonacci without exploding search).
        "combo_max_shift_back": 1,
        "combo_max_checks": 2_000_000,
        "combo_max_time": 1800.0,
        "transform_max_time": 1800.0,
        "total_max_time": 3600.0,
        # combo subcommand aliases
        "coeffs": "-5,-4,-3,-2,-1,1,2,3,4,5",
        "candidates": 250,
        "max_shift": 5,
        "max_shift_back": 1,
        "max_checks": 2_000_000,
        "max_time": 1800.0,
        "triples": 10,
        "triple_candidates": 200,
        "triple_max_checks": 2_000_000,
        "triple_max_time": 1800.0,
        # Enable per-component transforms in combo/pointwise/convolution searches.
        # This is still bounded by time/check caps and tends to surface useful
        # “explain the sequence” decompositions.
        "component_transforms": "id,diff,partial_sum",
        "combo_component_transforms": "id,diff,partial_sum",
        # For combinations, also try an expanded (DB-wide prefix index) triple search.
        # This is slower than the normal candidate-pool approach but catches cases where
        # components don't resemble the query.
        "combo_unfiltered": True,
        "combo_expanded": True,
        "combo_expanded_max_time": 1800.0,
        "combo_expanded_anchors": 800,
        # Mod-class (interleave) decompositions a(mn+r)=X_r(n+s_r).
        "modclass": 10,
        "modclass_moduli": "2,3",
        "modclass_max_time": 3.0,
        # combo subcommand expanded triple/pair fallback
        "expanded": True,
        "expanded_max_time": 1800.0,
        "expanded_anchors": 800,
        "stream": True,
        # Pointwise + convolution combo search (analyze pipeline)
        "pointwise_ops": "mul,gcd,lcm",
        "pointwise_limit": 10,
        "convolution_ops": "cauchy,dirichlet",
        "convolution_limit": 5,
    },
}


def _warn_if_db_missing_indexes(db_path: Path, *, as_json: bool) -> None:
    """
    Lightweight CLI hint to help users speed up older DBs.

    This does not create indexes automatically; it only suggests running:
      oeis optimize-db --db <path>
    """
    if as_json:
        return
    db = Path(db_path)
    if not db.exists():
        return
    try:
        from .storage import missing_recommended_indexes

        missing = missing_recommended_indexes(db)
    except Exception:
        return
    if not missing:
        return
    shown = ", ".join(missing[:4])
    extra = "" if len(missing) <= 4 else f", ... (+{len(missing) - 4} more)"
    print(
        f"Tip: DB is missing recommended index(es) ({shown}{extra}). "
        f"Run: oeis optimize-db --db {db}",
        file=sys.stderr,
    )


def _warn_if_data_stale(
    *,
    stripped_path: Path,
    names_path: Path,
    keywords_path: Path,
    db_path: Path,
    metadata_path: Path,
    max_age_days: float,
    warn_on_stale: bool,
    as_json: bool,
) -> None:
    if as_json or not warn_on_stale:
        return
    try:
        report = build_status_report(
            stripped_path=Path(stripped_path),
            names_path=Path(names_path),
            keywords_path=Path(keywords_path),
            db_path=Path(db_path),
            metadata_path=Path(metadata_path),
            max_age_days=float(max_age_days),
            include_db_checks=False,
        )
    except Exception:
        return
    freshness = report.get("freshness") or {}
    if not bool(freshness.get("is_stale")):
        return
    age_days = freshness.get("age_days")
    age_txt = f"{float(age_days):.1f} days" if age_days is not None else "unknown age"
    last_sync = freshness.get("last_sync_utc") or "unknown"
    print(
        f"Warning: local OEIS snapshot is stale ({age_txt}; last sync: {last_sync}). "
        f"Run: oeis status --refresh-if-stale",
        file=sys.stderr,
    )


def _apply_preset(args, preset_name: str):
    preset = PRESETS.get(preset_name)
    if not preset:
        return args
    for key, val in preset.items():
        if hasattr(args, key):
            setattr(args, key, val)
    return args


def _expand_preset_argv(argv: list[str]) -> list[str]:
    """
    Expand `--preset NAME` into explicit flags inserted before user flags.

    This makes presets act like "defaults": the preset values are applied,
    but any explicit flags the user passed later in argv will override them
    (argparse uses the last occurrence for most options).
    """
    if not argv:
        return argv
    cmd = argv[0]
    if cmd.startswith("-"):
        return argv

    preset_name: str | None = None
    for i, tok in enumerate(argv):
        if tok == "--preset" and i + 1 < len(argv):
            preset_name = argv[i + 1]
            break
    if not preset_name:
        return argv
    preset = PRESETS.get(preset_name)
    if not preset:
        return argv
    # Only expand presets for subcommands that advertise them.
    if cmd not in {"match", "tsearch", "combo", "analyze"}:
        return argv

    # Build option strings for the specific subcommand by looking up its parser.
    # We rely on `main()` calling this after building the parser/subparsers and
    # attaching `_SUBPARSER_CHOICES`.
    choices = globals().get("_SUBPARSER_CHOICES")
    if not isinstance(choices, dict):
        return argv
    subparser = choices.get(cmd)
    if subparser is None:
        return argv

    dest_to_actions: dict[str, list[argparse.Action]] = {}
    for action in getattr(subparser, "_actions", []):
        if not getattr(action, "option_strings", []):
            continue
        dest_to_actions.setdefault(action.dest, []).append(action)

    def _best_action_for(dest: str, val: object | None) -> argparse.Action | None:
        actions = dest_to_actions.get(dest)
        if not actions:
            return None
        if val is True:
            true_actions = [a for a in actions if isinstance(a, argparse._StoreTrueAction)]
            if true_actions:
                return max(true_actions, key=lambda a: max(len(s) for s in a.option_strings))
        if val is False:
            false_actions = [a for a in actions if isinstance(a, argparse._StoreFalseAction)]
            if false_actions:
                return max(false_actions, key=lambda a: max(len(s) for s in a.option_strings))
        return max(actions, key=lambda a: max(len(s) for s in a.option_strings))

    def _flag_for(dest: str, val: object | None) -> str | None:
        action = _best_action_for(dest, val)
        if not action:
            return None
        opts = list(action.option_strings)
        # Prefer the longest (typically the most descriptive).
        return max(opts, key=len) if opts else None

    expanded: list[str] = []

    # Command-specific aliasing:
    # - presets use `tlimit` for transform matches, but the `tsearch` subcommand uses `--limit`.
    if cmd == "tsearch" and "tlimit" in preset:
        flag = _flag_for("limit", preset.get("tlimit"))
        if flag:
            expanded.extend([flag, str(preset["tlimit"])])

    for key, val in preset.items():
        action = _best_action_for(key, val)
        flag = _flag_for(key, val)
        if not flag or not action:
            continue

        # Store-true/false options are represented by a flag with no value.
        if isinstance(action, argparse._StoreTrueAction):
            if bool(val):
                expanded.append(flag)
            continue
        if isinstance(action, argparse._StoreFalseAction):
            # Flag presence sets False; only include if preset wants False.
            if val is False:
                expanded.append(flag)
            continue

        # Avoid overriding the tsearch limit twice; the tlimit->limit mapping above wins.
        if cmd == "tsearch" and key == "limit" and "tlimit" in preset:
            continue

        if val is None:
            continue
        val_txt = str(val)
        # If the value looks like an option (starts with "-"), argparse may treat it
        # as another flag (e.g. "-5,-4,..." is not a valid negative number), so use
        # the `--opt=value` form to disambiguate.
        if val_txt.startswith("-"):
            expanded.append(f"{flag}={val_txt}")
        else:
            expanded.extend([flag, val_txt])

    # Insert right after the subcommand token so flags bind to that subparser.
    return [cmd] + expanded + argv[1:]


def _fmt_coeff_json(c) -> str:
    try:
        import fractions
    except Exception:
        fractions = None
    if fractions and isinstance(c, fractions.Fraction) and c.denominator != 1:
        return f"{c.numerator}/{c.denominator}"
    if isinstance(c, (int, float)) and float(c).is_integer():
        return str(int(c))
    return str(c)


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


def _fmt_formula(text: str | None, max_len: int = 200) -> str:
    if not text:
        return ""
    clean = text.replace("\n", " ")
    if len(clean) > max_len:
        clean = clean[: max_len - 1] + "…"
    return clean

from .combination_search import (
    search_two_sequence_combinations,
    search_two_sequence_combinations_expanded,
    search_three_sequence_combinations,
    search_three_sequence_combinations_expanded,
    search_mod_class_combinations,
    search_pointwise_two_sequence_combinations,
    search_pointwise_two_sequence_combinations_expanded,
    search_convolution_two_sequence_combinations,
    resolve_component_transforms,
)
from .config import load_config
from .build_index import build_index
from .matcher import candidate_sequences, match_exact, match_exact_db
from .ranking import rank_candidates_for_query
from .candidates import get_candidate_bucket
from .query import QueryParseError, parse_query
from .transform_search import search_transform_matches
from .transforms import default_transforms
from .sync import DEFAULT_NAMES_URL, DEFAULT_OEISDATA_REPO, DEFAULT_STRIPPED_URL, sync_data
from .storage import ensure_db_indexes, get_sequence_by_id
from .freshness import build_status_report, update_build_metadata, update_sync_metadata


def _main(argv=None):
    argv = argv or sys.argv[1:]

    cfg = load_config()
    default_stripped = cfg["paths"]["stripped"]
    default_names = cfg["paths"]["names"]
    default_keywords = cfg["paths"]["keywords"]
    default_db = cfg["paths"]["db"]
    default_max_terms = cfg["limits"]["max_terms"]
    default_limit = cfg["limits"]["max_results"]
    freshness_cfg = cfg.get("freshness", {})
    startup_cfg = cfg.get("startup", {})
    default_metadata_path = freshness_cfg.get("metadata_path", "data/processed/freshness.json")
    default_freshness_max_age_days = float(freshness_cfg.get("max_age_days", 30.0))
    default_warn_on_stale = bool(freshness_cfg.get("warn_on_stale", True))
    default_startup_refresh_if_stale = bool(startup_cfg.get("refresh_if_stale", False))

    parser = argparse.ArgumentParser(prog="oeis", description="Offline OEIS matcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build-index", help="Build SQLite index from OEIS raw exports.")
    p_build.add_argument("--stripped", default=default_stripped, help="Path to stripped.gz")
    p_build.add_argument("--names", default=default_names, help="Path to names.gz")
    p_build.add_argument("--keywords", default=default_keywords, help="Path to keywords file (optional)")
    p_build.add_argument("--offsets", default="", help="Path to offsets file (optional; otherwise use oeisdata/seq/OFFSET if present)")
    p_build.add_argument("--formulas", default="", help="Path to formulas file (optional; otherwise use oeisdata/seq/FORMULA if present)")
    p_build.add_argument("--db", default=default_db, help="Output SQLite path")
    p_build.add_argument("--oeisdata", default="data/raw/oeisdata", help="Optional path to oeisdata clone for keywords/metadata")
    p_build.add_argument("--max-terms", type=int, default=default_max_terms, help="Max terms to store per sequence")
    p_build.add_argument("--metadata", default=default_metadata_path, help="Path to freshness metadata JSON (updated on success)")

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
    p_sync.add_argument("--metadata", default=default_metadata_path, help="Path to freshness metadata JSON (updated on success)")

    p_status = sub.add_parser("status", help="Report local environment/data/index freshness and health.")
    p_status.add_argument("--stripped", default=default_stripped, help="Path to stripped OEIS export")
    p_status.add_argument("--names", default=default_names, help="Path to names OEIS export")
    p_status.add_argument("--keywords", default=default_keywords, help="Path to keywords export (optional)")
    p_status.add_argument("--db", default=default_db, help="SQLite index path")
    p_status.add_argument("--metadata", default=default_metadata_path, help="Path to freshness metadata JSON")
    p_status.add_argument("--max-age-days", type=float, default=default_freshness_max_age_days, help="Staleness threshold in days")
    p_status.add_argument(
        "--refresh-if-stale",
        action=argparse.BooleanOptionalAction,
        default=default_startup_refresh_if_stale,
        help="If stale, run sync + build-index non-interactively before printing final status.",
    )
    p_status.add_argument("--stripped-url", default=DEFAULT_STRIPPED_URL, help="Refresh source URL/path for stripped export")
    p_status.add_argument("--names-url", default=DEFAULT_NAMES_URL, help="Refresh source URL/path for names export")
    p_status.add_argument("--keywords-url", default="", help="Optional refresh source URL/path for keywords export")
    p_status.add_argument("--clone-oeisdata", action="store_true", help="Also refresh oeisdata clone during --refresh-if-stale")
    p_status.add_argument("--oeisdata-url", default=DEFAULT_OEISDATA_REPO, help="Repo URL for oeisdata clone during refresh")
    p_status.add_argument("--oeisdata", default="data/raw/oeisdata", help="Destination path for oeisdata clone during refresh")
    p_status.add_argument("--max-terms", type=int, default=default_max_terms, help="Max terms to store when rebuilding after refresh")
    p_status.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")

    p_opt = sub.add_parser("optimize-db", help="Create missing SQLite indexes for faster searches (one-time).")
    p_opt.add_argument("--db", default=default_db, help="SQLite index path")
    p_opt.add_argument("--analyze", action="store_true", help="Run SQLite ANALYZE after creating indexes (optional)")
    p_opt.add_argument(
        "--add-prefix-shifts",
        action="store_true",
        help="Add and backfill shifted prefix columns (prefix5_1..prefix5_k) needed for expanded shifted combo searches.",
    )
    p_opt.add_argument(
        "--max-prefix-shift",
        type=int,
        default=5,
        help="Maximum forward shift k for prefix5_k columns (only used with --add-prefix-shifts).",
    )
    p_opt.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")

    p_match = sub.add_parser("match", help="Match a sequence against OEIS.")
    p_match.add_argument("sequence", help="Comma or space separated integers")
    p_match.add_argument("--db", default=default_db, help="SQLite index path")
    p_match.add_argument("--subsequence", action="store_true", help="Allow subsequence (not just prefix) matches")
    p_match.add_argument("--limit", type=int, default=default_limit, help="Max matches to return")
    p_match.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_match.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_match.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit in text/JSON output")
    p_match.add_argument("--show-formula", action="store_true", help="Include FORMULA text when available (may be lengthy)")
    p_match.add_argument("--similar", type=int, default=0, help="Also show top N similarity candidates (scale+offset).")
    p_match.add_argument("--min-corr", type=float, default=None, help="Minimum correlation for similarity candidates")
    p_match.add_argument("--max-mse", type=float, default=None, help="Maximum MSE for similarity candidates")
    p_match.add_argument("--variance-band", type=float, default=None, help="Variance band for candidate filtering (overrides config)")
    p_match.add_argument("--growth-band", type=float, default=None, help="Growth-rate band for candidate filtering")
    p_match.add_argument("--no-subsequence-fallback", action="store_true", help="Do not auto-try subsequence if no prefix hit")
    p_match.add_argument("--preset", choices=list(PRESETS.keys()), help="Preset for search depth/limits (fast|deep|max)")

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
    p_tsearch.add_argument(
        "--extra-transforms",
        default="",
        help="Comma list of optional transforms. Examples: diff2,cumprod,reverse,evenodd,movsum3,binomial,euler,mobius,rle,rledec,concat,digitsum10,popcount,mod2,xorindex,log2,log10,loge,exp2,omega,bigomega,tau,sigma,phi,v2,indexsquare,primeindex,indexpow2,indexfactorial. Also supports patterns: movsumK, digitsumB, modM, expB.",
    )
    p_tsearch.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_tsearch.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")
    p_tsearch.add_argument("--show-formula", action="store_true", help="Include FORMULA text when available")
    p_tsearch.add_argument("--preset", choices=list(PRESETS.keys()), help="Preset for search depth/limits (fast|deep|max)")
    p_tsearch.add_argument("--max-time", type=float, default=None, help="Max wall time (seconds) for transform search")
    p_tsearch.add_argument("--variance-band", type=float, default=None, help="Variance band for candidate filtering (overrides config)")
    p_tsearch.add_argument("--growth-band", type=float, default=None, help="Growth-rate band for candidate filtering")
    p_tsearch.add_argument("--transform-min-score", type=float, default=None, help="Minimum score for transform matches")
    p_tsearch.add_argument("--transform-max-complexity", type=float, default=None, help="Maximum complexity for transform chains")
    p_tsearch.add_argument("--allow-constant-transforms", action="store_true", help="Keep constant transform outputs (default: drop)")
    p_tsearch.add_argument("--stream", action="store_true", help="Print matches as they are found (text mode only)")
    p_tsearch.add_argument("--no-stream", dest="stream", action="store_false", help="Disable streaming output (text mode).")
    p_tsearch.set_defaults(stream=False)

    p_combo = sub.add_parser(
        "combo",
        help="Search combinations (2-seq linear, 3-seq linear, pointwise ops, convolution).",
    )
    p_combo.add_argument("sequence", help="Comma or space separated integers")
    p_combo.add_argument("--db", default=default_db, help="SQLite index path")
    p_combo.add_argument("--preset", choices=list(PRESETS.keys()), help="Preset for candidate caps/coeffs (fast|deep|max)")
    p_combo.add_argument("--coeffs", default="-3,-2,-1,1,2,3", help="Comma-separated integer coefficients to try")
    p_combo.add_argument("--max-shift", type=int, default=0, help="Maximum forward shift (drop first k terms)")
    p_combo.add_argument("--max-shift-back", type=int, default=0, help="Maximum backward shift (negative indices)")
    p_combo.add_argument("--limit", type=int, default=default_limit, help="Max combination matches to return")
    p_combo.add_argument("--min-match-length", type=int, default=3, help="Minimum query length to consider")
    p_combo.add_argument("--candidates", type=int, default=40, help="Max candidate sequences to consider")
    p_combo.add_argument("--max-checks", type=int, default=200_000, help="Max coefficient/shift combinations to evaluate")
    p_combo.add_argument("--max-time", type=float, default=None, help="Max wall time (seconds) for combo search")
    p_combo.add_argument("--total-max-time", type=float, default=None, help="Hard wall time cap (seconds) for the entire combo pipeline")
    p_combo.add_argument("--max-combinations", type=int, default=None, help="Max combination evaluations to attempt (pairs)")
    p_combo.add_argument("--min-score", type=float, default=None, help="Minimum score for combo matches")
    p_combo.add_argument("--max-complexity", type=float, default=None, help="Maximum complexity for combo matches")
    p_combo.add_argument("--rational", action="store_true", help="Solve coefficients over rationals instead of brute-forcing integers")
    p_combo.add_argument("--triples", type=int, default=0, help="Return up to N three-sequence combinations")
    p_combo.add_argument("--triple-candidates", type=int, default=25, help="Max candidates for triple search")
    p_combo.add_argument("--triple-max-checks", type=int, default=300_000, help="Max evaluations for triple search")
    p_combo.add_argument("--triple-max-time", type=float, default=None, help="Max wall time (seconds) for triple search")
    p_combo.add_argument("--triple-max-combinations", type=int, default=None, help="Max combination evaluations to attempt (triples)")
    p_combo.add_argument("--triple-rational", action="store_true", help="Solve triple coefficients over rationals")
    p_combo.add_argument("--triple-min-score", type=float, default=None, help="Minimum score for triple matches")
    p_combo.add_argument("--triple-max-complexity", type=float, default=None, help="Maximum complexity for triple matches")
    p_combo.add_argument("--component-transforms", default="id", help="Comma-separated per-sequence transforms: id,diff,partial_sum")
    p_combo.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each match (components + result) in output")
    p_combo.add_argument(
        "--include-ids",
        default="",
        help="Comma-separated OEIS ids to force into the combo candidate pool (e.g., A000045,A000204).",
    )
    p_combo.add_argument(
        "--expanded",
        action="store_true",
        help="Also try expanded (DB-wide prefix index) searches for pairs/triples if none are found (slower).",
    )
    p_combo.add_argument(
        "--no-expanded",
        dest="expanded",
        action="store_false",
        help="Disable expanded (DB-wide) combo fallback (useful with --preset max overrides).",
    )
    p_combo.set_defaults(expanded=False)
    p_combo.add_argument(
        "--expanded-max-time",
        type=float,
        default=3.0,
        help="Max wall time (seconds) for expanded pair/triple search (only applies with --expanded).",
    )
    p_combo.add_argument(
        "--expanded-pointwise",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable expanded (DB-wide prefix index) pointwise mul fallback. Defaults to --expanded.",
    )
    p_combo.add_argument(
        "--expanded-pointwise-max-time",
        type=float,
        default=None,
        help="Max wall time (seconds) for expanded pointwise fallback (defaults to --expanded-max-time).",
    )
    p_combo.add_argument(
        "--expanded-anchors",
        type=int,
        default=400,
        help="Max anchor sequences to try for expanded triple search (only applies with --expanded).",
    )
    p_combo.add_argument("--variance-band", type=float, default=None, help="Variance band for candidate filtering (overrides config)")
    p_combo.add_argument("--growth-band", type=float, default=None, help="Growth-rate band for candidate filtering")
    p_combo.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_combo.add_argument("--combo-unfiltered", action="store_true", help="Skip prefix index when building combo candidate pool (use invariant/length filter instead)")
    p_combo.add_argument("--no-combo-unfiltered", dest="combo_unfiltered", action="store_false", help="Use prefix index for combo candidate pool (default).")
    p_combo.set_defaults(combo_unfiltered=False)
    p_combo.add_argument("--pointwise-ops", default="", help="Comma-separated pointwise ops: mul,gcd,lcm")
    p_combo.add_argument("--convolution-ops", default="", help="Comma-separated convolution ops: cauchy,dirichlet")
    p_combo.add_argument("--modclass", type=int, default=0, help="Return up to N mod-class/interleave decompositions (a(mn+r)=...).")
    p_combo.add_argument("--modclass-moduli", default="2,3", help="Comma-separated moduli to try for --modclass (e.g., 2,3,4).")
    p_combo.add_argument("--modclass-max-time", type=float, default=None, help="Max wall time (seconds) for --modclass stage.")
    p_combo.add_argument("--stream", action="store_true", help="Print matches as they are found (text mode only)")
    p_combo.add_argument("--no-stream", dest="stream", action="store_false", help="Disable streaming output (text mode).")
    p_combo.set_defaults(stream=False)
    p_combo.add_argument("--timings", action="store_true", help="Include per-stage timing diagnostics")

    p_analyze = sub.add_parser(
        "analyze",
        help="Run full pipeline (exact, transforms, similarity, combinations).",
    )
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
    p_analyze.add_argument(
        "--extra-transforms",
        default="",
        help="Comma list of optional transforms. Examples: diff2,cumprod,reverse,evenodd,movsum3,binomial,euler,mobius,rle,rledec,concat,digitsum10,popcount,mod2,xorindex,log2,log10,loge,exp2,omega,bigomega,tau,sigma,phi,v2,indexsquare,primeindex,indexpow2,indexfactorial. Also supports patterns: movsumK, digitsumB, modM, expB.",
    )
    p_analyze.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_analyze.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")
    p_analyze.add_argument("--show-formula", action="store_true", help="Include FORMULA text when available")
    p_analyze.add_argument("--similar", type=int, default=0, help="Return top N similarity-ranked candidates (scale+offset).")
    p_analyze.add_argument("--min-corr", type=float, default=None, help="Minimum correlation for similarity candidates")
    p_analyze.add_argument("--max-mse", type=float, default=None, help="Maximum MSE for similarity candidates")
    p_analyze.add_argument("--variance-band", type=float, default=None, help="Variance band for candidate filtering (overrides config)")
    p_analyze.add_argument("--growth-band", type=float, default=None, help="Growth-rate band for candidate filtering")
    p_analyze.add_argument("--combos", type=int, default=0, help="Return up to N two-sequence combinations (experimental)")
    p_analyze.add_argument("--combo-candidates", type=int, default=40, help="Max candidate sequences to consider for combos")
    p_analyze.add_argument("--combo-coeffs", default="-3,-2,-1,1,2,3", help="Comma-separated integer coefficients to try in combos")
    p_analyze.add_argument("--combo-max-shift", type=int, default=0, help="Maximum forward shift for combo search")
    p_analyze.add_argument("--combo-max-shift-back", type=int, default=0, help="Maximum backward shift for combo search")
    p_analyze.add_argument("--combo-max-checks", type=int, default=200_000, help="Max coefficient/shift combinations to evaluate for combos")
    p_analyze.add_argument("--combo-max-time", type=float, default=None, help="Max wall time (seconds) for combo search")
    p_analyze.add_argument("--combo-max-combinations", type=int, default=None, help="Max combination evaluations (pairs)")
    p_analyze.add_argument("--combo-min-score", type=float, default=None, help="Minimum score for combo matches")
    p_analyze.add_argument("--combo-max-complexity", type=float, default=None, help="Maximum complexity for combo matches")
    p_analyze.add_argument("--combo-rational", action="store_true", help="Solve combo coefficients over rationals (pairs only)")
    p_analyze.add_argument("--combo-component-transforms", default="id", help="Per-sequence transforms for combos: id,diff,partial_sum")
    p_analyze.add_argument("--triples", type=int, default=0, help="Return up to N three-sequence combinations (experimental, slow)")
    p_analyze.add_argument("--triple-candidates", type=int, default=25, help="Max candidate sequences to consider for triple combos")
    p_analyze.add_argument("--triple-max-checks", type=int, default=300_000, help="Max evaluations for triple combos")
    p_analyze.add_argument("--triple-max-time", type=float, default=None, help="Max wall time (seconds) for triple combos")
    p_analyze.add_argument("--triple-max-combinations", type=int, default=None, help="Max combination evaluations (triples)")
    p_analyze.add_argument("--triple-rational", action="store_true", help="Solve triple coefficients over rationals")
    p_analyze.add_argument("--triple-min-score", type=float, default=None, help="Minimum score for triple combo matches")
    p_analyze.add_argument("--triple-max-complexity", type=float, default=None, help="Maximum complexity for triple combo matches")
    p_analyze.add_argument("--combo-unfiltered", action="store_true", help="Skip prefix index when building combo candidate pool (use invariant/length filter instead)")
    p_analyze.add_argument("--no-combo-unfiltered", dest="combo_unfiltered", action="store_false", help="Use prefix index for combos (default).")
    p_analyze.add_argument(
        "--combo-expanded",
        action="store_true",
        help="Enable expanded (DB-wide prefix index) combo fallback when regular pair/triple search finds no results.",
    )
    p_analyze.add_argument(
        "--no-combo-expanded",
        dest="combo_expanded",
        action="store_false",
        help="Disable expanded (DB-wide) combo fallback (default).",
    )
    p_analyze.add_argument(
        "--combo-expanded-max-time",
        type=float,
        default=0.0,
        help="Max wall time (seconds) for expanded combo fallback (0 = no fallback time cap).",
    )
    p_analyze.add_argument(
        "--combo-expanded-pointwise",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable expanded (DB-wide) pointwise mul fallback (defaults to --combo-expanded).",
    )
    p_analyze.add_argument(
        "--combo-expanded-pointwise-max-time",
        type=float,
        default=None,
        help="Max wall time (seconds) for expanded pointwise fallback (defaults to --combo-expanded-max-time).",
    )
    p_analyze.add_argument(
        "--combo-expanded-anchors",
        type=int,
        default=400,
        help="Max anchor sequences to try during expanded triple fallback (triples only).",
    )
    p_analyze.add_argument("--no-subsequence-fallback", action="store_true", help="Do not auto-try subsequence if no prefix hit")
    p_analyze.add_argument("--pointwise-ops", default="", help="Comma-separated pointwise ops for combinations: mul,gcd,lcm")
    p_analyze.add_argument("--pointwise-limit", type=int, default=0, help="Return up to N pointwise combinations (experimental)")
    p_analyze.add_argument("--convolution-ops", default="", help="Comma-separated convolution ops: cauchy,dirichlet")
    p_analyze.add_argument("--convolution-limit", type=int, default=0, help="Return up to N convolution combinations (experimental)")
    p_analyze.add_argument("--modclass", type=int, default=0, help="Return up to N mod-class/interleave decompositions (a(mn+r)=...).")
    p_analyze.add_argument("--modclass-moduli", default="2,3", help="Comma-separated moduli to try for --modclass (e.g., 2,3,4).")
    p_analyze.add_argument("--modclass-max-time", type=float, default=None, help="Max wall time (seconds) for --modclass stage.")
    p_analyze.add_argument("--preset", choices=list(PRESETS.keys()), help="Preset for search depth/limits (fast|deep|max)")
    p_analyze.add_argument("--stream", action="store_true", help="Print results as stages complete (text mode only)")
    p_analyze.add_argument("--no-stream", dest="stream", action="store_false", help="Disable streaming output (text mode).")
    p_analyze.set_defaults(stream=False)
    p_analyze.add_argument("--timings", action="store_true", help="Include per-stage timing diagnostics")
    p_analyze.add_argument("--total-max-time", type=float, default=None, help="Hard wall time cap (seconds) for the entire analyze pipeline")
    p_analyze.add_argument("--transform-max-time", type=float, default=None, help="Max wall time (seconds) for transform search")
    p_analyze.add_argument("--transform-min-score", type=float, default=None, help="Minimum score for transform matches")
    p_analyze.add_argument("--transform-max-complexity", type=float, default=None, help="Maximum complexity for transform chains")
    p_analyze.add_argument("--allow-constant-transforms", action="store_true", help="Keep constant transform outputs (default: drop)")
    p_analyze.set_defaults(combo_unfiltered=False, combo_expanded=False)

    p_selfcheck = sub.add_parser("selfcheck", help="Run offline sanity checks (regressions + random combos).")
    p_selfcheck.add_argument("--db", default=default_db, help="SQLite index path")
    p_selfcheck.add_argument("--regressions", default="docs/regressions.json", help="Path to regression cases JSON")
    p_selfcheck.add_argument(
        "--no-regressions",
        dest="run_regressions",
        action="store_false",
        help="Skip regression cases (useful with small custom DBs).",
    )
    p_selfcheck.set_defaults(run_regressions=True)
    p_selfcheck.add_argument("--random-trials", type=int, default=0, help="Run N random combo sanity trials (requires a built DB)")
    p_selfcheck.add_argument("--pointwise-trials", type=int, default=0, help="Run N random pointwise (mul) trials (fast)")
    p_selfcheck.add_argument(
        "--convolution-trials",
        type=int,
        default=0,
        help="Run N random convolution trials (randomly chooses cauchy/dirichlet; fast)",
    )
    p_selfcheck.add_argument("--seed", type=int, default=0, help="RNG seed for random trials (deterministic)")
    p_selfcheck.add_argument("--qlen", type=int, default=8, help="Query length per random trial (>=5 recommended)")
    p_selfcheck.add_argument("--min-length", type=int, default=30, help="Minimum stored length for randomly chosen component sequences")
    p_selfcheck.add_argument("--scan-stride", type=int, default=100, help="Prefer A-numbers divisible by this for expanded pair trials")
    p_selfcheck.add_argument("--pair-max-time", type=float, default=6.0, help="Max seconds per expanded-pair random trial")
    p_selfcheck.add_argument("--pointwise-max-time", type=float, default=0.75, help="Max seconds per pointwise random trial")
    p_selfcheck.add_argument("--convolution-max-time", type=float, default=0.75, help="Max seconds per convolution random trial")
    p_selfcheck.add_argument("--pairs-only", action="store_true", help="Only run expanded pair trials")
    p_selfcheck.add_argument("--triples-only", action="store_true", help="Only run triple-in-bucket trials")
    p_selfcheck.add_argument("--fail-fast", action="store_true", help="Stop on first failing regression case")
    p_selfcheck.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")

    # Expose subparser choices so `_expand_preset_argv` can map preset keys to real flags.
    global _SUBPARSER_CHOICES
    _SUBPARSER_CHOICES = dict(sub.choices)
    argv = _expand_preset_argv(list(argv))
    args = parser.parse_args(argv)

    if args.cmd in {"match", "tsearch", "combo", "analyze", "selfcheck"}:
        _warn_if_db_missing_indexes(Path(args.db), as_json=bool(getattr(args, "as_json", False)))
        _warn_if_data_stale(
            stripped_path=Path(default_stripped),
            names_path=Path(default_names),
            keywords_path=Path(default_keywords),
            db_path=Path(args.db),
            metadata_path=Path(default_metadata_path),
            max_age_days=default_freshness_max_age_days,
            warn_on_stale=default_warn_on_stale,
            as_json=bool(getattr(args, "as_json", False)),
        )

    if args.cmd == "build-index":
        stripped_path = Path(args.stripped)
        names_path = Path(args.names)
        keywords_path = Path(args.keywords)
        db_path = Path(args.db)
        stats = build_index(
            stripped_path,
            names_path,
            keywords_path,
            db_path,
            max_terms=args.max_terms,
            oeisdata_root=Path(args.oeisdata),
            offsets_path=Path(args.offsets) if args.offsets else None,
            formulas_path=Path(args.formulas) if args.formulas else None,
        )
        try:
            update_build_metadata(
                Path(args.metadata),
                db_path=db_path,
                stripped_path=stripped_path,
                names_path=names_path,
                keywords_path=keywords_path,
                max_terms=args.max_terms,
                build_stats=stats,
            )
        except Exception as exc:
            print(f"Warning: failed to update freshness metadata: {exc}", file=sys.stderr)
        print(f"Inserted {stats['inserted']} sequences into {stats['db']}")
        return 0

    if args.cmd == "sync":
        stripped_path = Path(args.stripped)
        names_path = Path(args.names)
        keywords_path = Path(args.keywords)
        oeisdata_path = Path(args.oeisdata)
        stats = sync_data(
            stripped_url=args.stripped_url,
            names_url=args.names_url,
            keywords_url=args.keywords_url or None,
            stripped_path=stripped_path,
            names_path=names_path,
            keywords_path=keywords_path,
            force=args.force,
            clone_oeisdata=args.clone_oeisdata,
            oeisdata_path=oeisdata_path,
            oeisdata_url=args.oeisdata_url,
        )
        try:
            update_sync_metadata(
                Path(args.metadata),
                stripped_source=args.stripped_url,
                names_source=args.names_url,
                keywords_source=args.keywords_url or None,
                oeisdata_source=args.oeisdata_url if args.clone_oeisdata else None,
                stripped_path=stripped_path,
                names_path=names_path,
                keywords_path=keywords_path,
                oeisdata_path=oeisdata_path if args.clone_oeisdata else None,
                sync_stats=stats,
            )
        except Exception as exc:
            print(f"Warning: failed to update freshness metadata: {exc}", file=sys.stderr)
        for label in ("stripped", "names", "keywords", "oeisdata"):
            if label in stats:
                s = stats[label]
                size = f" ({s.get('bytes', 0)} bytes)" if "bytes" in s else ""
                print(f"{label}: {s['status']}{size} -> {s['path']}")
        print("Note: OEIS data is CC BY-SA 4.0; include attribution when redistributing.")
        return 0

    if args.cmd == "status":
        report = build_status_report(
            stripped_path=Path(args.stripped),
            names_path=Path(args.names),
            keywords_path=Path(args.keywords),
            db_path=Path(args.db),
            metadata_path=Path(args.metadata),
            max_age_days=float(args.max_age_days),
        )
        refresh_result: dict[str, object] | None = None
        exit_code = 0

        if bool(args.refresh_if_stale) and bool((report.get("freshness") or {}).get("is_stale")):
            refresh_result = {"attempted": True, "ok": False}
            stripped_path = Path(args.stripped)
            names_path = Path(args.names)
            keywords_path = Path(args.keywords)
            oeisdata_path = Path(args.oeisdata)
            db_path = Path(args.db)
            try:
                sync_stats = sync_data(
                    stripped_url=args.stripped_url,
                    names_url=args.names_url,
                    keywords_url=args.keywords_url or None,
                    stripped_path=stripped_path,
                    names_path=names_path,
                    keywords_path=keywords_path,
                    force=True,
                    clone_oeisdata=bool(args.clone_oeisdata),
                    oeisdata_path=oeisdata_path,
                    oeisdata_url=args.oeisdata_url,
                )
                update_sync_metadata(
                    Path(args.metadata),
                    stripped_source=args.stripped_url,
                    names_source=args.names_url,
                    keywords_source=args.keywords_url or None,
                    oeisdata_source=args.oeisdata_url if args.clone_oeisdata else None,
                    stripped_path=stripped_path,
                    names_path=names_path,
                    keywords_path=keywords_path,
                    oeisdata_path=oeisdata_path if args.clone_oeisdata else None,
                    sync_stats=sync_stats,
                )
                build_stats = build_index(
                    stripped_path,
                    names_path,
                    keywords_path,
                    db_path,
                    max_terms=int(args.max_terms),
                    oeisdata_root=oeisdata_path if args.clone_oeisdata else None,
                )
                update_build_metadata(
                    Path(args.metadata),
                    db_path=db_path,
                    stripped_path=stripped_path,
                    names_path=names_path,
                    keywords_path=keywords_path,
                    max_terms=int(args.max_terms),
                    build_stats=build_stats,
                )
                refresh_result.update(
                    {
                        "ok": True,
                        "sync": sync_stats,
                        "build": build_stats,
                    }
                )
            except Exception as exc:
                refresh_result["error"] = str(exc)
                exit_code = 2
            report = build_status_report(
                stripped_path=Path(args.stripped),
                names_path=Path(args.names),
                keywords_path=Path(args.keywords),
                db_path=Path(args.db),
                metadata_path=Path(args.metadata),
                max_age_days=float(args.max_age_days),
            )
        elif bool(args.refresh_if_stale):
            refresh_result = {"attempted": False, "reason": "not_stale"}

        if refresh_result is not None:
            report["refresh"] = refresh_result

        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
            return exit_code

        freshness = report.get("freshness") or {}
        age_days = freshness.get("age_days")
        age_txt = f"{float(age_days):.1f}d" if age_days is not None else "unknown"
        freshness_state = "stale" if freshness.get("is_stale") else "fresh"
        print(f"Status: {'ready' if report.get('ready') else 'degraded'}")
        print(
            "Freshness: "
            f"{freshness_state} (age={age_txt}, threshold={float(freshness.get('max_age_days') or 0.0):.1f}d, "
            f"last_sync={freshness.get('last_sync_utc') or 'unknown'})"
        )

        paths = report.get("paths") or {}
        for label in ("stripped", "names", "keywords"):
            marker = paths.get(label) or {}
            state = "ok" if marker.get("exists") else "missing"
            size = f"{int(marker.get('bytes'))} bytes" if marker.get("bytes") is not None else "n/a"
            mtime = marker.get("mtime_utc") or "n/a"
            print(f"{label}: {state} ({size}, mtime={mtime}) -> {marker.get('path')}")

        db_info = paths.get("db") or {}
        db_state = "ok" if db_info.get("exists") else "missing"
        db_seq = db_info.get("sequence_count")
        seq_txt = f", sequences={db_seq}" if db_seq is not None else ""
        print(f"db: {db_state}{seq_txt} -> {db_info.get('path')}")
        missing_indexes = db_info.get("missing_recommended_indexes") or []
        if missing_indexes:
            preview = ", ".join(missing_indexes[:5])
            suffix = "" if len(missing_indexes) <= 5 else f", ... (+{len(missing_indexes) - 5} more)"
            print(f"db indexes: missing {preview}{suffix}")
            print(f"Tip: oeis optimize-db --db {db_info.get('path')}")
        else:
            print("db indexes: ok")

        if refresh_result is not None:
            if refresh_result.get("attempted") and refresh_result.get("ok"):
                print("Refresh: completed (sync + build-index).")
            elif refresh_result.get("attempted") and not refresh_result.get("ok"):
                print(f"Refresh: failed ({refresh_result.get('error')})")
            else:
                print("Refresh: skipped (not stale).")

        for warning in report.get("warnings") or []:
            print(f"Warning: {warning}")
        return exit_code

    if args.cmd == "optimize-db":
        db_path = Path(args.db)
        stats = ensure_db_indexes(db_path, analyze=bool(args.analyze))
        if getattr(args, "add_prefix_shifts", False):
            try:
                from .storage import ensure_prefix_shifts

                shift_stats = ensure_prefix_shifts(db_path, max_shift=int(getattr(args, "max_prefix_shift", 5)))
                stats.update(
                    {
                        "prefix_shift_columns_added": shift_stats.get("added_columns") or [],
                        "prefix_shift_rows_updated": int(shift_stats.get("updated_rows") or 0),
                        "prefix_shift_max_shift": int(shift_stats.get("max_shift") or 0),
                    }
                )
            except Exception as e:
                stats["prefix_shift_error"] = str(e)
        if args.as_json:
            print(json.dumps(stats, indent=2))
            return 0

        created = stats.get("created") or []
        missing_cols = stats.get("missing_columns") or []
        analyzed = bool(stats.get("analyzed"))
        prefix_added = stats.get("prefix_shift_columns_added") or []
        prefix_rows = int(stats.get("prefix_shift_rows_updated") or 0)
        prefix_err = stats.get("prefix_shift_error") or ""

        print(f"DB: {db_path}")
        if created:
            print(f"Created {len(created)} index(es):")
            for name in created:
                print(f"  - {name}")
        else:
            print("No new indexes created (already optimized).")
        if prefix_added:
            print(f"\nAdded {len(prefix_added)} shifted prefix column(s):")
            for name in prefix_added:
                print(f"  - {name}")
            print(f"Backfilled shifted prefixes for {prefix_rows} row(s).")
        if prefix_err:
            print(f"\nWarning: failed to add/backfill shifted prefixes: {prefix_err}")
        if missing_cols:
            print("\nNote: DB is missing some optional columns, so some indexes were skipped:")
            for col in missing_cols:
                print(f"  - {col}")
        if analyzed:
            print("\nSQLite ANALYZE completed.")
        return 0

    if args.cmd == "match":
        try:
            query = parse_query(
                args.sequence,
                min_match_length=args.min_match_length,
                allow_subsequence=args.subsequence,
            )
        except QueryParseError as e:
            print(f"Invalid query: {e}")
            return 2
        db_path = Path(args.db)
        matches = match_exact_db(query, db_path, limit=args.limit, snippet_len=args.show_terms)
        fallback_used = False
        if not matches and not args.subsequence and not args.no_subsequence_fallback:
            try:
                fq = parse_query(
                    args.sequence,
                    min_match_length=args.min_match_length,
                    allow_subsequence=True,
                )
            except QueryParseError as e:
                print(f"Invalid query (fallback): {e}")
                return 2
            matches = match_exact_db(fq, db_path, limit=args.limit, snippet_len=args.show_terms)
            fallback_used = True
        sim_matches = (
            rank_candidates_for_query(
                query,
                db_path,
                top_k=args.similar,
                min_corr=args.min_corr,
                max_mse=args.max_mse,
                variance_band=args.variance_band,
                growth_band=args.growth_band,
            )
            if args.similar
            else []
        )
        if args.as_json:
            out = [
                {
                    "id": m.id,
                    "name": m.name,
                    "match_type": m.match_type,
                    "offset": m.offset,
                    "length": m.length,
                    **({"formula": m.formula} if args.show_formula and m.formula else {}),
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
            diag = {"variance_band": args.variance_band, "growth_band": args.growth_band}
            if fallback_used:
                diag["subsequence_fallback"] = True
            payload = {"query": query.terms, "matches": out, "similarity": sim, "diagnostics": diag}
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
                formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
                formula_disp = f" formula={formula_txt}" if formula_txt else ""
                print(f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{score}{snippet}{formula_disp}")
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
        stream_text = bool(getattr(args, "stream", False) and not args.as_json)
        try:
            query = parse_query(
                args.sequence,
                min_match_length=args.min_match_length,
                allow_subsequence=args.subsequence,
            )
        except QueryParseError as e:
            print(f"Invalid query: {e}")
            return 2

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
            moving_sum_windows=tuple(sorted(set((2,) if extras["movsum2"] else ()) | set(extras["movsum_windows"]))),
            allow_popcount=extras["popcount"],
            allow_digit_sum=extras["digitsum"],
            digit_sum_bases=extras["digit_bases"],
            modulus_values=extras["mod_values"],
            allow_xor_index=extras["xor_index"],
            allow_rle=extras["rle"],
            allow_rle_decode=extras["rle_dec"],
            allow_concat=extras["concat"],
            allow_binomial=extras["binomial"],
            allow_euler=extras["euler"],
            allow_mobius=extras["mobius"],
            allow_log=bool(extras["log_bases"]),
            log_bases=extras["log_bases"],
            allow_exp=bool(extras["exp_bases"]),
            exp_bases=extras["exp_bases"],
            allow_omega=extras["omega"],
            allow_bigomega=extras["bigomega"],
            allow_tau=extras["tau"],
            allow_sigma=extras["sigma"],
            allow_phi=extras["phi"],
            allow_v2=extras["v2"],
            allow_index_square=extras["index_square"],
            allow_prime_index=extras["prime_index"],
            allow_index_pow2=extras["index_pow2"],
            allow_index_factorial=extras["index_factorial"],
        )

        printed_transform: dict[tuple[str, str], tuple[str, float | None]] = {}
        printed_transform_count = 0

        def _fmt_transform_line(m) -> str:
            name = f" - {m.name}" if m.name else ""
            snippet = ""
            if m.snippet is not None:
                snippet = " terms=" + ",".join(str(t) for t in m.snippet)
            if m.transformed_terms is not None:
                snippet += " transformed=" + ",".join(str(t) for t in m.transformed_terms)
            expl = m.explanation or m.transform_desc or ""
            tdesc = f" via {expl}" if expl else ""
            if m.symbolic:
                tdesc += f" [{m.symbolic}]"
            score = f" score={m.score:.2f}" if m.score is not None else ""
            formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
            formula_disp = f" formula={formula_txt}" if formula_txt else ""
            return f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{score}{snippet}{formula_disp}"

        def _on_transform_match(m) -> None:
            nonlocal printed_transform_count
            key = (m.id, m.match_type)
            if key in printed_transform:
                return
            if args.limit is not None and printed_transform_count >= int(args.limit):
                return
            printed_transform[key] = (m.transform_desc or "", m.score)
            printed_transform_count += 1
            print(_fmt_transform_line(m), flush=True)

        snip = _choose_snippet_len(query.terms, args.show_terms)
        if args.limit and args.limit > 0:
            if stream_text:
                print("Transform matches:", flush=True)
            matches = search_transform_matches(
                query,
                Path(args.db),
                max_depth=args.max_depth,
                transforms=transforms,
                limit=args.limit,
                snippet_len=snip,
                full_scan=args.preset in ("deep", "max"),
                max_time_s=args.max_time,
                min_score=args.transform_min_score,
                max_complexity=args.transform_max_complexity,
                variance_band=args.variance_band,
                growth_band=args.growth_band,
                allow_constant_outputs=args.allow_constant_transforms,
                on_match=_on_transform_match if stream_text else None,
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
                    **({"formula": m.formula} if args.show_formula and m.formula else {}),
                    **({"explanation": m.explanation} if m.explanation else {}),
                    **({"latex": m.latex} if m.latex else {}),
                    **({"symbolic": m.symbolic} if m.symbolic else {}),
                    **({"symbolic_latex": m.symbolic_latex} if m.symbolic_latex else {}),
                    **({"terms": m.snippet} if m.snippet is not None else {}),
                    **({"transformed_terms": m.transformed_terms} if m.transformed_terms is not None else {}),
                }
                for m in matches
            ]
            print(json.dumps({"query": query.terms, "matches": out}, indent=2))
        else:
            if stream_text:
                if not matches:
                    print("  (none)", flush=True)
                else:
                    # Print any new/better final results not already streamed.
                    for m in matches:
                        key = (m.id, m.match_type)
                        cur = (m.transform_desc or "", m.score)
                        if printed_transform.get(key) != cur:
                            print(_fmt_transform_line(m), flush=True)
                return 0
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
                if m.symbolic:
                    tdesc += f" [{m.symbolic}]"
                formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
                formula_disp = f" formula={formula_txt}" if formula_txt else ""
                print(f"{m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{formula_disp}{snippet}")
            return 0

    if args.cmd == "combo":
        import time

        timings: dict[str, float] = {}
        t_start = time.perf_counter()
        stream_text = bool(getattr(args, "stream", False) and not args.as_json)
        time_budget_exhausted = False

        def _elapsed_s() -> float:
            return time.perf_counter() - t_start

        def _remaining_s() -> float | None:
            total = getattr(args, "total_max_time", None)
            if total is None:
                return None
            try:
                return max(0.0, float(total) - _elapsed_s())
            except (TypeError, ValueError):
                return None

        def _cap_by_total(stage_cap: float | None) -> float | None:
            rem = _remaining_s()
            if rem is None:
                return stage_cap
            if rem <= 0:
                return 0.0
            if stage_cap is None:
                return rem
            try:
                stage_cap_f = float(stage_cap)
            except (TypeError, ValueError):
                return rem
            return min(stage_cap_f, rem)

        deadline_s: float | None = None
        if getattr(args, "total_max_time", None) is not None:
            try:
                deadline_s = t_start + float(args.total_max_time)
            except (TypeError, ValueError):
                deadline_s = None

        try:
            query = parse_query(
                args.sequence,
                min_match_length=args.min_match_length,
                allow_subsequence=False,
            )
        except QueryParseError as e:
            print(f"Invalid query: {e}")
            return 2
        db_path = Path(args.db)
        coeffs = _parse_int_list(args.coeffs)
        triple_candidates = args.triple_candidates or args.candidates
        cap = max(args.candidates, triple_candidates)
        if stream_text:
            mode = "unfiltered" if args.combo_unfiltered else "prefix+invariants"
            print(f"Building candidate bucket (cap={cap}, mode={mode})…", flush=True)
        t0 = time.perf_counter()
        # Avoid letting candidate-bucket building consume the entire global budget.
        # Even a partial bucket is usually enough to start finding pair/triple hits,
        # and the expanded fallback can cover the "components don't resemble query"
        # cases under `--preset max`.
        bucket_deadline_s = deadline_s
        if deadline_s is not None:
            rem = _remaining_s()
            if rem is not None:
                cand_budget_s = min(60.0, rem * 0.25)
                bucket_deadline_s = min(deadline_s, time.perf_counter() + cand_budget_s)
        bucket = get_candidate_bucket(
            query,
            db_path,
            exact_limit=cap,
            similar_limit=cap,
            max_records=cap,
            fill_unfiltered=True,
            skip_prefix_filter=args.combo_unfiltered,
            variance_band=args.variance_band,
            growth_band=args.growth_band,
            deadline_s=bucket_deadline_s,
            time_fn=time.perf_counter,
        )
        if args.timings:
            timings["candidates_ms"] = 1000 * (time.perf_counter() - t0)
        include_ids = _parse_oeis_ids(args.include_ids)
        records = list(bucket.records)
        if include_ids:
            for sid in include_ids:
                rec = get_sequence_by_id(db_path, sid)
                if rec:
                    records.append(rec)
            # De-dupe; included ids should never be dropped later due to candidate trimming.
            records_by_id = {r.id: r for r in records}
            records = list(records_by_id.values())
        if stream_text:
            note = ""
            if bucket_deadline_s is not None and time.perf_counter() >= bucket_deadline_s:
                note = " (time-capped)"
            print(
                f"Candidate bucket: {len(records)} sequences (exact={len(bucket.exact_ids)} similar={len(bucket.similar_ids)}){note}",
                flush=True,
            )
        comp_transforms = resolve_component_transforms(_parse_transform_names(args.component_transforms))
        snip = _choose_snippet_len(query.terms, args.show_terms)
        max_candidates = None if include_ids else args.candidates
        triple_max_candidates = None if include_ids else triple_candidates

        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True

        def _fmt_combo_line(m, *, show_coeffs: bool = True) -> str:
            if len(m.ids) == 2:
                n1 = f" - {m.names[0]}" if m.names[0] else ""
                n2 = f" - {m.names[1]}" if m.names[1] else ""
                extra = ""
                if m.component_terms:
                    extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
                if m.combined_terms:
                    extra += f" result={_fmt_terms(m.combined_terms)}"
                coeffs_disp = ",".join(_fmt_coeff_json(c) for c in m.coeffs)
                coeffs_txt = f" coeffs={coeffs_disp}" if show_coeffs else ""
                return f"  {m.expression} len={m.length}{coeffs_txt} score={m.score:.2f} [{m.ids[0]}{n1}; {m.ids[1]}{n2}]{extra}"
            name_parts = [f"{id_}{' - ' + nm if nm else ''}" for id_, nm in zip(m.ids, m.names)]
            extra = ""
            if m.component_terms:
                extra = " " + " ".join(f"terms{i+1}={_fmt_terms(ts)}" for i, ts in enumerate(m.component_terms))
            if m.combined_terms:
                extra += f" result={_fmt_terms(m.combined_terms)}"
            return f"  {m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}"

        combos = []
        modclass_matches = []
        need_expanded_pairs = False
        if not time_budget_exhausted:
            t1 = time.perf_counter()
            if stream_text:
                print("Pair combinations:", flush=True)
            combos = search_two_sequence_combinations(
                query,
                records,
                coeffs=coeffs,
                max_shift=args.max_shift,
                max_shift_back=args.max_shift_back,
                limit=args.limit,
                max_candidates=max_candidates,
                max_checks=args.max_checks,
                max_time_s=_cap_by_total(args.max_time),
                max_combinations=args.max_combinations,
                component_transforms=comp_transforms,
                snippet_len=snip,
                use_rational=args.rational,
                min_score=args.min_score,
                max_complexity=args.max_complexity,
                on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=True), flush=True)) if stream_text else None,
            )
            if args.timings:
                timings["pair_ms"] = 1000 * (time.perf_counter() - t1)

            # Expanded DB-wide searches can be expensive (especially pairs).
            # To improve time-to-first-hit for triples, defer the expanded pair
            # fallback until after pointwise/convolution/triple stages.
            if args.expanded and not combos and (args.total_max_time is None or _remaining_s() > 0):
                if len(query.terms) < 5:
                    if stream_text:
                        print("  (expanded DB-wide search needs >= 5 terms; skipping)", flush=True)
                else:
                    exp_time = args.expanded_max_time if args.expanded_max_time and args.expanded_max_time > 0 else None
                    exp_time = _cap_by_total(exp_time)
                    if exp_time is None or exp_time > 0:
                        need_expanded_pairs = True
                        if stream_text:
                            print("  (no regular pair combos found; will try expanded DB-wide search later…)", flush=True)

            if stream_text and (not combos) and (not need_expanded_pairs):
                print("  (none)", flush=True)
            if args.total_max_time is not None and _remaining_s() == 0:
                time_budget_exhausted = True

        if args.modclass and int(args.modclass) > 0 and not time_budget_exhausted and (args.total_max_time is None or _remaining_s() > 0):
            t_mc = time.perf_counter()
            if stream_text:
                print("\nMod-class combinations:", flush=True)
            mc_time = _cap_by_total(getattr(args, "modclass_max_time", None))
            if mc_time is None or mc_time > 0:
                moduli = _parse_int_list(str(getattr(args, "modclass_moduli", "2,3")).replace(" ", ","))
                moduli = [m for m in moduli if m > 1]
                modclass_matches = search_mod_class_combinations(
                    query,
                    db_path,
                    moduli=tuple(moduli) if moduli else (2, 3),
                    limit=int(args.modclass),
                    max_shift=args.max_shift,
                    max_time_s=mc_time,
                    snippet_len=snip,
                    min_score=args.min_score,
                    max_complexity=args.max_complexity,
                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                )
            if args.timings:
                timings["modclass_ms"] = 1000 * (time.perf_counter() - t_mc)
            if stream_text and not modclass_matches:
                print("  (none)", flush=True)
            if args.total_max_time is not None and _remaining_s() == 0:
                time_budget_exhausted = True
        pointwise_matches = []
        conv_matches: list = []
        pw_ops = _parse_pointwise_ops(args.pointwise_ops)
        if pw_ops:
            if not time_budget_exhausted:
                expanded_pointwise = args.expanded if getattr(args, "expanded_pointwise", None) is None else bool(getattr(args, "expanded_pointwise"))
                t_pw = time.perf_counter()
                if stream_text:
                    print("\nPointwise combinations:", flush=True)
                pointwise_matches = search_pointwise_two_sequence_combinations(
                    query,
                    records,
                    ops=pw_ops,
                    max_shift=args.max_shift,
                    max_shift_back=args.max_shift_back,
                    limit=args.limit,
                    max_candidates=max_candidates,
                    max_checks=args.max_checks,
                    max_time_s=_cap_by_total(args.max_time),
                    component_transforms=comp_transforms,
                    snippet_len=snip,
                    min_score=args.min_score,
                    max_complexity=args.max_complexity,
                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                )
                # Expanded DB-wide fallback for pointwise multiplication. This is
                # important for cases where the multiplicative "mask" component
                # (0/1/2-valued, sparse, etc.) does not resemble the product.
                if (
                    expanded_pointwise
                    and ("mul" in pw_ops)
                    and (not pointwise_matches)
                    and (args.total_max_time is None or _remaining_s() > 0)
                    and len(query.terms) >= 5
                ):
                    raw_cap = getattr(args, "expanded_pointwise_max_time", None)
                    if raw_cap is None:
                        raw_cap = args.expanded_max_time
                    exp_time = raw_cap if raw_cap and raw_cap > 0 else None
                    exp_time = _cap_by_total(exp_time)
                    if exp_time is None or exp_time > 0:
                        t_pwe = time.perf_counter()
                        if stream_text:
                            print("  (no in-bucket mul hits; trying expanded DB-wide mul…)", flush=True)
                        pointwise_matches = search_pointwise_two_sequence_combinations_expanded(
                            query,
                            db_path,
                            ops=("mul",),
                            max_shift=args.max_shift,
                            limit=args.limit,
                            max_time_s=exp_time,
                            snippet_len=snip,
                            min_score=args.min_score,
                            max_complexity=args.max_complexity,
                            on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                        )
                        if args.timings:
                            timings["expanded_pointwise_ms"] = 1000 * (time.perf_counter() - t_pwe)
                if args.timings:
                    timings["pointwise_ms"] = 1000 * (time.perf_counter() - t_pw)
                if stream_text and not pointwise_matches:
                    print("  (none)", flush=True)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
        conv_ops = _parse_conv_ops(args.convolution_ops)
        if conv_ops:
            if not time_budget_exhausted:
                t_conv = time.perf_counter()
                if stream_text:
                    print("\nConvolution combinations:", flush=True)
                conv_matches = search_convolution_two_sequence_combinations(
                    query,
                    records,
                    ops=conv_ops,
                    max_length=32,
                    limit=args.limit,
                    max_candidates=max_candidates,
                    max_checks=args.max_checks,
                    max_time_s=_cap_by_total(args.max_time),
                    component_transforms=comp_transforms,
                    snippet_len=snip,
                    min_score=args.min_score,
                    max_complexity=args.max_complexity,
                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                )
                if args.timings:
                    timings["convolution_ms"] = 1000 * (time.perf_counter() - t_conv)
                if stream_text and not conv_matches:
                    print("  (none)", flush=True)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
        triples = []
        if args.triples:
            if not time_budget_exhausted:
                t3 = time.perf_counter()
                if stream_text:
                    print("\nTriple combinations:", flush=True)
                triples = search_three_sequence_combinations(
                    query,
                    records,
                    coeffs=coeffs,
                    max_shift=args.max_shift,
                    max_shift_back=args.max_shift_back,
                    limit=args.triples,
                    max_candidates=triple_max_candidates,
                    max_checks=args.triple_max_checks,
                    max_time_s=_cap_by_total(args.triple_max_time),
                    max_combinations=args.triple_max_combinations,
                    component_transforms=comp_transforms,
                    snippet_len=snip,
                    min_score=args.triple_min_score,
                    max_complexity=args.triple_max_complexity,
                    use_rational=args.triple_rational,
                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                )
                if args.timings:
                    timings["triples_ms"] = 1000 * (time.perf_counter() - t3)
                if args.expanded and not triples and (args.total_max_time is None or _remaining_s() > 0):
                    if len(query.terms) < 5:
                        if stream_text:
                            print("  (expanded DB-wide search needs >= 5 terms; skipping)", flush=True)
                    else:
                        exp_time = args.expanded_max_time if args.expanded_max_time and args.expanded_max_time > 0 else None
                        exp_time = _cap_by_total(exp_time)
                        if exp_time is None or exp_time > 0:
                            t3e = time.perf_counter()
                            if stream_text:
                                print("  (no regular triple combos found; trying expanded DB-wide search…)", flush=True)
                            triples = search_three_sequence_combinations_expanded(
                                query,
                                db_path,
                                coeffs=coeffs,
                                limit=args.triples,
                                max_anchors=args.expanded_anchors,
                                max_time_s=exp_time,
                                snippet_len=snip,
                                min_score=args.triple_min_score,
                                max_complexity=args.triple_max_complexity,
                                on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                            )
                            if args.timings:
                                timings["expanded_triples_ms"] = 1000 * (time.perf_counter() - t3e)
                if stream_text and not triples:
                    print("  (none)", flush=True)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True

        if need_expanded_pairs and not combos and not time_budget_exhausted and (args.total_max_time is None or _remaining_s() > 0):
            if len(query.terms) < 5:
                if stream_text:
                    print("\nExpanded pair combinations:", flush=True)
                    print("  (expanded DB-wide search needs >= 5 terms; skipping)", flush=True)
            else:
                exp_time = args.expanded_max_time if args.expanded_max_time and args.expanded_max_time > 0 else None
                exp_time = _cap_by_total(exp_time)
                if exp_time is None or exp_time > 0:
                    t1e = time.perf_counter()
                    if stream_text:
                        print("\nExpanded pair combinations:", flush=True)
                    combos = search_two_sequence_combinations_expanded(
                        query,
                        db_path,
                        coeffs=coeffs,
                        limit=args.limit,
                        max_shift=args.max_shift,
                        max_time_s=exp_time,
                        snippet_len=snip,
                        min_score=args.min_score,
                        max_complexity=args.max_complexity,
                        on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=True), flush=True)) if stream_text else None,
                    )
                    if args.timings:
                        timings["expanded_pair_ms"] = 1000 * (time.perf_counter() - t1e)
                if stream_text and not combos:
                    print("  (none)", flush=True)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
        if args.as_json:
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
            out = [
                {
                    "ids": list(m.ids),
                    "names": list(m.names),
                    "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
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
                    "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
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
            out_modclass = [
                {
                    "ids": list(m.ids),
                    "names": list(m.names),
                    "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
                    "shifts": list(m.shifts),
                    "length": m.length,
                    "score": m.score,
                    "expression": m.expression,
                    **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                    **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                    **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                }
                for m in modclass_matches
            ]
            out_pw = [
                {
                    "ids": list(m.ids),
                    "names": list(m.names),
                    "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
                    "shifts": list(m.shifts),
                    "length": m.length,
                    "score": m.score,
                    "expression": m.expression,
                    **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                    **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                    **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                }
                for m in pointwise_matches
            ]
            out_conv = [
                {
                    "ids": list(m.ids),
                    "names": list(m.names),
                    "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
                    "shifts": list(m.shifts),
                    "length": m.length,
                    "score": m.score,
                    "expression": m.expression,
                    **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                    **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                    **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                }
                for m in conv_matches
            ]
            print(
                json.dumps(
                    {
                        "query": query.terms,
                        "combinations": out,
                        "triple_combinations": out3,
                        "modclass_combinations": out_modclass,
                        "pointwise_combinations": out_pw,
                        "convolution_combinations": out_conv,
                        "diagnostics": {
                            **({"timings_ms": timings} if args.timings else {}),
                            "variance_band": args.variance_band,
                            "growth_band": args.growth_band,
                            **({"time_budget_exhausted": True} if time_budget_exhausted else {}),
                        },
                    },
                    indent=2,
                )
            )
        else:
            if stream_text:
                if time_budget_exhausted:
                    print("\n(Time budget reached; stopping early.)", flush=True)
                if args.timings:
                    timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                    print("\nTimings (ms):", flush=True)
                    for k, v in timings.items():
                        print(f"  {k}: {v:.1f}", flush=True)
                if not combos and not triples and not modclass_matches and not pointwise_matches and not conv_matches:
                    if not args.expanded:
                        print("\nNo combinations found. Tip: try --expanded or --preset max.", flush=True)
                    else:
                        print("\nNo combinations found.", flush=True)
                return 0
            if not combos and not triples and not modclass_matches and not pointwise_matches and not conv_matches:
                if not args.expanded:
                    print("No combinations found. Tip: try --expanded or --preset max.")
                else:
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
            if modclass_matches:
                print("\nMod-class combinations:")
                for m in modclass_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = " " + " ".join(f"terms{i+1}={_fmt_terms(ts)}" for i, ts in enumerate(m.component_terms))
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"{m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
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
            if pointwise_matches:
                print("\nPointwise combinations:")
                for m in pointwise_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"{m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
            if conv_matches:
                print("\nConvolution combinations:")
                for m in conv_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"{m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
            if time_budget_exhausted:
                print("\n(Time budget reached; stopping early.)")
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                print("\nTimings (ms):")
                for k, v in timings.items():
                    print(f"  {k}: {v:.1f}")
        return 0

    if args.cmd == "selfcheck":
        from .selfcheck import run_random_combo_trials, run_regressions

        db_path = Path(args.db)
        payload: dict[str, object] = {"db": str(db_path)}
        ok = True

        if args.run_regressions:
            cases_path = Path(args.regressions)
            reg_results, reg_summary = run_regressions(
                db_path=db_path,
                cases_path=cases_path,
                fail_fast=bool(args.fail_fast),
            )
            payload["regressions"] = {
                "summary": reg_summary,
                "results": [{"name": r.name, "ok": r.ok, "elapsed_s": r.elapsed_s, "details": r.details} for r in reg_results],
            }
            ok = ok and (int(reg_summary.get("fails") or 0) == 0)

            if not args.as_json:
                print(f"DB: {db_path}")
                print(f"Regressions ({reg_summary['passes']}/{reg_summary['cases']} passed):")
                for r in reg_results:
                    status = "PASS" if r.ok else "FAIL"
                    print(f"  {status} {r.name} ({r.elapsed_s:.2f}s)")
                    if (not r.ok) and r.details.get("reasons"):
                        for reason in r.details["reasons"]:
                            print(f"    - {reason}")

        if int(args.random_trials) > 0 or int(getattr(args, "pointwise_trials", 0)) > 0 or int(getattr(args, "convolution_trials", 0)) > 0:
            trials, trial_summary = run_random_combo_trials(
                db_path=db_path,
                trials=int(args.random_trials),
                pointwise_trials=int(getattr(args, "pointwise_trials", 0)),
                convolution_trials=int(getattr(args, "convolution_trials", 0)),
                seed=int(args.seed),
                qlen=int(args.qlen),
                min_length=int(args.min_length),
                scan_stride=int(args.scan_stride),
                pair_max_time_s=float(args.pair_max_time),
                pointwise_max_time_s=float(getattr(args, "pointwise_max_time", 0.75)),
                convolution_max_time_s=float(getattr(args, "convolution_max_time", 0.75)),
                pairs_only=bool(args.pairs_only),
                triples_only=bool(args.triples_only),
            )
            payload["random_trials"] = {
                "summary": trial_summary,
                "results": [
                    {"kind": t.kind, "ok": t.ok, "elapsed_s": t.elapsed_s, "expression": t.expression, "details": t.details}
                    for t in trials
                ],
            }
            ok = ok and (int(trial_summary.get("fails") or 0) == 0)

            if not args.as_json:
                print(f"\nRandom trials ({trial_summary['passes']}/{trial_summary['trials']} passed):")
                for t in trials:
                    status = "OK" if t.ok else "FAIL"
                    print(f"  {status} [{t.kind}] {t.expression} ({t.elapsed_s:.2f}s)")

        if args.as_json:
            print(json.dumps(payload, indent=2))

        return 0 if ok else 2

    if args.cmd == "analyze":
        import time
        timings: dict[str, float] = {}
        t_start = time.perf_counter()
        deadline_s: float | None = None
        if args.total_max_time is not None:
            try:
                deadline_s = t_start + float(args.total_max_time)
            except (TypeError, ValueError):
                deadline_s = None
        stream_text = bool(args.stream and not args.as_json)
        time_budget_exhausted = False

        def _elapsed_s() -> float:
            return time.perf_counter() - t_start

        def _remaining_s() -> float | None:
            if args.total_max_time is None:
                return None
            return max(0.0, float(args.total_max_time) - _elapsed_s())

        def _cap_by_total(stage_cap: float | None) -> float | None:
            rem = _remaining_s()
            if rem is None:
                return stage_cap
            if rem <= 0:
                return 0.0
            if stage_cap is None:
                return rem
            try:
                stage_cap_f = float(stage_cap)
            except (TypeError, ValueError):
                return rem
            return min(stage_cap_f, rem)

        def _fmt_combo_line(m, *, show_coeffs: bool = True) -> str:
            if len(m.ids) == 2:
                n1 = f" - {m.names[0]}" if m.names[0] else ""
                n2 = f" - {m.names[1]}" if m.names[1] else ""
                extra = ""
                if m.component_terms:
                    extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
                if m.combined_terms:
                    extra += f" result={_fmt_terms(m.combined_terms)}"
                coeffs_disp = ",".join(_fmt_coeff_json(c) for c in m.coeffs)
                coeffs_txt = f" coeffs={coeffs_disp}" if show_coeffs else ""
                return f"  {m.expression} len={m.length}{coeffs_txt} score={m.score:.2f} [{m.ids[0]}{n1}; {m.ids[1]}{n2}]{extra}"
            name_parts = [f"{id_}{' - ' + nm if nm else ''}" for id_, nm in zip(m.ids, m.names)]
            extra = ""
            if m.component_terms:
                extra = " " + " ".join(f"terms{i+1}={_fmt_terms(ts)}" for i, ts in enumerate(m.component_terms))
            if m.combined_terms:
                extra += f" result={_fmt_terms(m.combined_terms)}"
            return f"  {m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}"

        try:
            query = parse_query(
                args.sequence,
                min_match_length=args.min_match_length,
                allow_subsequence=args.subsequence,
            )
        except QueryParseError as e:
            print(f"Invalid query: {e}")
            return 2
        db_path = Path(args.db)

        # Exact matches (with optional fallback to subsequence)
        t0 = time.perf_counter()
        exact_matches = match_exact_db(query, db_path, limit=args.limit, snippet_len=args.show_terms)
        fallback_used = False
        if not exact_matches and not args.subsequence and not args.no_subsequence_fallback:
            try:
                fb_query = parse_query(
                    args.sequence,
                    min_match_length=args.min_match_length,
                    allow_subsequence=True,
                )
            except QueryParseError as e:
                print(f"Invalid query (fallback): {e}")
                return 2
            exact_matches = match_exact_db(fb_query, db_path, limit=args.limit, snippet_len=args.show_terms)
            fallback_used = True
        if args.timings:
            timings["exact_ms"] = 1000 * (time.perf_counter() - t0)
        if stream_text:
            print("Exact matches:", flush=True)
            if not exact_matches:
                print("  (none)", flush=True)
            for m in exact_matches:
                name = f" - {m.name}" if m.name else ""
                snippet = f" terms={','.join(str(t) for t in m.snippet)}" if m.snippet else ""
                score = f" score={m.score:.2f}" if m.score is not None else ""
                formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
                formula_disp = f" formula={formula_txt}" if formula_txt else ""
                print(f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{score}{snippet}{formula_disp}", flush=True)
        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True

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
            moving_sum_windows=tuple(sorted(set((2,) if extras["movsum2"] else ()) | set(extras["movsum_windows"]))),
            allow_popcount=extras["popcount"],
            allow_digit_sum=extras["digitsum"],
            digit_sum_bases=extras["digit_bases"],
            modulus_values=extras["mod_values"],
            allow_xor_index=extras["xor_index"],
            allow_rle=extras["rle"],
            allow_rle_decode=extras["rle_dec"],
            allow_concat=extras["concat"],
            allow_binomial=extras["binomial"],
            allow_euler=extras["euler"],
            allow_mobius=extras["mobius"],
            allow_log=bool(extras["log_bases"]),
            log_bases=extras["log_bases"],
            allow_exp=bool(extras["exp_bases"]),
            exp_bases=extras["exp_bases"],
            allow_omega=extras["omega"],
            allow_bigomega=extras["bigomega"],
            allow_tau=extras["tau"],
            allow_sigma=extras["sigma"],
            allow_phi=extras["phi"],
            allow_v2=extras["v2"],
            allow_index_square=extras["index_square"],
            allow_prime_index=extras["prime_index"],
            allow_index_pow2=extras["index_pow2"],
            allow_index_factorial=extras["index_factorial"],
        )

        combo_snip = _choose_snippet_len(query.terms, args.show_terms)

        def _fmt_transform_line(m) -> str:
            name = f" - {m.name}" if m.name else ""
            snippet = f" terms={','.join(str(t) for t in m.snippet)}" if m.snippet else ""
            if m.transformed_terms:
                snippet += f" transformed={','.join(str(t) for t in m.transformed_terms)}"
            expl = m.explanation or m.transform_desc or ""
            tdesc = f" via {expl}" if expl else ""
            if m.symbolic:
                tdesc += f" [{m.symbolic}]"
            score = f" score={m.score:.2f}" if m.score is not None else ""
            formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
            formula_disp = f" formula={formula_txt}" if formula_txt else ""
            return f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{score}{snippet}{formula_disp}"

        printed_transform: dict[tuple[str, str], tuple[str, float | None]] = {}
        printed_transform_count = 0

        def _on_transform_match(m) -> None:
            nonlocal printed_transform_count
            key = (m.id, m.match_type)
            if key in printed_transform:
                return
            # Keep streaming output bounded even when full_scan produces many candidates.
            if args.tlimit is not None and printed_transform_count >= int(args.tlimit):
                return
            printed_transform[key] = (m.transform_desc or "", m.score)
            printed_transform_count += 1
            print(_fmt_transform_line(m), flush=True)

        if stream_text:
            print("\nTransform matches:", flush=True)
        if args.tlimit and args.tlimit > 0 and (_remaining_s() is None or _remaining_s() > 0):
            transform_time_cap = _cap_by_total(args.transform_max_time)
            if transform_time_cap is not None and transform_time_cap <= 0:
                t_matches = []
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
            else:
                t_matches = search_transform_matches(
                    query,
                    db_path,
                    max_depth=args.max_depth,
                    transforms=transforms,
                    limit=args.tlimit,
                    snippet_len=combo_snip,
                    full_scan=args.preset in ("deep", "max"),
                    max_time_s=transform_time_cap,
                    min_score=args.transform_min_score,
                    max_complexity=args.transform_max_complexity,
                    variance_band=args.variance_band,
                    growth_band=args.growth_band,
                    allow_constant_outputs=args.allow_constant_transforms,
                    on_match=_on_transform_match if stream_text else None,
                )
        else:
            t_matches = []
            if args.total_max_time is not None and _remaining_s() == 0:
                time_budget_exhausted = True
        t1 = time.perf_counter()
        if args.timings:
            timings["transform_ms"] = 1000 * (t1 - t0) - timings.get("exact_ms", 0.0)
        if stream_text:
            if not t_matches:
                print("  (none)", flush=True)
            else:
                # Print any new/better final results not already streamed.
                for m in t_matches:
                    key = (m.id, m.match_type)
                    cur = (m.transform_desc or "", m.score)
                    if printed_transform.get(key) != cur:
                        print(_fmt_transform_line(m), flush=True)
        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True

        sim_matches = (
            rank_candidates_for_query(
                query,
                db_path,
                top_k=args.similar,
                min_corr=args.min_corr,
                max_mse=args.max_mse,
                variance_band=args.variance_band,
                growth_band=args.growth_band,
                deadline_s=deadline_s,
                time_fn=time.perf_counter,
            )
            if (args.similar and (_remaining_s() is None or _remaining_s() > 0))
            else []
        )
        t2 = time.perf_counter()
        if args.timings and args.similar:
            timings["similarity_ms"] = 1000 * (t2 - t1)
        if stream_text and sim_matches:
            print("\nSimilarity candidates:", flush=True)
            for c in sim_matches:
                print(
                    f"  {c.record.id} corr={c.corr:.3f} mse={c.mse:.3g} scale={c.scale:.3g} offset={c.offset:.3g} - {c.record.name}",
                    flush=True,
                )
        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True
        modclass_matches: list = []
        if args.modclass and int(args.modclass) > 0 and (_remaining_s() is None or _remaining_s() > 0):
            mc_start = time.perf_counter()
            mc_time_cap = _cap_by_total(args.modclass_max_time)
            if mc_time_cap is not None and mc_time_cap <= 0:
                modclass_matches = []
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
            else:
                if stream_text:
                    print("\nMod-class combinations:", flush=True)
                moduli = _parse_int_list(str(getattr(args, "modclass_moduli", "2,3")).replace(" ", ","))
                moduli = [m for m in moduli if m > 1]
                modclass_matches = search_mod_class_combinations(
                    query,
                    db_path,
                    moduli=tuple(moduli) if moduli else (2, 3),
                    limit=int(args.modclass),
                    max_shift=args.combo_max_shift,
                    max_time_s=mc_time_cap,
                    snippet_len=combo_snip,
                    min_score=args.combo_min_score,
                    max_complexity=args.combo_max_complexity,
                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                )
                if stream_text and not modclass_matches:
                    print("  (none)", flush=True)
                if args.timings:
                    timings["modclass_ms"] = 1000 * (time.perf_counter() - mc_start)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
        combo_matches: list = []
        triple_matches: list = []
        pointwise_matches: list = []
        conv_matches: list = []
        if (
            (args.combos or args.triples or (getattr(args, "pointwise_limit", 0) > 0 and args.pointwise_ops) or (getattr(args, "convolution_limit", 0) > 0 and args.convolution_ops))
            and (_remaining_s() is None or _remaining_s() > 0)
        ):
            combo_coeffs = _parse_int_list(args.combo_coeffs)
            triple_candidates = args.triple_candidates or args.combo_candidates
            cap = max(args.combo_candidates, triple_candidates)
            comp_transforms = resolve_component_transforms(_parse_transform_names(args.combo_component_transforms))
            combo_snip = _choose_snippet_len(query.terms, args.show_terms)
            bucket_deadline_s = deadline_s
            if deadline_s is not None:
                rem = _remaining_s()
                if rem is not None:
                    cand_budget_s = min(60.0, rem * 0.25)
                    bucket_deadline_s = min(deadline_s, time.perf_counter() + cand_budget_s)
            if stream_text:
                mode = "unfiltered" if args.combo_unfiltered else "prefix+invariants"
                print(f"\nBuilding combo candidate bucket (cap={cap}, mode={mode})…", flush=True)
            bucket = get_candidate_bucket(
                query,
                db_path,
                exact_limit=cap,
                similar_limit=cap,
                max_records=cap,
                fill_unfiltered=True,
                skip_prefix_filter=args.combo_unfiltered,
                variance_band=args.variance_band,
                growth_band=args.growth_band,
                deadline_s=bucket_deadline_s,
                time_fn=time.perf_counter,
            )
            if stream_text:
                note = ""
                if bucket_deadline_s is not None and time.perf_counter() >= bucket_deadline_s:
                    note = " (time-capped)"
                print(
                    f"Combo candidate bucket: {len(bucket.records)} sequences (exact={len(bucket.exact_ids)} similar={len(bucket.similar_ids)}){note}",
                    flush=True,
                )

            need_expanded_pairs = False
            expanded_pair_start = expanded_pair_end = None
            if args.combos:
                combo_start = time.perf_counter()
                combo_time_cap = _cap_by_total(args.combo_max_time)
                if combo_time_cap is not None and combo_time_cap <= 0:
                    combo_matches = []
                    if args.total_max_time is not None and _remaining_s() == 0:
                        time_budget_exhausted = True
                else:
                    if stream_text:
                        print("\nCombination matches:", flush=True)
                    combo_matches = search_two_sequence_combinations(
                        query,
                        bucket.records,
                        coeffs=combo_coeffs,
                        max_shift=args.combo_max_shift,
                        max_shift_back=args.combo_max_shift_back,
                        limit=args.combos,
                        max_candidates=args.combo_candidates,
                        max_checks=args.combo_max_checks,
                        max_time_s=combo_time_cap,
                        max_combinations=args.combo_max_combinations,
                        component_transforms=comp_transforms,
                        snippet_len=combo_snip,
                        min_score=args.combo_min_score,
                        max_complexity=args.combo_max_complexity,
                        use_rational=args.combo_rational,
                        on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=True), flush=True)) if stream_text else None,
                    )
                    # Expanded DB-wide pair search can be expensive; defer it until after
                    # pointwise/convolution/triple stages for better time-to-first-hit.
                    if args.combo_expanded and not combo_matches and (_remaining_s() is None or _remaining_s() > 0):
                        if len(query.terms) < 5:
                            if stream_text:
                                print("  (expanded DB-wide search needs >= 5 terms; skipping)", flush=True)
                        else:
                            exp_time = args.combo_expanded_max_time if args.combo_expanded_max_time and args.combo_expanded_max_time > 0 else None
                            exp_time = _cap_by_total(exp_time)
                            if exp_time is not None and exp_time <= 0:
                                if args.total_max_time is not None and _remaining_s() == 0:
                                    time_budget_exhausted = True
                            else:
                                need_expanded_pairs = True
                                if stream_text:
                                    print("  (no regular pair combos found; will try expanded DB-wide search later…)", flush=True)
                    if stream_text and not combo_matches and not need_expanded_pairs:
                        print("  (none)", flush=True)
                combo_end = time.perf_counter()
            else:
                combo_start = combo_end = None

            pw_ops = _parse_pointwise_ops(getattr(args, "pointwise_ops", ""))
            if getattr(args, "pointwise_limit", 0) > 0 and pw_ops:
                pw_start = time.perf_counter()
                pw_time_cap = _cap_by_total(args.combo_max_time)
                if pw_time_cap is not None and pw_time_cap <= 0:
                    pointwise_matches = []
                    if args.total_max_time is not None and _remaining_s() == 0:
                        time_budget_exhausted = True
                else:
                    if stream_text:
                        print("\nPointwise combination matches:", flush=True)
                    combo_expanded_pointwise = (
                        args.combo_expanded
                        if getattr(args, "combo_expanded_pointwise", None) is None
                        else bool(getattr(args, "combo_expanded_pointwise"))
                    )
                    pointwise_matches = search_pointwise_two_sequence_combinations(
                        query,
                        bucket.records,
                        ops=pw_ops,
                        max_shift=args.combo_max_shift,
                        max_shift_back=args.combo_max_shift_back,
                        limit=args.pointwise_limit,
                        max_candidates=args.combo_candidates,
                        max_checks=args.combo_max_checks,
                        max_time_s=pw_time_cap,
                        component_transforms=comp_transforms,
                        snippet_len=combo_snip,
                        min_score=args.combo_min_score,
                        max_complexity=args.combo_max_complexity,
                        on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                    )
                    # Expanded DB-wide fallback for pointwise multiplication (mul).
                    # This helps recover factor-style explanations even when a
                    # multiplicative component doesn't resemble the product.
                    if (
                        combo_expanded_pointwise
                        and ("mul" in pw_ops)
                        and (not pointwise_matches)
                        and (_remaining_s() is None or _remaining_s() > 0)
                        and len(query.terms) >= 5
                    ):
                        raw_cap = getattr(args, "combo_expanded_pointwise_max_time", None)
                        if raw_cap is None:
                            raw_cap = args.combo_expanded_max_time
                        exp_time = raw_cap if raw_cap and raw_cap > 0 else None
                        exp_time = _cap_by_total(exp_time)
                        if exp_time is None or exp_time > 0:
                            t_pwe = time.perf_counter()
                            if stream_text:
                                print("  (no in-bucket mul hits; trying expanded DB-wide mul…)", flush=True)
                            pointwise_matches = search_pointwise_two_sequence_combinations_expanded(
                                query,
                                db_path,
                                ops=("mul",),
                                max_shift=args.combo_max_shift,
                                limit=args.pointwise_limit,
                                max_time_s=exp_time,
                                snippet_len=combo_snip,
                                min_score=args.combo_min_score,
                                max_complexity=args.combo_max_complexity,
                                on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                            )
                            if args.timings:
                                timings["expanded_pointwise_ms"] = 1000 * (time.perf_counter() - t_pwe)
                    if stream_text and not pointwise_matches:
                        print("  (none)", flush=True)
                pw_end = time.perf_counter()
            else:
                pw_start = pw_end = None

            conv_ops = _parse_conv_ops(getattr(args, "convolution_ops", ""))
            if getattr(args, "convolution_limit", 0) > 0 and conv_ops:
                conv_start = time.perf_counter()
                conv_time_cap = _cap_by_total(args.combo_max_time)
                if conv_time_cap is not None and conv_time_cap <= 0:
                    conv_matches = []
                    if args.total_max_time is not None and _remaining_s() == 0:
                        time_budget_exhausted = True
                else:
                    if stream_text:
                        print("\nConvolution combination matches:", flush=True)
                    conv_matches = search_convolution_two_sequence_combinations(
                        query,
                        bucket.records,
                        ops=conv_ops,
                        max_length=32,
                        limit=args.convolution_limit,
                        max_candidates=args.combo_candidates,
                        max_checks=args.combo_max_checks,
                        max_time_s=conv_time_cap,
                        component_transforms=comp_transforms,
                        snippet_len=combo_snip,
                        min_score=args.combo_min_score,
                        max_complexity=args.combo_max_complexity,
                        on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                    )
                    if stream_text and not conv_matches:
                        print("  (none)", flush=True)
                conv_end = time.perf_counter()
            else:
                conv_start = conv_end = None

            # Triples can be significantly more expensive than pair/pointwise/convolution
            # searches, so run them later to improve time-to-first-hit for simpler combo
            # explanations under `--preset max`.
            if args.triples:
                triple_start = time.perf_counter()
                triple_time_cap = _cap_by_total(args.triple_max_time)
                if triple_time_cap is not None and triple_time_cap <= 0:
                    triple_matches = []
                    if args.total_max_time is not None and _remaining_s() == 0:
                        time_budget_exhausted = True
                else:
                    if stream_text:
                        print("\nTriple combination matches:", flush=True)
                    triple_matches = search_three_sequence_combinations(
                        query,
                        bucket.records,
                        coeffs=combo_coeffs,
                        max_shift=args.combo_max_shift,
                        max_shift_back=args.combo_max_shift_back,
                        limit=args.triples,
                        max_candidates=triple_candidates,
                        max_checks=args.triple_max_checks,
                        max_time_s=triple_time_cap,
                        max_combinations=args.triple_max_combinations,
                        component_transforms=comp_transforms,
                        snippet_len=combo_snip,
                        min_score=args.triple_min_score,
                        max_complexity=args.triple_max_complexity,
                        use_rational=args.triple_rational,
                        on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                    )
                    if args.combo_expanded and not triple_matches:
                        exp_time = args.combo_expanded_max_time if args.combo_expanded_max_time and args.combo_expanded_max_time > 0 else None
                        exp_time = _cap_by_total(exp_time)
                        if exp_time is not None and exp_time <= 0:
                            if args.total_max_time is not None and _remaining_s() == 0:
                                time_budget_exhausted = True
                        else:
                            if len(query.terms) < 5:
                                if stream_text:
                                    print("  (expanded DB-wide search needs >= 5 terms; skipping)", flush=True)
                            else:
                                if stream_text:
                                    print("  (no regular triple combos found; trying expanded DB-wide search…)", flush=True)
                                triple_matches = search_three_sequence_combinations_expanded(
                                    query,
                                    db_path,
                                    coeffs=combo_coeffs,
                                    limit=args.triples,
                                    max_anchors=args.combo_expanded_anchors,
                                    max_time_s=exp_time,
                                    snippet_len=combo_snip,
                                    min_score=args.triple_min_score,
                                    max_complexity=args.triple_max_complexity,
                                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                                )
                    if stream_text and not triple_matches:
                        print("  (none)", flush=True)
                triple_end = time.perf_counter()
            else:
                triple_start = triple_end = None

            if need_expanded_pairs and not combo_matches and not time_budget_exhausted and (_remaining_s() is None or _remaining_s() > 0):
                exp_time = args.combo_expanded_max_time if args.combo_expanded_max_time and args.combo_expanded_max_time > 0 else None
                exp_time = _cap_by_total(exp_time)
                if exp_time is not None and exp_time <= 0:
                    if args.total_max_time is not None and _remaining_s() == 0:
                        time_budget_exhausted = True
                else:
                    expanded_pair_start = time.perf_counter()
                    if stream_text:
                        print("\nExpanded pair combinations:", flush=True)
                    combo_matches = search_two_sequence_combinations_expanded(
                        query,
                        db_path,
                        coeffs=combo_coeffs,
                        limit=args.combos,
                        max_shift=args.combo_max_shift,
                        max_time_s=exp_time,
                        snippet_len=combo_snip,
                        min_score=args.combo_min_score,
                        max_complexity=args.combo_max_complexity,
                        on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=True), flush=True)) if stream_text else None,
                    )
                    expanded_pair_end = time.perf_counter()
                    if stream_text and not combo_matches:
                        print("  (none)", flush=True)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True

            if args.timings:
                if combo_start is not None and combo_end is not None:
                    pair_ms = 1000 * (combo_end - combo_start)
                    if expanded_pair_start is not None and expanded_pair_end is not None:
                        expanded_ms = 1000 * (expanded_pair_end - expanded_pair_start)
                        timings["expanded_pair_ms"] = expanded_ms
                        pair_ms += expanded_ms
                    timings["combination_ms"] = pair_ms
                if triple_start is not None and triple_end is not None:
                    timings["triple_ms"] = 1000 * (triple_end - triple_start)
                if pw_start is not None and pw_end is not None:
                    timings["pointwise_ms"] = 1000 * (pw_end - pw_start)
                if conv_start is not None and conv_end is not None:
                    timings["convolution_ms"] = 1000 * (conv_end - conv_start)

        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True

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
                if m.symbolic:
                    row["symbolic"] = m.symbolic
                if m.symbolic_latex:
                    row["symbolic_latex"] = m.symbolic_latex
                if args.show_formula and m.formula:
                    row["formula"] = m.formula
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
                        "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
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
                        "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
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
                "modclass_combinations": [
                    {
                        "ids": list(m.ids),
                        "names": list(m.names),
                        "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
                        "shifts": list(m.shifts),
                        "length": m.length,
                        "score": m.score,
                        "expression": m.expression,
                        **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                        **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                        **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                    }
                    for m in modclass_matches
                ],
                "pointwise_combinations": [
                    {
                        "ids": list(m.ids),
                        "names": list(m.names),
                        "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
                        "shifts": list(m.shifts),
                        "length": m.length,
                        "score": m.score,
                        "expression": m.expression,
                        **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                        **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                        **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                    }
                    for m in pointwise_matches
                ],
                "convolution_combinations": [
                    {
                        "ids": list(m.ids),
                        "names": list(m.names),
                        "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
                        "shifts": list(m.shifts),
                        "length": m.length,
                        "score": m.score,
                        "expression": m.expression,
                        **({"component_transforms": list(m.component_transforms)} if m.component_transforms else {}),
                        **({"component_terms": [list(t) for t in m.component_terms]} if m.component_terms else {}),
                        **({"combined_terms": m.combined_terms} if m.combined_terms else {}),
                    }
                    for m in conv_matches
                ],
            }
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
            payload["diagnostics"] = {
                **({"timings_ms": timings} if args.timings else {}),
                "variance_band": args.variance_band,
                "growth_band": args.growth_band,
                **({"subsequence_fallback": True} if fallback_used else {}),
                **({"time_budget_exhausted": True} if time_budget_exhausted else {}),
            }
            print(json.dumps(payload, indent=2))
        else:
            if stream_text:
                if time_budget_exhausted:
                    print("\n(Time budget reached; stopping early.)", flush=True)
                if args.timings:
                    timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                    print("\nTimings (ms):", flush=True)
                    for k, v in timings.items():
                        print(f"  {k}: {v:.1f}", flush=True)
                return 0
            print("Exact matches:")
            if not exact_matches:
                print("  (none)")
            for m in exact_matches:
                name = f" - {m.name}" if m.name else ""
                snippet = f" terms={','.join(str(t) for t in m.snippet)}" if m.snippet else ""
                score = f" score={m.score:.2f}" if m.score is not None else ""
                formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
                formula_disp = f" formula={formula_txt}" if formula_txt else ""
                print(f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{score}{snippet}{formula_disp}")

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
                if m.symbolic:
                    tdesc += f" [{m.symbolic}]"
                score = f" score={m.score:.2f}" if m.score is not None else ""
                formula_txt = _fmt_formula(m.formula) if args.show_formula else ""
                formula_disp = f" formula={formula_txt}" if formula_txt else ""
                print(f"  {m.id} [{m.match_type} @ {m.offset}] len={m.length}{name}{tdesc}{score}{snippet}{formula_disp}")

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
                    coeffs_disp = ",".join(_fmt_coeff_json(c) for c in m.coeffs)
                    print(
                        f"  {m.expression} len={m.length} coeffs={coeffs_disp} score={m.score:.2f} [{m.ids[0]}{n1}; {m.ids[1]}{n2}]{extra}"
                    )
            if modclass_matches:
                print("\nMod-class combinations:")
                for m in modclass_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = " " + " ".join(f"terms{i+1}={_fmt_terms(ts)}" for i, ts in enumerate(m.component_terms))
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"  {m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
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
            if pointwise_matches:
                print("\nPointwise combination matches:")
                for m in pointwise_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
                    if m.combined_terms:
                        extra += f" result={_fmt_terms(m.combined_terms)}"
                    print(f"  {m.expression} len={m.length} score={m.score:.2f} [{'; '.join(name_parts)}]{extra}")
            if conv_matches:
                print("\nConvolution combination matches:")
                for m in conv_matches:
                    name_parts = [f"{id_}{f' - {nm}' if nm else ''}" for id_, nm in zip(m.ids, m.names)]
                    extra = ""
                    if m.component_terms:
                        extra = f" terms1={_fmt_terms(m.component_terms[0])} terms2={_fmt_terms(m.component_terms[1])}"
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


def _parse_oeis_ids(text: str) -> list[str]:
    """
    Parse a comma/space-separated list of OEIS ids like "A000045,A000204".
    Invalid tokens are ignored.
    """
    if not text:
        return []
    raw = [p.strip().upper() for p in text.replace(" ", ",").split(",") if p.strip()]
    out: list[str] = []
    for tok in raw:
        if len(tok) == 7 and tok.startswith("A") and tok[1:].isdigit():
            out.append(tok)
    # De-dupe while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for tok in out:
        if tok in seen:
            continue
        seen.add(tok)
        uniq.append(tok)
    return uniq


def _parse_pointwise_ops(text: str) -> list[str]:
    allowed = {"mul", "gcd", "lcm"}
    return [p for p in (t.strip().lower() for t in text.split(",")) if p in allowed]


def _parse_conv_ops(text: str) -> list[str]:
    allowed = {"cauchy", "dirichlet"}
    return [p for p in (t.strip().lower() for t in text.split(",")) if p in allowed]


def _parse_extra_transforms(text: str) -> dict:
    names = {s.strip().lower() for s in text.split(",") if s.strip()}
    movsum_windows: list[int] = []
    mod_values: list[int] = []
    digit_bases: list[int] = []
    for n in names:
        if n.startswith("movsum") and n[6:].isdigit():
            movsum_windows.append(int(n[6:]))
        if n.startswith("mod") and n[3:].lstrip("+-").isdigit():
            try:
                mod_values.append(int(n[3:]))
            except ValueError:
                pass
        if n.startswith("digitsum") and n[8:].isdigit():
            try:
                digit_bases.append(int(n[8:]))
            except ValueError:
                pass
        if n in ("log2", "log10", "loge"):
            pass
        if n.startswith("exp") and n[3:].lstrip("+-").isdigit():
            pass
    return {
        "diff2": "diff2" in names,
        "cumprod": "cumprod" in names,
        "popcount": "popcount" in names,
        "digitsum": "digitsum" in names or any(n.startswith("digitsum") for n in names),
        "reverse": "reverse" in names,
        "evenodd": "evenodd" in names,
        "movsum2": "movsum2" in names,
        "binomial": "binomial" in names,
        "euler": "euler" in names,
        "mobius": "mobius" in names,
        "rle_dec": "rledec" in names or "rle_dec" in names,
        "movsum_windows": tuple(sorted(set(movsum_windows))),
        "mod_values": tuple(sorted(set(mod_values))),
        "digit_bases": tuple(sorted(set(digit_bases))),
        "xor_index": "xorindex" in names,
        "rle": "rle" in names,
        "concat": "concat" in names,
        "log_bases": tuple(
            sorted(
                {
                    2.0 if n == "log2" else 10.0 if n == "log10" else math.e
                    for n in names
                    if n in ("log2", "log10", "loge")
                }
            )
        ),
        "exp_bases": tuple(
            sorted(
                {
                    float(n[3:])
                    for n in names
                    if n.startswith("exp") and n[3:].lstrip("+-").isdigit()
                }
            )
        ),
        "omega": "omega" in names,
        "bigomega": "bigomega" in names,
        "tau": "tau" in names,
        "sigma": "sigma" in names,
        "phi": "phi" in names,
        "v2": "v2" in names,
        "index_square": "indexsquare" in names,
        "prime_index": "primeindex" in names,
        "index_pow2": "indexpow2" in names,
        "index_factorial": "indexfactorial" in names,
    }


def main(argv=None):
    try:
        return _main(argv)
    except BrokenPipeError:
        # Common when piping to tools like `head`; avoid noisy tracebacks.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
