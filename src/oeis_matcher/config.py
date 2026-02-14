from __future__ import annotations

import os
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "paths": {
        "stripped": "data/raw/stripped.gz",
        "names": "data/raw/names.gz",
        "keywords": "data/raw/keywords.txt",
        "db": "data/processed/oeis.db",
    },
    "limits": {
        "max_terms": 128,
        "max_results": 10,
        "variance_band": 50.0,
        "growth_band": 4.0,
    },
    "freshness": {
        "max_age_days": 30.0,
        "metadata_path": "data/processed/freshness.json",
        "warn_on_stale": True,
    },
    "startup": {
        "show_status": True,
        "refresh_if_stale": False,
    },
}


def _deep_update(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """
    Load configuration from:
      1) defaults,
      2) TOML file (config.toml or path provided),
      3) environment overrides.
    """
    cfg = deepcopy(DEFAULT_CONFIG)

    # Choose config path
    env_path = os.environ.get("OEIS_MATCHER_CONFIG")
    path = Path(env_path) if env_path else (config_path or Path("config.toml"))
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _deep_update(cfg, data)

    # Environment overrides (simple, flat)
    overrides = {
        "paths": {
            "stripped": os.environ.get("OEIS_STRIPPED_PATH"),
            "names": os.environ.get("OEIS_NAMES_PATH"),
            "db": os.environ.get("OEIS_DB_PATH"),
        },
        "limits": {
            "max_terms": _parse_int(os.environ.get("OEIS_MAX_TERMS")),
            "max_results": _parse_int(os.environ.get("OEIS_MAX_RESULTS")),
            "variance_band": _parse_float(os.environ.get("OEIS_VARIANCE_BAND")),
            "growth_band": _parse_float(os.environ.get("OEIS_GROWTH_BAND")),
        },
        "freshness": {
            "max_age_days": _parse_float(os.environ.get("OEIS_FRESHNESS_MAX_AGE_DAYS")),
            "metadata_path": os.environ.get("OEIS_FRESHNESS_METADATA_PATH"),
            "warn_on_stale": _parse_bool(os.environ.get("OEIS_WARN_ON_STALE_DATA")),
        },
        "startup": {
            "show_status": _parse_bool(os.environ.get("OEIS_STARTUP_SHOW_STATUS")),
            "refresh_if_stale": _parse_bool(os.environ.get("OEIS_STARTUP_REFRESH_IF_STALE")),
        },
    }
    _deep_update(cfg, {k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in overrides.items()})

    return cfg


def _parse_int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _parse_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _parse_bool(val: str | None) -> bool | None:
    if val is None:
        return None
    txt = val.strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return None
