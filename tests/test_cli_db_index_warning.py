from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def _make_db_missing_composite_indexes(tmp_path: Path) -> Path:
    db = tmp_path / "oeis_old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE sequences (
                id TEXT PRIMARY KEY,
                length INTEGER NOT NULL,
                terms TEXT NOT NULL,
                name TEXT,
                prefix5 TEXT,
                sign_pattern TEXT,
                first_diff_sign TEXT
            )
            """
        )
        # Prefix index exists, but composite invariant indexes do not.
        conn.execute("CREATE INDEX idx_prefix5 ON sequences(prefix5)")
        conn.execute("CREATE INDEX idx_sign ON sequences(sign_pattern)")
        conn.execute("CREATE INDEX idx_first_diff ON sequences(first_diff_sign)")
        conn.executemany(
            "INSERT INTO sequences (id, length, terms, name, prefix5, sign_pattern, first_diff_sign) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("A000012", 10, "1,1,1,1,1,1,1,1,1,1", "ones", "1,1,1,1,1", "nonneg", "flat"),
                ("A000027", 10, "1,2,3,4,5,6,7,8,9,10", "naturals", "1,2,3,4,5", "nonneg", "pos"),
            ],
        )
        conn.commit()
    return db


@pytest.mark.parametrize("cmd", ["match", "tsearch", "combo", "analyze"])
def test_cli_warns_when_db_missing_recommended_indexes(tmp_path: Path, cmd: str):
    db = _make_db_missing_composite_indexes(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())

    if cmd == "match":
        args = [cmd, "1,1,1", "--db", str(db), "--time-cap", "0.1"]
    elif cmd == "tsearch":
        args = [cmd, "1,1,1,1,1", "--db", str(db), "--time-cap", "0.1"]
    elif cmd == "combo":
        args = [cmd, "2,3,4,5,6", "--db", str(db), "--time-cap", "0.1"]
    else:
        args = [cmd, "1,2,3,4,5", "--db", str(db), "--time-cap", "0.1"]

    proc = subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli", *args],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Tip: DB is missing recommended index(es)" in proc.stderr


def test_cli_does_not_warn_in_json_mode(tmp_path: Path):
    db = _make_db_missing_composite_indexes(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())

    proc = subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli", "match", "1,1,1", "--db", str(db), "--json"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == ""
