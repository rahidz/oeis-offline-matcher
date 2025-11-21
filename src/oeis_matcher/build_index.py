"""
Command helpers to build the OEIS SQLite index.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .oeis_data import DEFAULT_MAX_TERMS, attach_titles, load_names, load_stripped
from .storage import init_db, write_records


def build_index(
    stripped_path: Path,
    names_path: Optional[Path],
    db_path: Path,
    *,
    max_terms: int = DEFAULT_MAX_TERMS,
) -> dict:
    """
    Build SQLite index from stripped/names files. Returns stats dict.
    """
    titles = load_names(names_path) if names_path and names_path.exists() else {}
    records = attach_titles(load_stripped(stripped_path, max_terms=max_terms), titles)

    init_db(db_path)
    inserted = write_records(records, db_path)

    return {"inserted": inserted, "db": str(db_path)}
