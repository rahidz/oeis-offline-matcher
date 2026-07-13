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


def test_analyze_lean_profile_runs_with_json(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    payload = _run(
        repo_root,
        [
            "analyze",
            "1,2,3,4,5,6",
            "--db",
            str(db),
            "--json",
            "--max",
            "--time-cap",
            "1.0",
        ],
    )
    assert payload.get("query") == [1, 2, 3, 4, 5, 6]
    assert isinstance(payload.get("transform_matches"), list)
    assert isinstance(payload.get("combinations"), list)


def test_analyze_legacy_checkpoint_flag_rejected(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "analyze",
            "0,2,6,12,20,30",
            "--db",
            str(db),
            "--json",
            "--checkpoint",
            str(tmp_path / "ckpt.json"),
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 2
    assert "Unsupported flag for `analyze`: --checkpoint" in proc.stderr


def test_analyze_lean_profile_conflict_rejected(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _mini_db(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "analyze",
            "0,2,6,12,20,30",
            "--db",
            str(db),
            "--json",
            "--fast",
            "--max",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 2
    assert "Choose only one profile" in proc.stderr
