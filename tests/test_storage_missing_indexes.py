from __future__ import annotations

import sqlite3
from pathlib import Path

from oeis_matcher.storage import missing_recommended_indexes


def _make_oldish_db(tmp_path: Path) -> Path:
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
        # Old DBs might have the simple indexes but lack the composite variants.
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


def test_missing_recommended_indexes_detects_composite_indexes(tmp_path: Path):
    db = _make_oldish_db(tmp_path)
    missing = missing_recommended_indexes(db)
    assert "idx_sign_id" in missing
    assert "idx_first_diff_id" in missing
