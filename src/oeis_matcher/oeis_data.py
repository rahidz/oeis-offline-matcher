"""
Parsing helpers for OEIS exported files.

The OEIS "stripped" format uses lines like:
  A000045 0,1,1,2,3,5,8,13,21

The "names" file uses:
  A000045 Fibonacci numbers
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, TextIO, Tuple

from .models import SequenceRecord

DEFAULT_MAX_TERMS = 128


def _open_maybe_gzip(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def parse_stripped_line(line: str, *, max_terms: int = DEFAULT_MAX_TERMS) -> Optional[SequenceRecord]:
    """
    Parse a single stripped line into SequenceRecord.

    Returns None if the line is malformed or missing an id/terms.
    """
    line = line.strip()
    if not line:
        return None

    # Expect "A123456 terms..."
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        return None

    seq_id, terms_part = parts
    if not seq_id.startswith("A") or not seq_id[1:].isdigit():
        return None

    term_tokens = [t.strip() for t in terms_part.split(",") if t.strip()]
    terms: list[int] = []
    for token in term_tokens:
        try:
            terms.append(int(token))
        except ValueError:
            # Skip tokens that are not integers; keep whatever was parsed.
            continue
        if len(terms) >= max_terms:
            break

    if not terms:
        return None

    return SequenceRecord(id=seq_id, terms=terms, length=len(terms))


def parse_names_line(line: str) -> Optional[Tuple[str, str]]:
    """
    Parse a single names line into (id, title).
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        return None

    seq_id, title = parts
    if not seq_id.startswith("A") or not seq_id[1:].isdigit():
        return None

    return seq_id, title.strip()


def parse_keywords_line(line: str) -> Optional[Tuple[str, list[str]]]:
    """
    Parse a single keywords line of form 'A123456 nonn,easy,more'.
    """
    line = line.strip()
    if not line:
        return None
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        return None
    seq_id, kw_part = parts
    if not seq_id.startswith("A") or not seq_id[1:].isdigit():
        return None
    kws = [k.strip() for k in kw_part.split(",") if k.strip()]
    return seq_id, kws


def load_stripped(path: Path, *, max_terms: int = DEFAULT_MAX_TERMS) -> Iterator[SequenceRecord]:
    """
    Stream SequenceRecord objects from a stripped file (plain or .gz).
    """
    with _open_maybe_gzip(path) as f:
        for line in f:
            record = parse_stripped_line(line, max_terms=max_terms)
            if record:
                yield record


def load_keywords_from_oeisdata(root: Path) -> Dict[str, list[str]]:
    """
    Extract keywords from the oeisdata mirror.
    Looks for seq/KEYWORDS and parses KEYWORDS lines.
    """
    keywords_file = root / "seq" / "KEYWORDS"
    mapping: Dict[str, list[str]] = {}
    if not keywords_file.exists():
        return mapping
    with keywords_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("A"):
                continue
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            seq_id = parts[0]
            kw_str = parts[1]
            kws = [k for k in kw_str.split(",") if k]
            mapping[seq_id] = kws
    return mapping


def load_names(path: Path) -> Dict[str, str]:
    """
    Load id -> title mapping from names file (plain or .gz).
    """
    mapping: Dict[str, str] = {}
    with _open_maybe_gzip(path) as f:
        for line in f:
            parsed = parse_names_line(line)
            if parsed:
                seq_id, title = parsed
                mapping[seq_id] = title
    return mapping


def load_keywords(path: Path) -> Dict[str, list[str]]:
    """
    Load id -> list[keyword] mapping from keywords file (plain or .gz).
    """
    mapping: Dict[str, list[str]] = {}
    with _open_maybe_gzip(path) as f:
        for line in f:
            parsed = parse_keywords_line(line)
            if parsed:
                seq_id, kws = parsed
                mapping[seq_id] = kws
    return mapping


def attach_titles(records: Iterable[SequenceRecord], titles: Dict[str, str]) -> Iterator[SequenceRecord]:
    """
    Add names to records if available.
    """
    for rec in records:
        if rec.name is None and rec.id in titles:
            rec = SequenceRecord(
                id=rec.id,
                terms=rec.terms,
                length=rec.length,
                name=titles[rec.id],
                keywords=rec.keywords,
                metadata=rec.metadata,
            )
        yield rec


def attach_keywords(records: Iterable[SequenceRecord], keywords: Dict[str, list[str]]) -> Iterator[SequenceRecord]:
    """
    Add keywords to records if available.
    """
    for rec in records:
        if rec.keywords is None and rec.id in keywords:
            rec = SequenceRecord(
                id=rec.id,
                terms=rec.terms,
                length=rec.length,
                name=rec.name,
                keywords=keywords[rec.id],
                metadata=rec.metadata,
            )
        yield rec
