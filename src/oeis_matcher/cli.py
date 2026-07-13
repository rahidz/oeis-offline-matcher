from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import math
import os
import shlex
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from fractions import Fraction

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
        "exact_max_time": 2.0,
        "similarity_max_time": 1.0,
        "candidate_max_time": 1.0,
        "combo_candidate_max_time": 1.0,
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
        "exact_max_time": 10.0,
        "similarity_max_time": 10.0,
        "candidate_max_time": 15.0,
        "combo_candidate_max_time": 15.0,
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
        "exact_max_time": 120.0,
        "similarity_max_time": 180.0,
        "candidate_max_time": 300.0,
        "combo_candidate_max_time": 300.0,
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
        # Optional symbolic/numeric candidate discovery (combo/analyze).
        "discovery": True,
        "discovery_limit": 16,
        "discovery_max_time": 3.0,
        "discovery_tools": "sympy",
        "combo_discovery": True,
        "combo_discovery_limit": 16,
        "combo_discovery_max_time": 3.0,
        "combo_discovery_tools": "sympy",
        "wide_prefilter": True,
        "combo_wide_prefilter": True,
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
        if isinstance(action, argparse.BooleanOptionalAction):
            if val is True:
                pos = [o for o in opts if not o.startswith("--no-")]
                if pos:
                    return max(pos, key=len)
            if val is False:
                neg = [o for o in opts if o.startswith("--no-")]
                if neg:
                    return max(neg, key=len)
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
        if isinstance(action, argparse.BooleanOptionalAction):
            if val is True or val is False:
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


_SEARCH_CMDS = {"match", "tsearch", "combo", "analyze"}
_PROFILE_BY_FLAG = {"--fast": "fast", "--deep": "deep", "--max": "max"}
_LEAN_ALLOWED_VALUE_FLAGS = {"--db", "--time-cap"}
_LEAN_ALLOWED_BOOL_FLAGS = {"--json", "--fast", "--deep", "--max"}


def _rewrite_search_argv(argv: list[str]) -> tuple[list[str], str | None]:
    """
    Enforce lean CLI flags for search commands and map shorthand profiles to `--preset`.

    Accepted search flags:
    - `--db`
    - `--json`
    - `--fast|--deep|--max`
    - `--time-cap`
    """
    if not argv:
        return argv, None
    cmd = argv[0]
    if cmd not in _SEARCH_CMDS:
        return argv, None
    if any(tok in {"-h", "--help"} for tok in argv[1:]):
        return argv, None

    out: list[str] = [cmd]
    profile: str | None = None
    positionals: list[str] = []
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok in _PROFILE_BY_FLAG:
            p = _PROFILE_BY_FLAG[tok]
            if profile is not None and profile != p:
                return argv, "Choose only one profile: use exactly one of --fast, --deep, --max."
            profile = p
            i += 1
            continue
        if tok in _LEAN_ALLOWED_BOOL_FLAGS:
            out.append(tok)
            i += 1
            continue
        if tok in _LEAN_ALLOWED_VALUE_FLAGS:
            if i + 1 >= len(argv):
                return argv, f"Missing value for {tok}."
            out.extend([tok, argv[i + 1]])
            i += 2
            continue
        if any(tok.startswith(flag + "=") for flag in _LEAN_ALLOWED_VALUE_FLAGS):
            out.append(tok)
            i += 1
            continue
        if tok.startswith("--"):
            allowed = sorted(_LEAN_ALLOWED_BOOL_FLAGS | _LEAN_ALLOWED_VALUE_FLAGS)
            allow_txt = " ".join(allowed)
            return argv, f"Unsupported flag for `{cmd}`: {tok}. Allowed flags: {allow_txt}"
        positionals.append(tok)
        i += 1

    if positionals:
        if cmd == "match":
            # Allow unquoted multi-token fielded queries.
            out.append(" ".join(positionals))
        else:
            if len(positionals) != 1:
                extra = " ".join(positionals[1:])
                return argv, f"Unexpected token(s) for `{cmd}`: {extra}"
            out.append(positionals[0])
    out.extend(["--preset", profile or "deep"])
    return out, None


def _apply_time_cap_overrides(args) -> None:
    """
    Map the top-level `--time-cap` knob onto existing per-command budget knobs.
    """
    cap = getattr(args, "time_cap", None)
    if cap is None:
        return
    try:
        cap_val = max(0.0, float(cap))
    except (TypeError, ValueError):
        return
    if args.cmd == "tsearch":
        cur = getattr(args, "max_time", None)
        args.max_time = cap_val if cur is None else min(float(cur), cap_val)
        return
    if args.cmd in {"combo", "analyze"}:
        cur = getattr(args, "total_max_time", None)
        args.total_max_time = cap_val if cur is None else min(float(cur), cap_val)


def _suppress_advanced_search_flags(parser, keep: set[str]) -> None:
    """
    Keep search help concise by showing only a small, preset-first surface.
    """
    for action in getattr(parser, "_actions", []):
        opts = list(getattr(action, "option_strings", []))
        if not opts:
            continue
        if action.dest == "help":
            continue
        if any(opt in keep for opt in opts):
            continue
        action.help = argparse.SUPPRESS


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_compatible(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(v) for v in value]
    return str(value)


def _db_marker(path: Path) -> dict:
    p = Path(path)
    marker = {"path": str(p)}
    if not p.exists():
        marker.update({"exists": False, "bytes": None, "mtime_ns": None})
        return marker
    st = p.stat()
    marker.update(
        {
            "exists": True,
            "bytes": int(st.st_size),
            "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
        }
    )
    return marker


def _checkpoint_context(args, *, query_terms: list[int | None], db_path: Path) -> dict:
    ignored = {
        "checkpoint",
        "resume",
        "as_json",
        "stream",
        "timings",
    }
    arg_ctx: dict[str, object] = {}
    for key, val in vars(args).items():
        if key in ignored:
            continue
        # Allow resume runs to use different time budgets while keeping all
        # other search-shaping options fixed.
        if key.endswith("_max_time"):
            continue
        arg_ctx[key] = _json_compatible(val)
    return {
        "cmd": "analyze",
        "query_terms": list(query_terms),
        "db": _db_marker(db_path),
        "args": arg_ctx,
    }


def _read_checkpoint(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _new_checkpoint(context: dict) -> dict:
    now = _utc_now_iso()
    return {
        "schema_version": 1,
        "created_utc": now,
        "updated_utc": now,
        "context": context,
        "stages": {},
    }


def _checkpoint_compatible(state: dict, *, context: dict) -> bool:
    return int(state.get("schema_version") or 0) == 1 and (state.get("context") == context)


def _checkpoint_get(state: dict | None, stage: str) -> dict | None:
    if not state:
        return None
    stages = state.get("stages")
    if not isinstance(stages, dict):
        return None
    entry = stages.get(stage)
    return entry if isinstance(entry, dict) else None


def _checkpoint_put(state: dict | None, stage: str, payload: dict) -> None:
    if not state:
        return
    stages = state.setdefault("stages", {})
    if not isinstance(stages, dict):
        return
    stages[stage] = payload
    state["updated_utc"] = _utc_now_iso()


def _matches_to_checkpoint(matches: list) -> list[dict]:
    return [asdict(m) for m in matches]


def _matches_from_checkpoint(rows: list[dict]) -> list:
    out: list[Match] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            out.append(Match(**row))
        except TypeError:
            continue
    return out


def _coeff_from_json(value):
    s = str(value)
    if "/" in s:
        num, den = s.split("/", 1)
        try:
            return Fraction(int(num), int(den))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def _combo_to_checkpoint(m) -> dict:
    row = {
        "ids": list(m.ids),
        "names": list(m.names),
        "coeffs": [_fmt_coeff_json(c) for c in m.coeffs],
        "shifts": list(m.shifts),
        "length": int(m.length),
        "score": float(m.score),
        "expression": m.expression,
    }
    if m.component_transforms is not None:
        row["component_transforms"] = list(m.component_transforms)
    if m.latex_expression is not None:
        row["latex_expression"] = m.latex_expression
    if m.component_terms is not None:
        row["component_terms"] = [list(ts) for ts in m.component_terms]
    if m.combined_terms is not None:
        row["combined_terms"] = list(m.combined_terms)
    if m.candidate_provenance is not None:
        row["candidate_provenance"] = [list(rs) for rs in m.candidate_provenance]
    return row


def _combo_from_checkpoint(row: dict) -> CombinationMatch | None:
    if not isinstance(row, dict):
        return None
    try:
        ids = tuple(str(x) for x in row.get("ids") or [])
        names = tuple((str(x) if x is not None else None) for x in (row.get("names") or []))
        coeffs = tuple(_coeff_from_json(c) for c in (row.get("coeffs") or []))
        shifts = tuple(int(s) for s in (row.get("shifts") or []))
        component_transforms = row.get("component_transforms")
        component_terms = row.get("component_terms")
        combined_terms = row.get("combined_terms")
        candidate_provenance = row.get("candidate_provenance")
        return CombinationMatch(
            ids=ids,
            names=names,
            coeffs=coeffs,
            shifts=shifts,
            length=int(row.get("length") or 0),
            score=float(row.get("score") or 0.0),
            expression=str(row.get("expression") or ""),
            component_transforms=tuple(str(t) for t in component_transforms) if component_transforms is not None else None,
            latex_expression=(str(row.get("latex_expression")) if row.get("latex_expression") is not None else None),
            component_terms=tuple([int(v) for v in ts] for ts in component_terms) if component_terms is not None else None,
            combined_terms=[int(v) for v in combined_terms] if combined_terms is not None else None,
            candidate_provenance=(
                tuple(tuple(str(x) for x in rs) for rs in candidate_provenance)
                if candidate_provenance is not None
                else None
            ),
        )
    except (TypeError, ValueError):
        return None


def _combos_from_checkpoint(rows: list[dict]) -> list[CombinationMatch]:
    out: list[CombinationMatch] = []
    for row in rows:
        m = _combo_from_checkpoint(row)
        if m is not None:
            out.append(m)
    return out


def _attach_combo_candidate_provenance(
    matches: list[CombinationMatch],
    provenance: dict[str, list[str]] | None,
) -> list[CombinationMatch]:
    if not matches or not provenance:
        return matches
    out: list[CombinationMatch] = []
    for m in matches:
        prov = tuple(tuple(sorted(set(provenance.get(seq_id, [])))) for seq_id in m.ids)
        out.append(replace(m, candidate_provenance=(prov if any(prov) else None)))
    return out

from .combination_search import (
    merge_combination_families,
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
from .models import CombinationMatch, Match, SequenceRecord
from .ranking import rank_candidates_for_query
from .candidates import get_candidate_bucket
from .query import QueryParseError, parse_query
from .transform_search import search_transform_matches
from .transforms import default_transforms
from .sync import DEFAULT_NAMES_URL, DEFAULT_OEISDATA_REPO, DEFAULT_STRIPPED_URL, sync_data
from .storage import ensure_db_indexes, get_sequence_by_id, iter_sequences
from .freshness import build_status_report, update_build_metadata, update_sync_metadata
from .explanation_ranking import parse_family_quotas, rerank_explanations
from .bfiles import build_bfile_index, fetch_bfiles, search_bfile_index


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

    def _add_lean_search_flags(p) -> None:
        grp = p.add_mutually_exclusive_group()
        grp.add_argument("--fast", action="store_true", help="Use the fast preset.")
        grp.add_argument("--deep", action="store_true", help="Use the deep preset.")
        grp.add_argument("--max", action="store_true", help="Use the max preset (widest/exhaustive search).")
        p.add_argument("--time-cap", type=float, default=None, help="Global wall-time cap in seconds.")

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

    p_bfetch = sub.add_parser("bfetch", help="Download canonical OEIS b-files for specific ids.")
    p_bfetch.add_argument("ids", help='Comma/space-separated OEIS ids (e.g., "A000045,A000217").')
    p_bfetch.add_argument("--dest", default="data/raw/bfiles", help="Destination directory for downloaded b-files")
    p_bfetch.add_argument("--base-url", default="https://oeis.org", help="Base URL for b-file downloads")
    p_bfetch.add_argument("--force", action="store_true", help="Re-download files even if already present")
    p_bfetch.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")

    p_bindex = sub.add_parser("bindex", help="Build a value index from local b-files.")
    p_bindex.add_argument("--files-root", default="data/raw/bfiles", help="Root directory containing b-files")
    p_bindex.add_argument("--db", default="data/processed/bfiles.db", help="Output SQLite path for b-file value index")
    p_bindex.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")

    p_bsearch = sub.add_parser("bsearch", help="Search for a value in indexed b-files.")
    p_bsearch.add_argument("value", help="Integer value to search for")
    p_bsearch.add_argument("--db", default="data/processed/bfiles.db", help="SQLite path built by `oeis bindex`")
    p_bsearch.add_argument("--limit", type=int, default=20, help="Maximum matches to print")
    p_bsearch.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")

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
    p_match.add_argument(
        "sequence",
        help='Comma/space-separated integers, or fielded query like "keyword:more name:fibonacci term@0:1".',
    )
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
    _add_lean_search_flags(p_match)

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
        help="Comma list of optional transforms. Examples: diff2,cumprod,altsign,reverse,evenodd,movsum3,binomial,invbinomial,euler,eulerogf,inveulerogf,stirling1,stirling2,invstirling1,invstirling2,ogfinv,seriesrev,mobius,rle,rledec,concat,digitsum10,popcount,mod2,xorindex,log2,log10,loge,exp2,omega,bigomega,tau,sigma,phi,v2,vp3,lpf,gpf,rad,squarefree,liouville,ratioint,indexsquare,primeindex,indexpow2,indexfactorial,indextri,indexfib,indexpowk3. Also supports patterns: movsumK, digitsumB, modM, expB, vpP, indexpowkK.",
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
    _add_lean_search_flags(p_tsearch)

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
    p_combo.add_argument(
        "--candidate-max-time",
        type=float,
        default=None,
        help="Max wall time (seconds) for combo candidate-bucket building stage",
    )
    p_combo.add_argument(
        "--discovery",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable optional symbolic/numeric candidate discovery (SymPy-backed).",
    )
    p_combo.add_argument("--discovery-limit", type=int, default=16, help="Max discovered candidate ids to inject.")
    p_combo.add_argument(
        "--discovery-max-time",
        type=float,
        default=2.0,
        help="Max wall time (seconds) for discovery stage during candidate-bucket building.",
    )
    p_combo.add_argument(
        "--discovery-tools",
        default="sympy",
        help="Comma-separated discovery backends (currently: sympy).",
    )
    p_combo.add_argument(
        "--wide-prefilter",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Widen invariant/prefix prefilters for difficult combo queries (slower, broader).",
    )
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
    _add_lean_search_flags(p_combo)

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
        help="Comma list of optional transforms. Examples: diff2,cumprod,altsign,reverse,evenodd,movsum3,binomial,invbinomial,euler,eulerogf,inveulerogf,stirling1,stirling2,invstirling1,invstirling2,ogfinv,seriesrev,mobius,rle,rledec,concat,digitsum10,popcount,mod2,xorindex,log2,log10,loge,exp2,omega,bigomega,tau,sigma,phi,v2,vp3,lpf,gpf,rad,squarefree,liouville,ratioint,indexsquare,primeindex,indexpow2,indexfactorial,indextri,indexfib,indexpowk3. Also supports patterns: movsumK, digitsumB, modM, expB, vpP, indexpowkK.",
    )
    p_analyze.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    p_analyze.add_argument("--show-terms", type=int, metavar="N", help="Include first N terms of each hit")
    p_analyze.add_argument("--show-formula", action="store_true", help="Include FORMULA text when available")
    p_analyze.add_argument("--exact-max-time", type=float, default=None, help="Max wall time (seconds) for exact-match stage")
    p_analyze.add_argument("--similar", type=int, default=0, help="Return top N similarity-ranked candidates (scale+offset).")
    p_analyze.add_argument("--similarity-max-time", type=float, default=None, help="Max wall time (seconds) for similarity stage")
    p_analyze.add_argument("--min-corr", type=float, default=None, help="Minimum correlation for similarity candidates")
    p_analyze.add_argument("--max-mse", type=float, default=None, help="Maximum MSE for similarity candidates")
    p_analyze.add_argument("--variance-band", type=float, default=None, help="Variance band for candidate filtering (overrides config)")
    p_analyze.add_argument("--growth-band", type=float, default=None, help="Growth-rate band for candidate filtering")
    p_analyze.add_argument("--combos", type=int, default=0, help="Return up to N two-sequence combinations (experimental)")
    p_analyze.add_argument("--combo-candidates", type=int, default=40, help="Max candidate sequences to consider for combos")
    p_analyze.add_argument(
        "--combo-candidate-max-time",
        type=float,
        default=None,
        help="Max wall time (seconds) for combo candidate-bucket building stage",
    )
    p_analyze.add_argument(
        "--combo-discovery",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable optional symbolic/numeric discovery during combo candidate-bucket building.",
    )
    p_analyze.add_argument("--combo-discovery-limit", type=int, default=16, help="Max discovered candidate ids to inject.")
    p_analyze.add_argument(
        "--combo-discovery-max-time",
        type=float,
        default=2.0,
        help="Max wall time (seconds) for combo discovery stage.",
    )
    p_analyze.add_argument(
        "--combo-discovery-tools",
        default="sympy",
        help="Comma-separated discovery backends (currently: sympy).",
    )
    p_analyze.add_argument(
        "--combo-wide-prefilter",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Widen combo candidate prefilters for difficult queries (slower, broader).",
    )
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
    p_analyze.add_argument("--checkpoint", default="", help="Path to checkpoint JSON for persisted analyze stage results")
    p_analyze.add_argument("--resume", action="store_true", help="Resume from --checkpoint when context is compatible")
    p_analyze.add_argument(
        "--rerank",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable explanation reranking. Defaults to enabled for --preset deep|max.",
    )
    p_analyze.add_argument("--rerank-limit", type=int, default=0, help="Top-K explanations to keep after reranking (0 = auto).")
    p_analyze.add_argument(
        "--rerank-default-quota",
        type=int,
        default=1,
        help="Per-family quota for reranking pass (phase 1 fairness step).",
    )
    p_analyze.add_argument(
        "--rerank-quotas",
        default="",
        help="Comma-separated family quotas like transform=2,pointwise=1,convolution=1.",
    )
    p_analyze.set_defaults(combo_unfiltered=False, combo_expanded=False)
    _add_lean_search_flags(p_analyze)

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

    lean_keep = {"--db", "--json", "--fast", "--deep", "--max", "--time-cap"}
    _suppress_advanced_search_flags(p_match, lean_keep)
    _suppress_advanced_search_flags(p_tsearch, lean_keep)
    _suppress_advanced_search_flags(p_combo, lean_keep)
    _suppress_advanced_search_flags(p_analyze, lean_keep)

    # Expose subparser choices so `_expand_preset_argv` can map preset keys to real flags.
    global _SUBPARSER_CHOICES
    _SUBPARSER_CHOICES = dict(sub.choices)
    rewritten_argv, rewrite_err = _rewrite_search_argv(list(argv))
    if rewrite_err:
        print(rewrite_err, file=sys.stderr)
        return 2
    argv = _expand_preset_argv(rewritten_argv)
    args = parser.parse_args(argv)
    _apply_time_cap_overrides(args)

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

    if args.cmd == "bfetch":
        ids = _parse_oeis_ids(args.ids)
        if not ids:
            print("No valid OEIS ids found.")
            return 2
        stats = fetch_bfiles(
            ids,
            dest_root=Path(args.dest),
            force=bool(args.force),
            base_url=str(args.base_url),
        )
        exit_code = 2 if int(stats.get("failed") or 0) > 0 else 0
        if args.as_json:
            print(json.dumps(stats, indent=2))
            return exit_code
        print(
            f"bfetch: downloaded={stats['downloaded']} skipped={stats['skipped']} "
            f"failed={stats['failed']} -> {stats['dest_root']}"
        )
        for row in stats.get("files") or []:
            if row.get("status") == "failed":
                print(f"{row['id']}: failed ({row.get('error')})")
        return exit_code

    if args.cmd == "bindex":
        stats = build_bfile_index(Path(args.files_root), Path(args.db))
        if args.as_json:
            print(json.dumps(stats, indent=2))
            return 0
        print(
            f"bindex: files_seen={stats['files_seen']} files_indexed={stats['files_indexed']} "
            f"rows={stats['rows_written']} lfs_pointers={stats['lfs_pointers']} -> {stats['db']}"
        )
        if int(stats.get("lfs_pointers") or 0) > 0:
            print("Note: some files are Git LFS pointers; fetch real b-files first.")
        return 0

    if args.cmd == "bsearch":
        try:
            result = search_bfile_index(Path(args.db), args.value, limit=max(1, int(args.limit)))
        except FileNotFoundError:
            print(f"Missing DB: {args.db}")
            return 2
        except Exception as exc:
            print(f"bsearch failed: {exc}")
            return 2
        if args.as_json:
            print(json.dumps(result, indent=2))
            return 0
        print(f"value={result['value']} total={result['total']} db={args.db}")
        for row in result.get("matches") or []:
            print(f"{row['id']} n={row['n']}")
        if result.get("truncated"):
            extra = int(result["total"]) - len(result.get("matches") or [])
            print(f"... and {extra} more")
        return 0

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
        import time

        deadline_s: float | None = None
        if getattr(args, "time_cap", None) is not None:
            try:
                deadline_s = time.perf_counter() + max(0.0, float(args.time_cap))
            except (TypeError, ValueError):
                deadline_s = None

        def _timed_out() -> bool:
            return deadline_s is not None and time.perf_counter() >= deadline_s

        field_query, field_query_error = _parse_field_query(args.sequence)
        if field_query_error is not None:
            print(field_query_error)
            return 2
        if field_query is not None:
            db_path = Path(args.db)
            seqs = []
            for seq in iter_sequences(db_path):
                if _timed_out():
                    break
                if not _match_field_query(seq, field_query):
                    continue
                seqs.append(seq)
                if args.limit is not None and len(seqs) >= int(args.limit):
                    break
            is_keyword_only = _field_query_is_keyword_only(field_query)
            keyword_diag = field_query.keywords[0] if is_keyword_only and len(field_query.keywords) == 1 else None
            match_type = "keyword" if is_keyword_only else "fielded"
            if args.as_json:
                out = [
                    {
                        "id": s.id,
                        "name": s.name,
                        "match_type": match_type,
                        "offset": 0,
                        "length": s.length,
                        **({"keywords": s.keywords} if s.keywords is not None else {}),
                        **({"formula": s.formula} if args.show_formula and s.formula else {}),
                        **({"terms": s.terms[: args.show_terms]} if args.show_terms is not None else {}),
                    }
                    for s in seqs
                ]
                payload = {
                    "query": [],
                    "query_text": args.sequence,
                    "matches": out,
                    "similarity": [],
                    "diagnostics": {
                        "field_query": _field_query_to_dict(field_query),
                        **({"keyword_query": keyword_diag} if keyword_diag is not None else {}),
                        **({"timed_out": True} if _timed_out() else {}),
                    },
                }
                print(json.dumps(payload, indent=2))
            else:
                if not seqs:
                    if is_keyword_only and keyword_diag is not None:
                        print(f"No keyword matches found for '{keyword_diag}'.")
                    else:
                        print("No fielded matches found.")
                for s in seqs:
                    name = f" - {s.name}" if s.name else ""
                    keywords_disp = f" keywords={','.join(s.keywords)}" if s.keywords else ""
                    snippet = f" terms={','.join(str(t) for t in s.terms[: args.show_terms])}" if args.show_terms is not None else ""
                    formula_txt = _fmt_formula(s.formula) if args.show_formula else ""
                    formula_disp = f" formula={formula_txt}" if formula_txt else ""
                    if is_keyword_only and keyword_diag is not None:
                        label = f"keyword:{keyword_diag}"
                    else:
                        label = "fielded"
                    print(f"{s.id} [{label}] len={s.length}{name}{keywords_disp}{snippet}{formula_disp}")
            return 0

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
        if not matches and not args.subsequence and not args.no_subsequence_fallback and not _timed_out():
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
                deadline_s=deadline_s,
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
            if _timed_out():
                diag["timed_out"] = True
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
            allow_alt_sign=extras["alt_sign"],
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
            vp_values=extras["vp_values"],
            allow_lpf=extras["lpf"],
            allow_gpf=extras["gpf"],
            allow_rad=extras["rad"],
            allow_squarefree=extras["squarefree"],
            allow_liouville=extras["liouville"],
            allow_ratio_int=extras["ratio_int"],
            allow_index_square=extras["index_square"],
            allow_prime_index=extras["prime_index"],
            allow_index_pow2=extras["index_pow2"],
            allow_index_factorial=extras["index_factorial"],
            allow_index_triangular=extras["index_triangular"],
            allow_index_fibonacci=extras["index_fibonacci"],
            index_power_values=extras["index_power_values"],
            allow_inverse_binomial=extras["inv_binomial"],
            allow_euler_ogf=extras["euler_ogf"],
            allow_inverse_euler_ogf=extras["inv_euler_ogf"],
            allow_stirling1=extras["stirling1"],
            allow_stirling2=extras["stirling2"],
            allow_inverse_stirling1=extras["inv_stirling1"],
            allow_inverse_stirling2=extras["inv_stirling2"],
            allow_ogf_inverse=extras["ogf_inverse"],
            allow_series_reversion=extras["series_reversion"],
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
            return 0
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
            disc = "on" if bool(getattr(args, "discovery", False)) else "off"
            pref = "wide" if bool(getattr(args, "wide_prefilter", False)) else "default"
            print(
                f"Building candidate bucket (cap={cap}, mode={mode}, discovery={disc}, prefilter={pref})…",
                flush=True,
            )
        t0 = time.perf_counter()
        cand_cap = _cap_by_total(getattr(args, "candidate_max_time", None))
        if cand_cap is None:
            bucket_deadline_s = None
        elif cand_cap <= 0:
            bucket_deadline_s = time.perf_counter()
        else:
            bucket_deadline_s = time.perf_counter() + float(cand_cap)
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
            enable_discovery=bool(getattr(args, "discovery", False)),
            discovery_limit=int(getattr(args, "discovery_limit", 16)),
            discovery_max_time_s=getattr(args, "discovery_max_time", None),
            discovery_tools=tuple(_parse_transform_names(getattr(args, "discovery_tools", "sympy"))),
            widen_prefilter=bool(getattr(args, "wide_prefilter", False)),
        )
        candidate_provenance = bucket.provenance
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
                f"Candidate bucket: {len(records)} sequences "
                f"(exact={len(bucket.exact_ids)} similar={len(bucket.similar_ids)} discovery={len(bucket.discovery_ids)}){note}",
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
            combos = _attach_combo_candidate_provenance(combos, candidate_provenance)
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
                modclass_matches = _attach_combo_candidate_provenance(modclass_matches, candidate_provenance)
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
                pointwise_matches = _attach_combo_candidate_provenance(pointwise_matches, candidate_provenance)
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
                        pointwise_matches = _attach_combo_candidate_provenance(pointwise_matches, candidate_provenance)
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
                conv_matches = _attach_combo_candidate_provenance(conv_matches, candidate_provenance)
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
                    allow_self_reference=bool(getattr(args, "preset", "") == "max"),
                    on_match=(lambda m: print(_fmt_combo_line(m, show_coeffs=False), flush=True)) if stream_text else None,
                )
                triples = _attach_combo_candidate_provenance(triples, candidate_provenance)
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
                            triples = _attach_combo_candidate_provenance(triples, candidate_provenance)
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
                    combos = _attach_combo_candidate_provenance(combos, candidate_provenance)
                    if args.timings:
                        timings["expanded_pair_ms"] = 1000 * (time.perf_counter() - t1e)
                if stream_text and not combos:
                    print("  (none)", flush=True)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
        if args.as_json:
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
            combined_limit = max(
                int(getattr(args, "limit", 0) or 0),
                int(getattr(args, "triples", 0) or 0),
                int(getattr(args, "modclass", 0) or 0),
                int(getattr(args, "pointwise_limit", 0) or 0),
                int(getattr(args, "convolution_limit", 0) or 0),
                0,
            )
            combined_matches = merge_combination_families(
                {
                    "linear_pair": combos,
                    "linear_triple": triples,
                    "modclass": modclass_matches,
                    "pointwise": pointwise_matches,
                    "convolution": conv_matches,
                },
                limit=combined_limit if combined_limit > 0 else None,
                per_family_quota=1,
            )
            def _crow(m):
                return {
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
                    **(
                        {"candidate_provenance": [list(rs) for rs in m.candidate_provenance]}
                        if m.candidate_provenance
                        else {}
                    ),
                }

            out = [_crow(m) for m in combos]
            out3 = [_crow(m) for m in triples]
            out_modclass = [_crow(m) for m in modclass_matches]
            out_pw = [_crow(m) for m in pointwise_matches]
            out_conv = [_crow(m) for m in conv_matches]
            out_combined = [{"family": fam, **_crow(m)} for fam, m in combined_matches]
            print(
                json.dumps(
                    {
                        "query": query.terms,
                        "combinations": out,
                        "triple_combinations": out3,
                        "modclass_combinations": out_modclass,
                        "pointwise_combinations": out_pw,
                        "convolution_combinations": out_conv,
                        "combined_combinations": out_combined,
                        "diagnostics": {
                            **({"timings_ms": timings} if args.timings else {}),
                            "variance_band": args.variance_band,
                            "growth_band": args.growth_band,
                            "combined_combinations_count": len(combined_matches),
                            "candidate_bucket": {
                                "size": len(records),
                                "exact": len(bucket.exact_ids),
                                "similar": len(bucket.similar_ids),
                                "discovery": len(bucket.discovery_ids),
                                "provenance_counts": {
                                    reason: sum(1 for rs in bucket.provenance.values() if reason in rs)
                                    for reason in sorted({r for rs in bucket.provenance.values() for r in rs})
                                },
                                **(
                                    {"discovery_diagnostics": bucket.discovery_diagnostics}
                                    if bucket.discovery_diagnostics
                                    else {}
                                ),
                                **(
                                    {"provider_diagnostics": bucket.provider_diagnostics}
                                    if bucket.provider_diagnostics
                                    else {}
                                ),
                            },
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
        combo_stage_requested = bool(
            (args.modclass and int(args.modclass) > 0)
            or bool(getattr(args, "combos", 0))
            or bool(getattr(args, "triples", 0))
            or bool(getattr(args, "pointwise_limit", 0) > 0 and getattr(args, "pointwise_ops", ""))
            or bool(getattr(args, "convolution_limit", 0) > 0 and getattr(args, "convolution_ops", ""))
        )
        schedule_mode = "latency_first" if getattr(args, "preset", None) in ("deep", "max") else "default"
        transform_probe_used = False
        transform_probe_cap_s: float | None = None
        transform_refined = False
        checkpoint_path = Path(args.checkpoint) if str(getattr(args, "checkpoint", "")).strip() else None
        checkpoint_state: dict | None = None
        checkpoint_loaded = False
        checkpoint_resumed_stages: list[str] = []
        checkpoint_saved_stages: list[str] = []

        if checkpoint_path is not None:
            checkpoint_ctx = _checkpoint_context(args, query_terms=query.terms, db_path=db_path)
            if bool(getattr(args, "resume", False)) and checkpoint_path.exists():
                loaded = _read_checkpoint(checkpoint_path)
                if loaded and _checkpoint_compatible(loaded, context=checkpoint_ctx):
                    checkpoint_state = loaded
                    checkpoint_loaded = True
                else:
                    print(
                        f"Warning: checkpoint at {checkpoint_path} is incompatible with this analyze run; starting fresh.",
                        file=sys.stderr,
                    )
            if checkpoint_state is None:
                checkpoint_state = _new_checkpoint(checkpoint_ctx)
                try:
                    _write_checkpoint(checkpoint_path, checkpoint_state)
                except Exception as exc:
                    print(f"Warning: failed to initialize checkpoint {checkpoint_path}: {exc}", file=sys.stderr)
                    checkpoint_path = None
                    checkpoint_state = None
                    checkpoint_loaded = False

        def _cp_get(stage: str) -> dict | None:
            entry = _checkpoint_get(checkpoint_state, stage)
            if entry is not None:
                checkpoint_resumed_stages.append(stage)
            return entry

        def _cp_put(stage: str, payload: dict) -> None:
            if checkpoint_path is None:
                return
            _checkpoint_put(checkpoint_state, stage, payload)
            checkpoint_saved_stages.append(stage)
            try:
                _write_checkpoint(checkpoint_path, checkpoint_state or {})
            except Exception as exc:
                print(f"Warning: failed to write checkpoint {checkpoint_path}: {exc}", file=sys.stderr)

        # Exact matches (with optional fallback to subsequence)
        t0 = time.perf_counter()
        exact_cached = _cp_get("exact")
        if exact_cached is not None:
            exact_matches = _matches_from_checkpoint(list(exact_cached.get("matches") or []))
            fallback_used = bool(exact_cached.get("fallback_used"))
        else:
            exact_stage_cap = _cap_by_total(args.exact_max_time)
            if exact_stage_cap is None:
                exact_deadline_s = None
            elif exact_stage_cap <= 0:
                exact_deadline_s = time.perf_counter()
            else:
                exact_deadline_s = time.perf_counter() + float(exact_stage_cap)
            exact_matches = match_exact_db(
                query,
                db_path,
                limit=args.limit,
                snippet_len=args.show_terms,
                deadline_s=exact_deadline_s,
                time_fn=time.perf_counter,
            )
            fallback_used = False
            if (
                not exact_matches
                and not args.subsequence
                and not args.no_subsequence_fallback
                and (exact_deadline_s is None or time.perf_counter() < exact_deadline_s)
            ):
                try:
                    fb_query = parse_query(
                        args.sequence,
                        min_match_length=args.min_match_length,
                        allow_subsequence=True,
                    )
                except QueryParseError as e:
                    print(f"Invalid query (fallback): {e}")
                    return 2
                exact_matches = match_exact_db(
                    fb_query,
                    db_path,
                    limit=args.limit,
                    snippet_len=args.show_terms,
                    deadline_s=exact_deadline_s,
                    time_fn=time.perf_counter,
                )
                fallback_used = True
            _cp_put(
                "exact",
                {
                    "matches": _matches_to_checkpoint(exact_matches),
                    "fallback_used": bool(fallback_used),
                },
            )
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

        exclude_exact_from_derived = bool(getattr(args, "preset", None) in ("deep", "max") and exact_matches)
        excluded_exact_ids = {m.id for m in exact_matches} if exclude_exact_from_derived else set()

        def _transform_is_excluded(m) -> bool:
            return bool(excluded_exact_ids) and m.id in excluded_exact_ids

        def _combo_is_excluded(m) -> bool:
            return bool(excluded_exact_ids) and any(seq_id in excluded_exact_ids for seq_id in m.ids)

        def _filter_transform_matches(matches: list) -> list:
            if not excluded_exact_ids:
                return matches
            return [m for m in matches if not _transform_is_excluded(m)]

        def _filter_combo_matches(matches: list) -> list:
            if not excluded_exact_ids:
                return matches
            return [m for m in matches if not _combo_is_excluded(m)]

        def _filter_similarity_rows(rows: list[dict]) -> list[dict]:
            if not excluded_exact_ids:
                return rows
            return [row for row in rows if row.get("id") not in excluded_exact_ids]

        def _filter_candidate_bucket(bucket):
            if not excluded_exact_ids:
                return bucket
            filtered_records = [rec for rec in bucket.records if rec.id not in excluded_exact_ids]
            if len(filtered_records) == len(bucket.records):
                return bucket
            keep_ids = {rec.id for rec in filtered_records}
            return replace(
                bucket,
                exact_ids=[sid for sid in bucket.exact_ids if sid in keep_ids],
                transform_ids=[sid for sid in bucket.transform_ids if sid in keep_ids],
                similar_ids=[sid for sid in bucket.similar_ids if sid in keep_ids],
                discovery_ids=[sid for sid in bucket.discovery_ids if sid in keep_ids],
                records=filtered_records,
                provenance={sid: rs for sid, rs in bucket.provenance.items() if sid in keep_ids},
            )

        def _combo_on_match(show_coeffs: bool):
            if not stream_text:
                return None

            def _emit(m) -> None:
                if _combo_is_excluded(m):
                    return
                print(_fmt_combo_line(m, show_coeffs=show_coeffs), flush=True)

            return _emit

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
            allow_alt_sign=extras["alt_sign"],
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
            vp_values=extras["vp_values"],
            allow_lpf=extras["lpf"],
            allow_gpf=extras["gpf"],
            allow_rad=extras["rad"],
            allow_squarefree=extras["squarefree"],
            allow_liouville=extras["liouville"],
            allow_ratio_int=extras["ratio_int"],
            allow_index_square=extras["index_square"],
            allow_prime_index=extras["prime_index"],
            allow_index_pow2=extras["index_pow2"],
            allow_index_factorial=extras["index_factorial"],
            allow_index_triangular=extras["index_triangular"],
            allow_index_fibonacci=extras["index_fibonacci"],
            index_power_values=extras["index_power_values"],
            allow_inverse_binomial=extras["inv_binomial"],
            allow_euler_ogf=extras["euler_ogf"],
            allow_inverse_euler_ogf=extras["inv_euler_ogf"],
            allow_stirling1=extras["stirling1"],
            allow_stirling2=extras["stirling2"],
            allow_inverse_stirling1=extras["inv_stirling1"],
            allow_inverse_stirling2=extras["inv_stirling2"],
            allow_ogf_inverse=extras["ogf_inverse"],
            allow_series_reversion=extras["series_reversion"],
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
            if _transform_is_excluded(m):
                return
            key = (m.id, m.match_type)
            if key in printed_transform:
                return
            # Keep streaming output bounded even when full_scan produces many candidates.
            if args.tlimit is not None and printed_transform_count >= int(args.tlimit):
                return
            printed_transform[key] = (m.transform_desc or "", m.score)
            printed_transform_count += 1
            print(_fmt_transform_line(m), flush=True)

        transform_cached = _cp_get("transform")
        defer_transform_refine = False
        if stream_text:
            print("\nTransform matches:", flush=True)
        if transform_cached is not None:
            t_matches = _matches_from_checkpoint(list(transform_cached.get("matches") or []))
            t_matches = _filter_transform_matches(t_matches)
        elif args.tlimit and args.tlimit > 0 and (_remaining_s() is None or _remaining_s() > 0):
            transform_time_cap = _cap_by_total(args.transform_max_time)
            if transform_time_cap is not None and transform_time_cap <= 0:
                t_matches = []
            else:
                effective_transform_cap = transform_time_cap
                if schedule_mode == "latency_first" and combo_stage_requested:
                    probe_target = 5.0
                    if transform_time_cap is None:
                        effective_transform_cap = probe_target
                        defer_transform_refine = True
                    elif transform_time_cap > probe_target:
                        effective_transform_cap = probe_target
                        defer_transform_refine = True
                    if effective_transform_cap is not None:
                        transform_probe_cap_s = float(effective_transform_cap)
                        transform_probe_used = bool(defer_transform_refine)
                t_matches = search_transform_matches(
                    query,
                    db_path,
                    max_depth=args.max_depth,
                    transforms=transforms,
                    limit=args.tlimit,
                    snippet_len=combo_snip,
                    full_scan=args.preset in ("deep", "max"),
                    max_time_s=effective_transform_cap,
                    min_score=args.transform_min_score,
                    max_complexity=args.transform_max_complexity,
                    variance_band=args.variance_band,
                    growth_band=args.growth_band,
                    allow_constant_outputs=args.allow_constant_transforms,
                    on_match=_on_transform_match if stream_text else None,
                )
            t_matches = _filter_transform_matches(t_matches)
            if not defer_transform_refine:
                _cp_put("transform", {"matches": _matches_to_checkpoint(t_matches)})
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

        sim_cached = _cp_get("similarity")
        sim_rows: list[dict] = []
        if sim_cached is not None:
            sim_rows = [dict(r) for r in list(sim_cached.get("matches") or []) if isinstance(r, dict)]
        else:
            sim_matches: list = []
            sim_stage_cap = _cap_by_total(args.similarity_max_time)
            if args.similar and (_remaining_s() is None or _remaining_s() > 0):
                if sim_stage_cap is None:
                    sim_deadline_s = None
                elif sim_stage_cap <= 0:
                    sim_deadline_s = time.perf_counter()
                else:
                    sim_deadline_s = time.perf_counter() + float(sim_stage_cap)
                if sim_deadline_s is None or time.perf_counter() < sim_deadline_s:
                    sim_matches = rank_candidates_for_query(
                        query,
                        db_path,
                        top_k=args.similar,
                        min_corr=args.min_corr,
                        max_mse=args.max_mse,
                        variance_band=args.variance_band,
                        growth_band=args.growth_band,
                        deadline_s=sim_deadline_s,
                        time_fn=time.perf_counter,
                    )
            sim_rows = [
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
            sim_rows = _filter_similarity_rows(sim_rows)
            _cp_put("similarity", {"matches": sim_rows})
        sim_rows = _filter_similarity_rows(sim_rows)
        t2 = time.perf_counter()
        if args.timings and args.similar:
            timings["similarity_ms"] = 1000 * (t2 - t1)
        if stream_text and sim_rows:
            print("\nSimilarity candidates:", flush=True)
            for c in sim_rows:
                print(
                    f"  {c['id']} corr={float(c['corr']):.3f} mse={float(c['mse']):.3g} "
                    f"scale={float(c['scale']):.3g} offset={float(c['offset']):.3g} - {c.get('name')}",
                    flush=True,
                )
        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True
        modclass_cached = _cp_get("modclass") if args.modclass and int(args.modclass) > 0 else None
        modclass_matches: list = (
            _combos_from_checkpoint(list(modclass_cached.get("matches") or [])) if modclass_cached is not None else []
        )
        modclass_matches = _filter_combo_matches(modclass_matches)
        if modclass_cached is None and args.modclass and int(args.modclass) > 0 and (_remaining_s() is None or _remaining_s() > 0):
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
                    on_match=_combo_on_match(False),
                )
                modclass_matches = _filter_combo_matches(modclass_matches)
                _cp_put("modclass", {"matches": [_combo_to_checkpoint(m) for m in modclass_matches]})
                if stream_text and not modclass_matches:
                    print("  (none)", flush=True)
                if args.timings:
                    timings["modclass_ms"] = 1000 * (time.perf_counter() - mc_start)
                if args.total_max_time is not None and _remaining_s() == 0:
                    time_budget_exhausted = True
        combo_cached = _cp_get("combo") if args.combos else None
        triple_cached = _cp_get("triple") if args.triples else None
        pointwise_cached = _cp_get("pointwise") if (getattr(args, "pointwise_limit", 0) > 0 and args.pointwise_ops) else None
        conv_cached = _cp_get("convolution") if (getattr(args, "convolution_limit", 0) > 0 and args.convolution_ops) else None
        combo_matches: list = _combos_from_checkpoint(list(combo_cached.get("matches") or [])) if combo_cached is not None else []
        triple_matches: list = _combos_from_checkpoint(list(triple_cached.get("matches") or [])) if triple_cached is not None else []
        pointwise_matches: list = (
            _combos_from_checkpoint(list(pointwise_cached.get("matches") or [])) if pointwise_cached is not None else []
        )
        conv_matches: list = _combos_from_checkpoint(list(conv_cached.get("matches") or [])) if conv_cached is not None else []
        combo_matches = _filter_combo_matches(combo_matches)
        triple_matches = _filter_combo_matches(triple_matches)
        pointwise_matches = _filter_combo_matches(pointwise_matches)
        conv_matches = _filter_combo_matches(conv_matches)
        candidate_bucket_diag: dict[str, object] | None = None
        candidate_provenance_map: dict[str, list[str]] | None = None
        need_combo_compute = bool(args.combos) and combo_cached is None
        need_triple_compute = bool(args.triples) and triple_cached is None
        need_pointwise_compute = bool(getattr(args, "pointwise_limit", 0) > 0 and args.pointwise_ops) and pointwise_cached is None
        need_conv_compute = bool(getattr(args, "convolution_limit", 0) > 0 and args.convolution_ops) and conv_cached is None
        if (
            (need_combo_compute or need_triple_compute or need_pointwise_compute or need_conv_compute)
            and (_remaining_s() is None or _remaining_s() > 0)
        ):
            combo_coeffs = _parse_int_list(args.combo_coeffs)
            triple_candidates = args.triple_candidates or args.combo_candidates
            cap = max(args.combo_candidates, triple_candidates)
            comp_transforms = resolve_component_transforms(_parse_transform_names(args.combo_component_transforms))
            combo_snip = _choose_snippet_len(query.terms, args.show_terms)
            combo_cand_cap = _cap_by_total(args.combo_candidate_max_time)
            if combo_cand_cap is None:
                bucket_deadline_s = None
            elif combo_cand_cap <= 0:
                bucket_deadline_s = time.perf_counter()
            else:
                bucket_deadline_s = time.perf_counter() + float(combo_cand_cap)
            if stream_text:
                mode = "unfiltered" if args.combo_unfiltered else "prefix+invariants"
                disc = "on" if bool(getattr(args, "combo_discovery", False)) else "off"
                pref = "wide" if bool(getattr(args, "combo_wide_prefilter", False)) else "default"
                print(
                    f"\nBuilding combo candidate bucket (cap={cap}, mode={mode}, discovery={disc}, prefilter={pref})…",
                    flush=True,
                )
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
                enable_discovery=bool(getattr(args, "combo_discovery", False)),
                discovery_limit=int(getattr(args, "combo_discovery_limit", 16)),
                discovery_max_time_s=getattr(args, "combo_discovery_max_time", None),
                discovery_tools=tuple(_parse_transform_names(getattr(args, "combo_discovery_tools", "sympy"))),
                widen_prefilter=bool(getattr(args, "combo_wide_prefilter", False)),
            )
            bucket = _filter_candidate_bucket(bucket)
            candidate_provenance_map = bucket.provenance
            candidate_bucket_diag = {
                "size": len(bucket.records),
                "exact": len(bucket.exact_ids),
                "similar": len(bucket.similar_ids),
                "discovery": len(bucket.discovery_ids),
                "provenance_counts": {
                    reason: sum(1 for rs in bucket.provenance.values() if reason in rs)
                    for reason in sorted({r for rs in bucket.provenance.values() for r in rs})
                },
                **({"discovery_diagnostics": bucket.discovery_diagnostics} if bucket.discovery_diagnostics else {}),
                **({"provider_diagnostics": bucket.provider_diagnostics} if bucket.provider_diagnostics else {}),
            }
            if stream_text:
                note = ""
                if bucket_deadline_s is not None and time.perf_counter() >= bucket_deadline_s:
                    note = " (time-capped)"
                print(
                    f"Combo candidate bucket: {len(bucket.records)} sequences "
                    f"(exact={len(bucket.exact_ids)} similar={len(bucket.similar_ids)} discovery={len(bucket.discovery_ids)}){note}",
                    flush=True,
                )

            need_expanded_pairs = False
            expanded_pair_start = expanded_pair_end = None
            if need_combo_compute:
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
                        on_match=_combo_on_match(True),
                    )
                    combo_matches = _attach_combo_candidate_provenance(combo_matches, candidate_provenance_map)
                    combo_matches = _filter_combo_matches(combo_matches)
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
                    _cp_put("combo", {"matches": [_combo_to_checkpoint(m) for m in combo_matches]})
                combo_end = time.perf_counter()
            else:
                combo_start = combo_end = None

            pw_ops = _parse_pointwise_ops(getattr(args, "pointwise_ops", ""))
            if need_pointwise_compute and getattr(args, "pointwise_limit", 0) > 0 and pw_ops:
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
                        on_match=_combo_on_match(False),
                    )
                    pointwise_matches = _attach_combo_candidate_provenance(pointwise_matches, candidate_provenance_map)
                    pointwise_matches = _filter_combo_matches(pointwise_matches)
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
                                on_match=_combo_on_match(False),
                            )
                            pointwise_matches = _attach_combo_candidate_provenance(pointwise_matches, candidate_provenance_map)
                            pointwise_matches = _filter_combo_matches(pointwise_matches)
                            if args.timings:
                                timings["expanded_pointwise_ms"] = 1000 * (time.perf_counter() - t_pwe)
                    if stream_text and not pointwise_matches:
                        print("  (none)", flush=True)
                    _cp_put("pointwise", {"matches": [_combo_to_checkpoint(m) for m in pointwise_matches]})
                pw_end = time.perf_counter()
            else:
                pw_start = pw_end = None

            conv_ops = _parse_conv_ops(getattr(args, "convolution_ops", ""))
            if need_conv_compute and getattr(args, "convolution_limit", 0) > 0 and conv_ops:
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
                        on_match=_combo_on_match(False),
                    )
                    conv_matches = _attach_combo_candidate_provenance(conv_matches, candidate_provenance_map)
                    conv_matches = _filter_combo_matches(conv_matches)
                    if stream_text and not conv_matches:
                        print("  (none)", flush=True)
                    _cp_put("convolution", {"matches": [_combo_to_checkpoint(m) for m in conv_matches]})
                conv_end = time.perf_counter()
            else:
                conv_start = conv_end = None

            # Triples can be significantly more expensive than pair/pointwise/convolution
            # searches, so run them later to improve time-to-first-hit for simpler combo
            # explanations under `--preset max`.
            if need_triple_compute:
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
                        allow_self_reference=bool(getattr(args, "preset", "") == "max"),
                        on_match=_combo_on_match(False),
                    )
                    triple_matches = _attach_combo_candidate_provenance(triple_matches, candidate_provenance_map)
                    triple_matches = _filter_combo_matches(triple_matches)
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
                                    on_match=_combo_on_match(False),
                                )
                                triple_matches = _attach_combo_candidate_provenance(
                                    triple_matches, candidate_provenance_map
                                )
                                triple_matches = _filter_combo_matches(triple_matches)
                    if stream_text and not triple_matches:
                        print("  (none)", flush=True)
                    _cp_put("triple", {"matches": [_combo_to_checkpoint(m) for m in triple_matches]})
                triple_end = time.perf_counter()
            else:
                triple_start = triple_end = None

            if need_combo_compute and need_expanded_pairs and not combo_matches and not time_budget_exhausted and (_remaining_s() is None or _remaining_s() > 0):
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
                        on_match=_combo_on_match(True),
                    )
                    combo_matches = _attach_combo_candidate_provenance(combo_matches, candidate_provenance_map)
                    combo_matches = _filter_combo_matches(combo_matches)
                    _cp_put("combo", {"matches": [_combo_to_checkpoint(m) for m in combo_matches]})
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

        if candidate_provenance_map:
            combo_matches = _attach_combo_candidate_provenance(combo_matches, candidate_provenance_map)
            triple_matches = _attach_combo_candidate_provenance(triple_matches, candidate_provenance_map)
            pointwise_matches = _attach_combo_candidate_provenance(pointwise_matches, candidate_provenance_map)
            conv_matches = _attach_combo_candidate_provenance(conv_matches, candidate_provenance_map)
            modclass_matches = _attach_combo_candidate_provenance(modclass_matches, candidate_provenance_map)

        if defer_transform_refine and args.tlimit and args.tlimit > 0 and (_remaining_s() is None or _remaining_s() > 0):
            refine_cap = _cap_by_total(args.transform_max_time)
            if refine_cap is None or refine_cap > 0:
                t_refine = time.perf_counter()
                refined_matches = search_transform_matches(
                    query,
                    db_path,
                    max_depth=args.max_depth,
                    transforms=transforms,
                    limit=args.tlimit,
                    snippet_len=combo_snip,
                    full_scan=args.preset in ("deep", "max"),
                    max_time_s=refine_cap,
                    min_score=args.transform_min_score,
                    max_complexity=args.transform_max_complexity,
                    variance_band=args.variance_band,
                    growth_band=args.growth_band,
                    allow_constant_outputs=args.allow_constant_transforms,
                    on_match=None,
                )
                t_matches = _filter_transform_matches(refined_matches)
                transform_refined = True
                if args.timings:
                    refine_ms = 1000 * (time.perf_counter() - t_refine)
                    timings["transform_refine_ms"] = refine_ms
                    timings["transform_ms"] = timings.get("transform_ms", 0.0) + refine_ms
                _cp_put("transform", {"matches": _matches_to_checkpoint(t_matches)})
                if stream_text:
                    for m in t_matches:
                        key = (m.id, m.match_type)
                        cur = (m.transform_desc or "", m.score)
                        if printed_transform.get(key) != cur:
                            print(_fmt_transform_line(m), flush=True)
            else:
                _cp_put("transform", {"matches": _matches_to_checkpoint(t_matches)})
        elif defer_transform_refine:
            _cp_put("transform", {"matches": _matches_to_checkpoint(t_matches)})

        if args.total_max_time is not None and _remaining_s() == 0:
            time_budget_exhausted = True

        combined_limit = max(
            int(getattr(args, "combos", 0) or 0),
            int(getattr(args, "triples", 0) or 0),
            int(getattr(args, "modclass", 0) or 0),
            int(getattr(args, "pointwise_limit", 0) or 0),
            int(getattr(args, "convolution_limit", 0) or 0),
            0,
        )
        combined_matches = merge_combination_families(
            {
                "linear_pair": combo_matches,
                "linear_triple": triple_matches,
                "modclass": modclass_matches,
                "pointwise": pointwise_matches,
                "convolution": conv_matches,
            },
            limit=combined_limit if combined_limit > 0 else None,
            per_family_quota=1,
        )
        ranking_families = {
            "linear_pair": combo_matches,
            "linear_triple": triple_matches,
            "modclass": modclass_matches,
            "pointwise": pointwise_matches,
            "convolution": conv_matches,
        }
        if args.rerank is None:
            rerank_enabled = bool(getattr(args, "preset", None) in ("deep", "max"))
            rerank_mode = "auto_preset_deepmax" if rerank_enabled else "off_default"
        else:
            rerank_enabled = bool(args.rerank)
            rerank_mode = "explicit_on" if rerank_enabled else "explicit_off"

        auto_ranking_limit = max(
            int(getattr(args, "tlimit", 0) or 0),
            int(getattr(args, "combos", 0) or 0),
            int(getattr(args, "triples", 0) or 0),
            int(getattr(args, "modclass", 0) or 0),
            int(getattr(args, "pointwise_limit", 0) or 0),
            int(getattr(args, "convolution_limit", 0) or 0),
            0,
        )
        configured_ranking_limit = int(getattr(args, "rerank_limit", 0) or 0)
        ranking_limit = configured_ranking_limit if configured_ranking_limit > 0 else (auto_ranking_limit if auto_ranking_limit > 0 else None)
        default_quota = max(0, int(getattr(args, "rerank_default_quota", 1)))
        quota_overrides = parse_family_quotas(getattr(args, "rerank_quotas", ""))

        if rerank_enabled:
            ranked_explanations, ranking_info = rerank_explanations(
                transform_matches=t_matches,
                family_matches=ranking_families,
                limit=ranking_limit,
                default_quota=default_quota,
                quotas=quota_overrides,
                diversity=True,
            )
        else:
            ranked_explanations, ranking_info = rerank_explanations(
                transform_matches=t_matches,
                family_matches=ranking_families,
                limit=ranking_limit,
                default_quota=0,
                quotas={},
                diversity=False,
            )
        ranking_diag = {
            "enabled": rerank_enabled,
            "mode": rerank_mode,
            "configured_limit": configured_ranking_limit,
            "default_quota": default_quota,
            "quota_overrides": quota_overrides,
            **ranking_info,
        }
        scheduling_diag = {
            "mode": schedule_mode,
            "combo_stage_requested": combo_stage_requested,
            "transform_probe_used": transform_probe_used,
            "transform_refined": transform_refined,
            **({"transform_probe_cap_s": transform_probe_cap_s} if transform_probe_cap_s is not None else {}),
        }

        if args.as_json:
            def _crow(m):
                return {
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
                    **(
                        {"candidate_provenance": [list(rs) for rs in m.candidate_provenance]}
                        if m.candidate_provenance
                        else {}
                    ),
                }

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

            def _erow(fam: str, m):
                if fam == "transform":
                    row = {
                        "family": "transform",
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
                    return row
                return {"family": fam, **_crow(m)}

            payload = {
                "query": query.terms,
                "exact_matches": [_mrow(m) for m in exact_matches],
                "transform_matches": [_mrow(m) for m in t_matches],
                "similarity": sim_rows,
                "combinations": [_crow(m) for m in combo_matches],
                "triple_combinations": [_crow(m) for m in triple_matches],
                "modclass_combinations": [_crow(m) for m in modclass_matches],
                "pointwise_combinations": [_crow(m) for m in pointwise_matches],
                "convolution_combinations": [_crow(m) for m in conv_matches],
                "combined_combinations": [{"family": fam, **_crow(m)} for fam, m in combined_matches],
                "ranked_explanations": [_erow(fam, m) for fam, m in ranked_explanations],
            }
            if args.timings:
                timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                payload["diagnostics"] = {
                **({"timings_ms": timings} if args.timings else {}),
                "variance_band": args.variance_band,
                "growth_band": args.growth_band,
                "combined_combinations_count": len(combined_matches),
                "ranking": ranking_diag,
                "scheduling": scheduling_diag,
                **({"candidate_bucket": candidate_bucket_diag} if candidate_bucket_diag is not None else {}),
                **(
                    {
                        "checkpoint": {
                            "enabled": True,
                            "path": str(checkpoint_path),
                            "resumed": checkpoint_loaded,
                            "resumed_stages": checkpoint_resumed_stages,
                            "saved_stages": checkpoint_saved_stages,
                        }
                    }
                    if checkpoint_path is not None
                    else {}
                ),
                **({"subsequence_fallback": True} if fallback_used else {}),
                **({"time_budget_exhausted": True} if time_budget_exhausted else {}),
            }
            print(json.dumps(payload, indent=2))
        else:
            def _fmt_ranked_line(fam: str, m) -> str:
                if fam == "transform":
                    return _fmt_transform_line(m)
                show_coeffs = fam in {"linear_pair", "linear_triple"}
                return _fmt_combo_line(m, show_coeffs=show_coeffs)

            if stream_text:
                if time_budget_exhausted:
                    print("\n(Time budget reached; stopping early.)", flush=True)
                if ranked_explanations:
                    print("\nTop explanations:", flush=True)
                    for fam, m in ranked_explanations:
                        print(f"  [{fam}] {_fmt_ranked_line(fam, m).strip()}", flush=True)
                if args.timings:
                    timings["total_ms"] = 1000 * (time.perf_counter() - t_start)
                    print("\nTimings (ms):", flush=True)
                    for k, v in timings.items():
                        print(f"  {k}: {v:.1f}", flush=True)
                return 0
            if ranked_explanations:
                print("Top explanations:")
                for fam, m in ranked_explanations:
                    print(f"  [{fam}] {_fmt_ranked_line(fam, m).strip()}")
                print()
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

            if sim_rows:
                print("\nSimilarity candidates:")
                for c in sim_rows:
                    print(
                        f"  {c['id']} corr={float(c['corr']):.3f} mse={float(c['mse']):.3g} "
                        f"scale={float(c['scale']):.3g} offset={float(c['offset']):.3g} - {c.get('name')}"
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


@dataclass
class _FieldQuery:
    ids: list[str] = field(default_factory=list)
    name_substrings: list[str] = field(default_factory=list)
    formula_substrings: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    sign_pattern: str | None = None
    monotonic: str | None = None
    has_formula: bool | None = None
    contains_terms: list[int] = field(default_factory=list)
    excludes_terms: list[int] = field(default_factory=list)
    term_equals: list[tuple[int, int]] = field(default_factory=list)  # (0-based index, value)


def _parse_int_csv_strict(text: str) -> tuple[list[int] | None, str | None]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return [], None
    out: list[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            return None, f"Invalid integer list '{text}'."
    return out, None


def _parse_bool_strict(text: str) -> bool | None:
    t = text.strip().lower()
    if t in {"1", "true", "yes", "y", "on"}:
        return True
    if t in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _normalize_keyword_tag(text: str) -> str | None:
    kw = text.strip().lower()
    if not kw:
        return None
    if not all(ch.isalnum() or ch == "_" for ch in kw):
        return None
    return kw


def _normalize_sign_pattern(text: str) -> str | None:
    t = text.strip().lower()
    aliases = {
        "nonnegative": "nonneg",
        "nonneg": "nonneg",
        "nonpositive": "nonpos",
        "nonpos": "nonpos",
        "alternating": "alternating",
        "mixed": "mixed",
        "empty": "empty",
    }
    return aliases.get(t)


def _normalize_monotonic(text: str) -> str | None:
    t = text.strip().lower()
    aliases = {
        "nondecreasing": "nondecreasing",
        "increasing": "nondecreasing",
        "inc": "nondecreasing",
        "nonincreasing": "nonincreasing",
        "decreasing": "nonincreasing",
        "dec": "nonincreasing",
        "either": "either",
        "monotonic": "either",
    }
    return aliases.get(t)


def _parse_field_query(text: str) -> tuple[_FieldQuery | None, str | None]:
    """
    Parse fielded `oeis match` queries like:
      keyword:more
      name:fibonacci keyword:nonn sign:nonneg
      id:A000045 term@3:2 contains:1,2 excludes:0

    Returns:
    - (None, None): not a fielded query (fall back to numeric sequence parse).
    - (_FieldQuery, None): valid fielded query.
    - (None, error): malformed fielded query.
    """
    if ":" not in text:
        return None, None
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        return None, f"Invalid field query: {exc}"
    if not tokens:
        return None, None

    supported_fields = {
        "id",
        "name",
        "formula",
        "keyword",
        "sign",
        "monotonic",
        "hasformula",
        "has-formula",
        "contains",
        "excludes",
    }

    def _is_field_token(tok: str) -> bool:
        if ":" not in tok:
            return False
        key = tok.split(":", 1)[0].strip().lower()
        return key.startswith("term@") or (key in supported_fields)

    if not any(_is_field_token(tok) for tok in tokens):
        return None, None

    normalized_tokens: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if ":" in tok:
            k, v = tok.split(":", 1)
            if v == "" and i + 1 < len(tokens) and ":" not in tokens[i + 1]:
                normalized_tokens.append(f"{k}:{tokens[i + 1]}")
                i += 2
                continue
        normalized_tokens.append(tok)
        i += 1

    q = _FieldQuery()
    for tok in normalized_tokens:
        if ":" not in tok:
            return None, f"Invalid field query token '{tok}' (expected field:value)."
        key_raw, value_raw = tok.split(":", 1)
        key = key_raw.strip().lower()
        value = value_raw.strip()
        if not value:
            if key == "keyword":
                return None, "Invalid keyword query: use keyword:<tag> (example: keyword:more)"
            return None, f"Invalid field query token '{tok}' (empty value)."

        if key == "id":
            ids = _parse_oeis_ids(value)
            if not ids:
                return None, f"Invalid id filter '{tok}' (expected A123456 style ids)."
            q.ids.extend(ids)
            continue
        if key == "name":
            q.name_substrings.append(value.lower())
            continue
        if key == "formula":
            q.formula_substrings.append(value.lower())
            continue
        if key == "keyword":
            tags = [t.strip() for t in value.split(",") if t.strip()]
            if not tags:
                return None, "Invalid keyword query: use keyword:<tag> (example: keyword:more)"
            for tag in tags:
                norm = _normalize_keyword_tag(tag)
                if norm is None:
                    return None, f"Invalid keyword query: bad tag '{tag}'. Use letters/digits/_ only."
                q.keywords.append(norm)
            continue
        if key == "sign":
            norm = _normalize_sign_pattern(value)
            if norm is None:
                return None, f"Invalid sign filter '{tok}' (use nonneg|nonpos|alternating|mixed|empty)."
            q.sign_pattern = norm
            continue
        if key == "monotonic":
            norm = _normalize_monotonic(value)
            if norm is None:
                return None, f"Invalid monotonic filter '{tok}' (use nondecreasing|nonincreasing|either)."
            q.monotonic = norm
            continue
        if key in {"hasformula", "has-formula"}:
            b = _parse_bool_strict(value)
            if b is None:
                return None, f"Invalid has-formula filter '{tok}' (use true|false)."
            q.has_formula = b
            continue
        if key == "contains":
            vals, err = _parse_int_csv_strict(value)
            if err is not None:
                return None, f"{err} (from '{tok}')"
            q.contains_terms.extend(vals or [])
            continue
        if key == "excludes":
            vals, err = _parse_int_csv_strict(value)
            if err is not None:
                return None, f"{err} (from '{tok}')"
            q.excludes_terms.extend(vals or [])
            continue
        if key.startswith("term@"):
            idx_text = key[5:]
            if not idx_text.isdigit():
                return None, f"Invalid term@index filter '{tok}' (index must be a nonnegative integer)."
            try:
                term_val = int(value)
            except ValueError:
                return None, f"Invalid term@index filter '{tok}' (value must be an integer)."
            q.term_equals.append((int(idx_text), term_val))
            continue
        return None, f"Unsupported field '{key_raw}' in token '{tok}'."

    if (
        not q.ids
        and not q.name_substrings
        and not q.formula_substrings
        and not q.keywords
        and q.sign_pattern is None
        and q.monotonic is None
        and q.has_formula is None
        and not q.contains_terms
        and not q.excludes_terms
        and not q.term_equals
    ):
        return None, "Empty field query."
    return q, None


def _field_query_to_dict(q: _FieldQuery) -> dict:
    return {
        "ids": q.ids,
        "name_substrings": q.name_substrings,
        "formula_substrings": q.formula_substrings,
        "keywords": q.keywords,
        "sign_pattern": q.sign_pattern,
        "monotonic": q.monotonic,
        "has_formula": q.has_formula,
        "contains_terms": q.contains_terms,
        "excludes_terms": q.excludes_terms,
        "term_equals": [{"index0": i, "value": v} for i, v in q.term_equals],
    }


def _field_query_is_keyword_only(q: _FieldQuery) -> bool:
    return bool(q.keywords) and (
        not q.ids
        and not q.name_substrings
        and not q.formula_substrings
        and q.sign_pattern is None
        and q.monotonic is None
        and q.has_formula is None
        and not q.contains_terms
        and not q.excludes_terms
        and not q.term_equals
    )


def _sign_pattern_for_terms(terms: list[int]) -> str:
    if not terms:
        return "empty"
    all_nonneg = all(v >= 0 for v in terms)
    all_nonpos = all(v <= 0 for v in terms)
    if all_nonneg:
        return "nonneg"
    if all_nonpos:
        return "nonpos"
    alt = all(terms[i] == 0 or terms[i + 1] == 0 or (terms[i] > 0) != (terms[i + 1] > 0) for i in range(len(terms) - 1))
    if alt:
        return "alternating"
    return "mixed"


def _match_field_query(rec: SequenceRecord, q: _FieldQuery) -> bool:
    if q.ids and rec.id not in q.ids:
        return False

    nm = (rec.name or "").lower()
    for frag in q.name_substrings:
        if frag not in nm:
            return False

    fm = (rec.formula or "").lower()
    for frag in q.formula_substrings:
        if frag not in fm:
            return False

    rec_kw = {k.lower() for k in (rec.keywords or [])}
    for tag in q.keywords:
        if tag not in rec_kw:
            return False

    has_formula = bool(rec.formula or rec.has_formula)
    if q.has_formula is not None and has_formula != q.has_formula:
        return False

    if q.sign_pattern is not None and _sign_pattern_for_terms(rec.terms) != q.sign_pattern:
        return False

    if q.monotonic is not None:
        nondecr = all(rec.terms[i] <= rec.terms[i + 1] for i in range(len(rec.terms) - 1))
        nonincr = all(rec.terms[i] >= rec.terms[i + 1] for i in range(len(rec.terms) - 1))
        if q.monotonic == "nondecreasing" and not nondecr:
            return False
        if q.monotonic == "nonincreasing" and not nonincr:
            return False
        if q.monotonic == "either" and not (nondecr or nonincr):
            return False

    terms_set = set(rec.terms)
    for v in q.contains_terms:
        if v not in terms_set:
            return False
    for v in q.excludes_terms:
        if v in terms_set:
            return False
    for idx0, v in q.term_equals:
        if idx0 < 0 or idx0 >= len(rec.terms) or rec.terms[idx0] != v:
            return False

    return True


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
    vp_values: list[int] = []
    index_power_values: list[int] = []
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
        if n.startswith("vp") and n[2:].isdigit():
            try:
                p = int(n[2:])
                if p > 1:
                    vp_values.append(p)
            except ValueError:
                pass
        if n.startswith("indexpowk") and n[9:].isdigit():
            try:
                k = int(n[9:])
                if k >= 2:
                    index_power_values.append(k)
            except ValueError:
                pass
    return {
        "diff2": "diff2" in names,
        "cumprod": "cumprod" in names,
        "popcount": "popcount" in names,
        "digitsum": "digitsum" in names or any(n.startswith("digitsum") for n in names),
        "alt_sign": "altsign" in names or "alt_sign" in names,
        "reverse": "reverse" in names,
        "evenodd": "evenodd" in names,
        "movsum2": "movsum2" in names,
        "binomial": "binomial" in names,
        "inv_binomial": "invbinomial" in names or "inv_binomial" in names,
        "euler": "euler" in names,
        "euler_ogf": "eulerogf" in names or "euler_ogf" in names,
        "inv_euler_ogf": "inveulerogf" in names or "inv_euler_ogf" in names,
        "stirling1": "stirling1" in names,
        "stirling2": "stirling2" in names,
        "inv_stirling1": "invstirling1" in names or "inv_stirling1" in names,
        "inv_stirling2": "invstirling2" in names or "inv_stirling2" in names,
        "ogf_inverse": "ogfinv" in names or "ogf_inverse" in names or "ogf_inv" in names,
        "series_reversion": "seriesrev" in names or "seriesreversion" in names or "series_reversion" in names,
        "mobius": "mobius" in names,
        "rle_dec": "rledec" in names or "rle_dec" in names,
        "movsum_windows": tuple(sorted(set(movsum_windows))),
        "mod_values": tuple(sorted(set(mod_values))),
        "digit_bases": tuple(sorted(set(digit_bases))),
        "vp_values": tuple(sorted(set(vp_values))),
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
        "lpf": "lpf" in names,
        "gpf": "gpf" in names,
        "rad": "rad" in names,
        "squarefree": "squarefree" in names,
        "liouville": "liouville" in names,
        "ratio_int": "ratioint" in names or "ratio_int" in names,
        "index_square": "indexsquare" in names,
        "prime_index": "primeindex" in names,
        "index_pow2": "indexpow2" in names,
        "index_factorial": "indexfactorial" in names,
        "index_triangular": "indextriangular" in names or "indextri" in names,
        "index_fibonacci": "indexfibonacci" in names or "indexfib" in names,
        "index_power_values": tuple(sorted(set(index_power_values))),
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
