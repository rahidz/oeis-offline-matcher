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


def _run_cli(repo_root: Path, argv: list[str]) -> dict:
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


def test_analyze_global_time_cap_can_be_set_to_zero(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    payload = _run_cli(
        repo_root,
        [
            "analyze",
            "1,2,3,4,5,6",
            "--db",
            str(db),
            "--json",
            "--time-cap",
            "0",
        ],
    )
    assert payload["exact_matches"] == []
    assert payload["similarity"] == []
    assert payload["transform_matches"] == []
    assert payload["combinations"] == []
    assert payload["triple_combinations"] == []
    assert payload["pointwise_combinations"] == []
    assert payload["convolution_combinations"] == []


def test_combo_global_time_cap_can_be_set_to_zero(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    payload = _run_cli(
        repo_root,
        [
            "combo",
            "0,2,6,12,20,30",
            "--db",
            str(db),
            "--json",
            "--time-cap",
            "0",
        ],
    )
    assert payload["combinations"] == []
    assert payload["triple_combinations"] == []
    assert payload["pointwise_combinations"] == []
