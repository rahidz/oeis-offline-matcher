"""Offline search text and incoming-reference counts from an oeisdata mirror.

Incoming references count distinct source entries mentioning a target A-number
in %C, %F, or %Y text. Self-links and repeated mentions count zero and once,
respectively. These are corpus connections, not independent interpretations or
external citations; %H navigation and adjacent entries are deliberately excluded.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path

ENTRY_GLOB = "A[0-9][0-9][0-9]/A[0-9][0-9][0-9][0-9][0-9][0-9].seq"
_ID = re.compile(r"\bA[0-9]{6}\b")
_FIELDS = {"C": "comments", "D": "references_text", "H": "links", "Y": "crossrefs"}


@contextmanager
def search_metadata_writer(db_path: Path):
    """Yield a per-entry consumer; replace the metadata atomically on success."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DROP TABLE IF EXISTS search_metadata_pending")
            conn.execute(
                "CREATE TABLE search_metadata_pending (id TEXT PRIMARY KEY, comments TEXT, "
                "references_text TEXT, links TEXT, crossrefs TEXT, inbound_links INTEGER NOT NULL DEFAULT 0)"
            )
            batch = []
            inbound = Counter()
            stats = {"available": False, "entries": 0, "reference_edges": 0}

            def flush():
                conn.executemany(
                    "INSERT INTO search_metadata_pending "
                    "(id, comments, references_text, links, crossrefs) VALUES (?, ?, ?, ?, ?)", batch
                )
                batch.clear()

            def consume(seq_id: str, lines: list[str]):
                fields = {field: [] for field in _FIELDS}
                targets = set()
                for line in lines:
                    parts = line.rstrip().split(maxsplit=2)
                    if len(parts) < 2 or not parts[0].startswith("%"):
                        continue
                    if parts[1] != seq_id:
                        raise ValueError(f"entry ID {parts[1]} does not match {seq_id}")
                    if len(parts) < 3:
                        continue
                    field = parts[0][1:]
                    if field in fields:
                        fields[field].append(parts[2])
                    if field in {"C", "F", "Y"}:
                        targets.update(_ID.findall(parts[2]))
                targets.discard(seq_id)
                inbound.update(targets)
                stats["reference_edges"] += len(targets)
                batch.append((seq_id, *("\n".join(fields[field]) for field in _FIELDS)))
                stats["entries"] += 1
                stats["available"] = True
                if len(batch) >= 1000:
                    flush()

            yield consume, stats
            if stats["available"]:
                flush()
                conn.executemany(
                    "UPDATE search_metadata_pending SET inbound_links=? WHERE id=?",
                    ((count, seq_id) for seq_id, count in inbound.items()),
                )
                conn.execute("DROP TABLE IF EXISTS search_metadata")
                conn.execute("ALTER TABLE search_metadata_pending RENAME TO search_metadata")
                # Replacing the table also removes its invalidation triggers.
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='search_profiles'").fetchone():
                    conn.execute("DELETE FROM search_profiles")
            else:
                conn.execute("DROP TABLE search_metadata_pending")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def build_search_metadata(db_path: Path, oeisdata_root: Path) -> dict:
    """Enrich an existing main DB; an absent/empty mirror leaves metadata intact."""
    db_path, oeisdata_root = Path(db_path), Path(oeisdata_root)
    if not db_path.is_file():
        raise FileNotFoundError(f"OEIS database not found: {db_path}")
    with search_metadata_writer(db_path) as (consume, stats):
        for path in sorted((oeisdata_root / "seq").glob(ENTRY_GLOB)):
            with path.open(encoding="utf-8") as source:
                consume(path.stem, source.readlines())
    return {**stats, "db": str(db_path), "source": str(oeisdata_root)}
