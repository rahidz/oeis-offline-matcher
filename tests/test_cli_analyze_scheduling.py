from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from oeis_matcher.build_index import build_index


def _mini_db(tmp_path: Path) -> Path:
    base = Path(__file__).parent / "data" / "mini_oeis"
    db = tmp_path / "oeis.db"
    build_index(base / "stripped.txt", base / "names.txt", base / "keywords.txt", db, max_terms=20)
    return db


def _run(repo_root: Path, argv: list[str]) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli", *argv],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_analyze_max_profile_runs_via_lean_surface(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    payload = _run(
        repo_root,
        [
            "analyze",
            "0,2,6,12,20,30",
            "--db",
            str(db),
            "--max",
            "--json",
            "--time-cap",
            "3.0",
        ],
    )
    assert payload.get("query") == [0, 2, 6, 12, 20, 30]
    assert isinstance(payload.get("transform_matches"), list)
    assert isinstance(payload.get("combinations"), list)
    assert isinstance(payload.get("pointwise_combinations"), list)
    assert isinstance(payload.get("convolution_combinations"), list)


def test_analyze_without_profile_defaults_to_deep_profile(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    default_payload = _run(
        repo_root,
        [
            "analyze",
            "0,2,6,12,20,30",
            "--db",
            str(db),
            "--json",
            "--time-cap",
            "3.0",
        ],
    )
    deep_payload = _run(
        repo_root,
        [
            "analyze",
            "0,2,6,12,20,30",
            "--db",
            str(db),
            "--deep",
            "--json",
            "--time-cap",
            "3.0",
        ],
    )
    for key in (
        "exact_matches",
        "transform_matches",
        "similarity",
        "combinations",
        "triple_combinations",
        "pointwise_combinations",
        "convolution_combinations",
        "combined_combinations",
        "ranked_explanations",
    ):
        assert default_payload.get(key) == deep_payload.get(key)
