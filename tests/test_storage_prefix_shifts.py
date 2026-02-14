from __future__ import annotations

import sqlite3
from pathlib import Path

from oeis_matcher.storage import ensure_prefix_shifts


def test_ensure_prefix_shifts_adds_and_fills_columns(tmp_path: Path):
    db = tmp_path / "oeis.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE sequences (
                id TEXT PRIMARY KEY,
                length INTEGER NOT NULL,
                terms TEXT NOT NULL,
                prefix5 TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO sequences (id, length, terms, prefix5) VALUES (?, ?, ?, ?)",
            ("A000001", 7, "1,2,3,4,5,6,7", "1,2,3,4,5"),
        )
        conn.commit()

    stats = ensure_prefix_shifts(db, max_shift=2, batch_size=1)
    assert stats.get("added_columns") == ["prefix5_1", "prefix5_2"]
    assert stats.get("updated_rows") == 1

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT prefix5_1, prefix5_2 FROM sequences WHERE id = ?", ("A000001",)).fetchone()
    assert row == ("2,3,4,5,6", "3,4,5,6,7")

