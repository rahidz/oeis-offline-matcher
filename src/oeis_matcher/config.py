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
        "db": "data/processed/oeis.db",
    },
    "limits": {
        "max_terms": 128,
        "max_results": 10,
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
