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


def test_cli_preset_max_enables_all_combo_stages(tmp_path: Path):
    db = _mini_db(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            "1,2,3,4,5",
            "--db",
            str(db),
            "--preset",
            "max",
            "--timings",
            "--json",
            # Keep runtime tiny; we only care that max preset activates the stages.
            "--max-time",
            "1.0",
            "--triple-max-time",
            "1.0",
            "--expanded-max-time",
            "0",
            "--max-checks",
            "20000",
            "--triple-max-checks",
            "20000",
            "--candidates",
            "30",
            "--triple-candidates",
            "30",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    diag = payload.get("diagnostics") or {}
    timings = diag.get("timings_ms") or {}
    assert "candidates_ms" in timings, timings
    assert "pair_ms" in timings, timings
    assert "pointwise_ms" in timings, timings
    assert "convolution_ms" in timings, timings
    assert "triples_ms" in timings, timings

    # These should be non-empty on this fixture (ones/naturals are present).
    assert payload.get("pointwise_combinations"), payload
    assert payload.get("convolution_combinations"), payload


def test_cli_preset_max_combo_enables_component_transforms(tmp_path: Path):
    # If preset max enables component transforms, pointwise search should be able
    # to explain naturals as n * diff(n) without the ones sequence existing in the DB.
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A000027 1,2,3,4,5,6,7,8,9,10\n", encoding="utf-8")
    names.write_text("A000027 Naturals\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    repo_root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            "1,2,3,4,5",
            "--db",
            str(db),
            "--preset",
            "max",
            "--json",
            "--triples",
            "0",
            "--convolution-ops",
            "",
            "--pointwise-ops",
            "mul",
            "--max-time",
            "0.75",
            "--max-checks",
            "100000",
            "--candidates",
            "20",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    pointwise = payload.get("pointwise_combinations") or []
    assert any(
        (m.get("ids") or []) == ["A000027", "A000027"] and ("diff" in (m.get("component_transforms") or []))
        for m in pointwise
    ), payload
