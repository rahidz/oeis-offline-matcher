"""
Command helpers to build the OEIS SQLite index.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .oeis_data import (
    DEFAULT_MAX_TERMS,
    attach_titles,
    attach_keywords,
    attach_offsets,
    attach_formulas,
    load_names,
    load_keywords,
    load_keywords_from_oeisdata,
    load_stripped,
    load_offsets,
    load_offsets_from_oeisdata,
    load_formulas,
    load_formulas_from_oeisdata,
)
from .storage import ensure_db_indexes, init_db, write_records


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

    init_db(db_path, create_indexes=False)
    inserted = write_records(records, db_path)
    ensure_db_indexes(db_path)

    return {"inserted": inserted, "db": str(db_path)}
