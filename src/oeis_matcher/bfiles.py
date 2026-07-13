"""
Helpers for OEIS b-file fetch/index/search workflows.
"""

from __future__ import annotations

import shutil
import sqlite3
import urllib.request
from pathlib import Path
from typing import Iterator


def bfile_url(seq_id: str, *, base_url: str = "https://oeis.org") -> str:
    return f"{base_url.rstrip('/')}/{seq_id}/b{seq_id[1:]}.txt"


def bfile_relpath(seq_id: str) -> Path:
    return Path(f"A{seq_id[1:4]}") / f"b{seq_id[1:]}.txt"


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.readline().strip() == "version https://git-lfs.github.com/spec/v1"
    except OSError:
        return False


def fetch_bfiles(
    seq_ids: list[str],
    *,
    dest_root: Path,
    force: bool = False,
    base_url: str = "https://oeis.org",
) -> dict:
    dest_root = Path(dest_root)
    rows: list[dict] = []
    downloaded = 0
    skipped = 0
    failed = 0
    for seq_id in seq_ids:
        dest = dest_root / bfile_relpath(seq_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not force:
            skipped += 1
            rows.append({"id": seq_id, "status": "skipped", "path": str(dest)})
            continue

        url = bfile_url(seq_id, base_url=base_url)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
                shutil.copyfileobj(resp, out, length=64 * 1024)
            tmp.replace(dest)
            downloaded += 1
            rows.append({"id": seq_id, "status": "downloaded", "path": str(dest), "url": url, "bytes": int(dest.stat().st_size)})
        except Exception as exc:
            failed += 1
            tmp.unlink(missing_ok=True)
            rows.append({"id": seq_id, "status": "failed", "path": str(dest), "url": url, "error": str(exc)})

    return {
        "dest_root": str(dest_root),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "files": rows,
    }


def iter_bfile_paths(files_root: Path) -> Iterator[tuple[str, Path]]:
    files_root = Path(files_root)
    if not files_root.exists():
        return
    for path in sorted(files_root.rglob("b*.txt")):
        name = path.name.lower()
        if len(name) < 8 or name[0] != "b":
            continue
        digits = name[1:7]
        if not digits.isdigit():
            continue
        if len(name) > 11 and name[7] != "_":
            continue
        yield f"A{digits}", path


def _iter_bfile_values(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                yield int(parts[0]), str(int(parts[1]))
            except ValueError:
                continue


def init_bfile_db(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS bfile_values")
        conn.execute(
            """
            CREATE TABLE bfile_values (
                seq_id TEXT NOT NULL,
                n INTEGER NOT NULL,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX idx_bfile_value ON bfile_values(value)")
        conn.execute("CREATE INDEX idx_bfile_seq_n ON bfile_values(seq_id, n)")
        conn.commit()


def build_bfile_index(files_root: Path, db_path: Path, *, batch_size: int = 50000) -> dict:
    files_root = Path(files_root)
    db_path = Path(db_path)
    init_bfile_db(db_path)

    files_seen = 0
    files_indexed = 0
    lfs_pointers = 0
    rows_written = 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        batch: list[tuple[str, int, str]] = []
        for seq_id, path in iter_bfile_paths(files_root):
            files_seen += 1
            if _is_lfs_pointer(path):
                lfs_pointers += 1
                continue

            has_rows = False
            for n, value in _iter_bfile_values(path):
                batch.append((seq_id, n, value))
                has_rows = True
                if len(batch) >= batch_size:
                    conn.executemany("INSERT INTO bfile_values(seq_id, n, value) VALUES (?, ?, ?)", batch)
                    rows_written += len(batch)
                    batch.clear()
            if has_rows:
                files_indexed += 1

        if batch:
            conn.executemany("INSERT INTO bfile_values(seq_id, n, value) VALUES (?, ?, ?)", batch)
            rows_written += len(batch)
        conn.commit()

    return {
        "files_root": str(files_root),
        "db": str(db_path),
        "files_seen": files_seen,
        "files_indexed": files_indexed,
        "lfs_pointers": lfs_pointers,
        "rows_written": rows_written,
    }


def search_bfile_index(db_path: Path, value: str, *, limit: int = 20) -> dict:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    value_txt = str(int(str(value).strip()))
    with sqlite3.connect(db_path) as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM bfile_values WHERE value = ?", (value_txt,)).fetchone()[0])
        rows = conn.execute(
            "SELECT seq_id, n FROM bfile_values WHERE value = ? ORDER BY seq_id ASC, n ASC LIMIT ?",
            (value_txt, int(limit)),
        ).fetchall()

    return {
        "value": value_txt,
        "total": total,
        "matches": [{"id": str(seq_id), "n": int(n)} for seq_id, n in rows],
        "limit": int(limit),
        "truncated": total > int(limit),
    }
