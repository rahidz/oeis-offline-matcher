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


def test_cli_selfcheck_runs_docs_regressions(tmp_path: Path):
    db = _mini_db(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "selfcheck",
            "--db",
            str(db),
            "--regressions",
            str(repo_root / "docs" / "regressions.json"),
            "--json",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["regressions"]["summary"]["fails"] == 0, payload


def test_cli_preset_max_enables_pointwise_and_convolution(tmp_path: Path):
    db = _mini_db(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "analyze",
            "1,2,3,4,5,6",
            "--db",
            str(db),
            "--max",
            "--json",
            "--time-cap",
            "2.0",
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
    convolution = payload.get("convolution_combinations") or []

    assert pointwise, payload
    assert any((m.get("ids") or []) == ["A000012", "A000012"] for m in convolution), payload


def test_cli_selfcheck_supports_pointwise_and_convolution_trials(tmp_path: Path):
    # Ensure the CLI flags are wired through and the trial types run end-to-end.
    # Use a tiny deterministic DB so the random sampler is stable.
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A800000 1,2,3,4,5,6,7,8,9,10,11,12",
                "A800001 2,3,4,5,6,7,8,9,10,11,12,13",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A800000 A\nA800001 B\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=32)

    repo_root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "selfcheck",
            "--db",
            str(db),
            "--no-regressions",
            "--random-trials",
            "0",
            "--pointwise-trials",
            "2",
            "--convolution-trials",
            "2",
            "--seed",
            "0",
            "--qlen",
            "8",
            "--min-length",
            "8",
            "--pointwise-max-time",
            "2.0",
            "--convolution-max-time",
            "2.0",
            "--json",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    trial = payload.get("random_trials") or {}
    summary = trial.get("summary") or {}
    assert summary.get("fails") == 0, payload
    assert summary.get("trials") == 4, payload
