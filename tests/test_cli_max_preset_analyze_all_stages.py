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


def _run_analyze(repo_root: Path, *, db: Path, query: str) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "analyze",
            query,
            "--db",
            str(db),
            "--preset",
            "max",
            "--json",
            "--timings",
            # Keep the test fast; the fixture DB is tiny so this should be ample.
            "--total-max-time",
            "5.0",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_preset_max_analyze_runs_all_stages_by_default(tmp_path: Path):
    db = _mini_db(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    # Case 1: pronic numbers should have both a linear combo explanation (n^2+n)
    # and a pointwise mul explanation (n*(n+1)) on the mini fixture.
    pronic = _run_analyze(repo_root, db=db, query="0,2,6,12,20,30")
    diag = pronic.get("diagnostics") or {}
    timings = diag.get("timings_ms") or {}
    for key in (
        "exact_ms",
        "transform_ms",
        "similarity_ms",
        "combination_ms",
        "triple_ms",
        "pointwise_ms",
        "convolution_ms",
        "total_ms",
    ):
        assert key in timings, timings
    assert pronic.get("combinations"), pronic
    assert pronic.get("pointwise_combinations"), pronic

    # Case 2: naturals should have a convolution explanation (ones * ones).
    naturals = _run_analyze(repo_root, db=db, query="1,2,3,4,5,6")
    assert naturals.get("convolution_combinations"), naturals
