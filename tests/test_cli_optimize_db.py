from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _make_oldish_db(tmp_path: Path) -> Path:
    """
    Create a minimal 'older-style' DB that has the columns we need for
    ensure_db_indexes(), but lacks the newer composite indexes.
    """
    db = tmp_path / "oeis_old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE sequences (
                id TEXT PRIMARY KEY,
                length INTEGER NOT NULL,
                terms TEXT NOT NULL,
                name TEXT,
                sign_pattern TEXT,
                first_diff_sign TEXT
            )
            """
        )
        conn.execute("CREATE INDEX idx_sign ON sequences(sign_pattern)")
        conn.execute("CREATE INDEX idx_first_diff ON sequences(first_diff_sign)")
        conn.executemany(
            "INSERT INTO sequences (id, length, terms, name, sign_pattern, first_diff_sign) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("A000001", 5, "1,1,1,1,1", "ones", "nonneg", "flat"),
                ("A000002", 5, "1,2,3,4,5", "naturals", "nonneg", "pos"),
            ],
        )
        conn.commit()
    return db


def test_cli_optimize_db_creates_composite_indexes(tmp_path: Path):
    db = _make_oldish_db(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "optimize-db",
            "--db",
            str(db),
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
    created = payload.get("created") or []
    assert "idx_sign_id" in created, payload
    assert "idx_first_diff_id" in created, payload

    with sqlite3.connect(db) as conn:
        names = {row[1] for row in conn.execute("PRAGMA index_list(sequences)").fetchall()}
    assert "idx_sign_id" in names
    assert "idx_first_diff_id" in names

