"""
Command helpers to build the OEIS SQLite index.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Optional

from .oeis_data import (
    DEFAULT_MAX_TERMS,
    attach_formulas,
    attach_keywords,
    attach_offsets,
    attach_titles,
    load_formulas,
    load_formulas_from_oeisdata,
    load_keywords,
    load_keywords_from_oeisdata,
    load_names,
    load_offsets,
    load_offsets_from_oeisdata,
    load_stripped,
)
from .storage import ensure_db_indexes, init_db, write_records


def _replace_database(temp_path: Path, db_path: Path) -> None:
    if not db_path.exists():
        os.replace(temp_path, db_path)
        return

    # A WAL file belongs to the inode it was created for. Replacing the main DB
    # while another connection still owns that WAL can make new readers replay
    # old frames against the new file. Move the old DB briefly to DELETE mode
    # and hold an exclusive lock across the rename; if a reader is active, abort
    # and leave the existing database untouched.
    try:
        with closing(sqlite3.connect(db_path, timeout=5.0)) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint and checkpoint[0]:
                raise RuntimeError("existing database is busy; build completed but was not installed")
            if conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise RuntimeError("could not prepare existing database for atomic replacement")
            conn.execute("BEGIN EXCLUSIVE")
            os.replace(temp_path, db_path)
    except sqlite3.OperationalError:
        raise
    except sqlite3.DatabaseError:
        # A corrupt/non-SQLite destination cannot have a usable SQLite reader
        # to coordinate with. Discard stale sidecars and install the valid build.
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
        os.replace(temp_path, db_path)


def build_index(
    stripped_path: Path,
    names_path: Optional[Path],
    keywords_path: Optional[Path],
    db_path: Path,
    *,
    oeisdata_root: Optional[Path] = None,
    offsets_path: Optional[Path] = None,
    formulas_path: Optional[Path] = None,
    max_terms: int = DEFAULT_MAX_TERMS,
) -> dict:
    """
    Build SQLite index from stripped/names files. Returns stats dict.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    titles = load_names(names_path) if names_path and names_path.exists() else {}
    keywords = load_keywords(keywords_path) if keywords_path and keywords_path.exists() else {}
    if not keywords and oeisdata_root and oeisdata_root.exists():
        keywords = load_keywords_from_oeisdata(oeisdata_root)

    offsets = (
        load_offsets(offsets_path)
        if offsets_path and offsets_path.exists()
        else load_offsets_from_oeisdata(oeisdata_root) if oeisdata_root and oeisdata_root.exists() else {}
    )
    formulas = (
        load_formulas(formulas_path)
        if formulas_path and formulas_path.exists()
        else load_formulas_from_oeisdata(oeisdata_root)
        if oeisdata_root and oeisdata_root.exists()
        else {}
    )

    records = attach_titles(load_stripped(stripped_path, max_terms=max_terms), titles)
    records = attach_keywords(records, keywords)
    records = attach_offsets(records, offsets)
    records = attach_formulas(records, formulas)

    temp_path = db_path.with_name(f".{db_path.name}.build-{os.getpid()}-{uuid.uuid4().hex}.tmp")
    try:
        init_db(temp_path, create_indexes=False)
        inserted = write_records(records, temp_path)
        ensure_db_indexes(temp_path)
        with closing(sqlite3.connect(temp_path)) as conn:
            checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint and checkpoint[0]:
                raise RuntimeError(f"could not checkpoint temporary database: {checkpoint}")
        _replace_database(temp_path, db_path)
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{temp_path}{suffix}").unlink(missing_ok=True)

    return {"inserted": inserted, "db": str(db_path)}
