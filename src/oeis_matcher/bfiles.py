"""Resumable b-file manifests and on-demand exact-value search."""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import USER_AGENT

BFILE_SCHEMA_VERSION = 3
_CANONICAL_NAME = re.compile(r"^b([0-9]{6})\.txt$", re.IGNORECASE)
_AUXILIARY_NAME = re.compile(r"^b[0-9]{6}_.+\.txt$", re.IGNORECASE)


def bfile_url(seq_id: str, *, base_url: str = "https://oeis.org") -> str:
    return f"{base_url.rstrip('/')}/{seq_id}/b{seq_id[1:]}.txt"


def bfile_relpath(seq_id: str) -> Path:
    return Path(f"A{seq_id[1:4]}") / f"b{seq_id[1:]}.txt"


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as source:
            return source.readline().strip() == "version https://git-lfs.github.com/spec/v1"
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
    downloaded = skipped = failed = 0
    for seq_id in seq_ids:
        dest = dest_root / bfile_relpath(seq_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not force and not _is_lfs_pointer(dest):
            skipped += 1
            rows.append({"id": seq_id, "status": "skipped", "path": str(dest)})
            continue

        url = bfile_url(seq_id, base_url=base_url)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request) as response, tmp.open("wb") as output:
                shutil.copyfileobj(response, output, length=64 * 1024)
            tmp.replace(dest)
            downloaded += 1
            rows.append({"id": seq_id, "status": "downloaded", "path": str(dest), "url": url, "bytes": dest.stat().st_size})
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
    """Yield canonical `bNNNNNN.txt` files; auxiliary variants are intentionally excluded."""
    files_root = Path(files_root)
    if not files_root.exists():
        return
    for path in files_root.rglob("b*.txt"):
        match = _CANONICAL_NAME.fullmatch(path.name)
        if match:
            yield f"A{match.group(1)}", path


def _metadata(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM bfile_meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else default


def init_bfile_db(db_path: Path, *, rebuild: bool = False) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = None
        if "bfile_meta" in tables:
            row = conn.execute("SELECT value FROM bfile_meta WHERE key = 'schema_version'").fetchone()
            version = str(row[0]) if row else None
        legacy = "bfile_values" in tables or ("bfiles" not in tables and bool(tables)) or version not in (None, str(BFILE_SCHEMA_VERSION))
        if rebuild or legacy:
            for table in ("bfile_values", "bfile_search_hits", "bfile_searches", "bfiles", "bfile_meta"):
                conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("CREATE TABLE IF NOT EXISTS bfile_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bfiles (
                seq_id TEXT PRIMARY KEY,
                relpath TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bfile_searches (
                value TEXT NOT NULL,
                generation INTEGER NOT NULL,
                total INTEGER NOT NULL,
                scan_seconds REAL NOT NULL,
                searched_utc TEXT NOT NULL,
                PRIMARY KEY (value, generation)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bfile_search_hits (
                value TEXT NOT NULL,
                generation INTEGER NOT NULL,
                seq_id TEXT NOT NULL,
                n TEXT NOT NULL,
                abs_n TEXT NOT NULL,
                abs_n_digits INTEGER NOT NULL,
                negative INTEGER NOT NULL,
                line_number INTEGER NOT NULL,
                relpath TEXT NOT NULL,
                PRIMARY KEY (value, generation, seq_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bfile_search_rank ON bfile_search_hits(value, generation, abs_n_digits, abs_n, negative, seq_id)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO bfile_meta(key, value) VALUES ('schema_version', ?)",
            (str(BFILE_SCHEMA_VERSION),),
        )


def build_bfile_index(files_root: Path, db_path: Path, *, rebuild: bool = False) -> dict:
    """Build/update a compact manifest; replace rebuilt databases atomically."""
    files_root = Path(files_root).resolve()
    if not files_root.exists():
        raise FileNotFoundError(files_root)
    db_path = Path(db_path)
    if not rebuild:
        return _build_bfile_index(files_root, db_path, rebuild=False)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{db_path.name}.", suffix=".tmp", dir=db_path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        result = _build_bfile_index(files_root, temporary, rebuild=True)
        result["db"] = str(db_path)
        temporary.replace(db_path)
        return result
    finally:
        for suffix in ("", "-journal", "-shm", "-wal"):
            Path(f"{temporary}{suffix}").unlink(missing_ok=True)


def _build_bfile_index(files_root: Path, db_path: Path, *, rebuild: bool) -> dict:
    init_bfile_db(db_path, rebuild=rebuild)

    canonical: dict[str, tuple[Path, str, int, int]] = {}
    auxiliary_ignored = auxiliary_bytes = duplicate_canonical = 0
    for path in files_root.rglob("b*.txt"):
        match = _CANONICAL_NAME.fullmatch(path.name)
        if not match:
            if _AUXILIARY_NAME.fullmatch(path.name):
                auxiliary_ignored += 1
                try:
                    auxiliary_bytes += path.stat().st_size
                except OSError:
                    pass
            continue
        stat = path.stat()
        seq_id = f"A{match.group(1)}"
        row = (path, path.relative_to(files_root).as_posix(), stat.st_size, stat.st_mtime_ns)
        if seq_id in canonical:
            duplicate_canonical += 1
            if row[1] >= canonical[seq_id][1]:
                continue
        canonical[seq_id] = row

    with sqlite3.connect(db_path) as conn:
        existing = {
            str(seq_id): (str(relpath), int(size), int(mtime), str(status))
            for seq_id, relpath, size, mtime, status in conn.execute(
                "SELECT seq_id, relpath, size_bytes, mtime_ns, status FROM bfiles"
            )
        }
        updates = []
        skipped_unchanged = lfs_pointers = raw_bytes = 0
        for seq_id in sorted(canonical):
            path, relpath, size, mtime_ns = canonical[seq_id]
            raw_bytes += size
            old = existing.get(seq_id)
            if old and old[:3] == (relpath, size, mtime_ns):
                status = old[3]
                skipped_unchanged += 1
            else:
                status = "lfs_pointer" if size < 1024 and _is_lfs_pointer(path) else "ok"
                updates.append((seq_id, relpath, size, mtime_ns, status))
            lfs_pointers += status == "lfs_pointer"

        removed = sorted(set(existing) - set(canonical))
        if updates:
            conn.executemany(
                """
                INSERT INTO bfiles(seq_id, relpath, size_bytes, mtime_ns, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(seq_id) DO UPDATE SET
                    relpath=excluded.relpath,
                    size_bytes=excluded.size_bytes,
                    mtime_ns=excluded.mtime_ns,
                    status=excluded.status
                """,
                updates,
            )
        if removed:
            conn.executemany("DELETE FROM bfiles WHERE seq_id = ?", ((seq_id,) for seq_id in removed))

        generation = int(_metadata(conn, "generation", "0") or 0)
        if updates or removed or rebuild:
            generation += 1
            conn.execute("DELETE FROM bfile_search_hits")
            conn.execute("DELETE FROM bfile_searches")
        values = {
            "files_root": str(files_root),
            "generation": str(generation),
            "canonical_files": str(len(canonical)),
            "canonical_bytes": str(raw_bytes),
            "auxiliary_files_ignored": str(auxiliary_ignored),
            "last_indexed_utc": datetime.now(timezone.utc).isoformat(),
        }
        conn.executemany("INSERT OR REPLACE INTO bfile_meta(key, value) VALUES (?, ?)", values.items())
        conn.commit()

    return {
        "schema_version": BFILE_SCHEMA_VERSION,
        "storage_strategy": "canonical manifest + on-demand ripgrep cache",
        "files_root": str(files_root),
        "db": str(db_path),
        "generation": generation,
        "files_seen": len(canonical) + auxiliary_ignored,
        "files_indexed": len(canonical) - lfs_pointers,
        "manifest_rows": len(canonical),
        "files_updated": len(updates),
        "files_removed": len(removed),
        "skipped_unchanged": skipped_unchanged,
        "lfs_pointers": lfs_pointers,
        "auxiliary_ignored": auxiliary_ignored,
        "duplicate_canonical": duplicate_canonical,
        "canonical_bytes": raw_bytes,
        "canonical_gib": round(raw_bytes / 2**30, 3),
        "auxiliary_bytes_ignored": auxiliary_bytes,
        "db_bytes": Path(db_path).stat().st_size,
        "legacy_value_rows_materialized": 0,
    }


def _value_pattern(value: int) -> str:
    if value == 0:
        token = r"[+-]?0+"
    elif value > 0:
        token = rf"\+?0*{value}"
    else:
        token = rf"-0*{-value}"
    return rf"^[[:space:]]*[+-]?[0-9]+[[:space:]]+{token}(?:[[:space:]]|$)"


def _ranked_hits(
    conn: sqlite3.Connection,
    value: str,
    generation: int,
    limit: int,
    oeis_db: Path | None,
) -> list[dict]:
    attached = bool(oeis_db and Path(oeis_db).exists())
    if attached:
        conn.execute("ATTACH DATABASE ? AS oeis_main", (str(Path(oeis_db)),))
        sql = """
            SELECT h.seq_id, h.n, h.line_number, h.relpath, s.name, s.keywords,
                   4 * (instr(',' || coalesce(s.keywords, '') || ',', ',core,') > 0)
                   + 2 * (instr(',' || coalesce(s.keywords, '') || ',', ',nice,') > 0)
                   + (instr(',' || coalesce(s.keywords, '') || ',', ',easy,') > 0) AS popularity
            FROM bfile_search_hits h
            LEFT JOIN oeis_main.sequences s ON s.id = h.seq_id
            WHERE h.value = ? AND h.generation = ?
            ORDER BY popularity DESC, h.abs_n_digits, h.abs_n, h.negative DESC, h.seq_id
            LIMIT ?
        """
    else:
        sql = """
            SELECT seq_id, n, line_number, relpath, NULL AS name, NULL AS keywords, 0 AS popularity
            FROM bfile_search_hits
            WHERE value = ? AND generation = ?
            ORDER BY abs_n_digits, abs_n, negative DESC, seq_id
            LIMIT ?
        """
    rows = conn.execute(sql, (value, generation, limit)).fetchall()
    return [
        {
            "rank": rank,
            "id": str(row[0]),
            "n": int(row[1]),
            "name": row[4],
            "keywords": str(row[5]).split(",") if row[5] else [],
            "popularity": int(row[6]),
            "line": int(row[2]),
            "path": str(row[3]),
        }
        for rank, row in enumerate(rows, 1)
    ]


def search_bfile_index(
    db_path: Path,
    value: str,
    *,
    limit: int = 20,
    oeis_db: Path | None = Path("data/processed/oeis.db"),
    threads: int = 0,
    max_time_s: float | None = None,
    refresh_cache: bool = False,
) -> dict:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    value_txt = str(int(str(value).strip()))
    limit = max(1, int(limit))

    with sqlite3.connect(db_path) as conn:
        generation = int(_metadata(conn, "generation", "0") or 0)
        files_root = Path(_metadata(conn, "files_root", "") or "")
        if not files_root.exists():
            raise FileNotFoundError(f"b-file corpus missing: {files_root}")
        if refresh_cache:
            conn.execute("DELETE FROM bfile_search_hits WHERE value = ? AND generation = ?", (value_txt, generation))
            conn.execute("DELETE FROM bfile_searches WHERE value = ? AND generation = ?", (value_txt, generation))
        cached_row = conn.execute(
            "SELECT total, scan_seconds FROM bfile_searches WHERE value = ? AND generation = ?",
            (value_txt, generation),
        ).fetchone()
        cached = cached_row is not None

    if not cached:
        started = time.perf_counter()
        command = [
            "rg",
            "--text",
            "--color",
            "never",
            "--no-heading",
            "--line-number",
            "--max-count",
            "1",
            "--threads",
            str(max(0, int(threads))),
            "--glob",
            "b[0-9][0-9][0-9][0-9][0-9][0-9].txt",
            _value_pattern(int(value_txt)),
            str(files_root),
        ]
        try:
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=max_time_s)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"b-file scan exceeded {max_time_s:g}s; no partial cache was written") from exc
        if process.returncode not in (0, 1):
            raise RuntimeError(process.stderr.strip() or f"ripgrep exited {process.returncode}")

        best: dict[str, tuple[int, int, str]] = {}
        for line in process.stdout.splitlines():
            try:
                path_text, line_text, content = line.split(":", 2)
                path = Path(path_text)
                match = _CANONICAL_NAME.fullmatch(path.name)
                parts = content.split()
                if not match or len(parts) < 2 or int(parts[1]) != int(value_txt):
                    continue
                seq_id = f"A{match.group(1)}"
                candidate = (int(parts[0]), int(line_text), path.relative_to(files_root).as_posix())
                old = best.get(seq_id)
                if old is None or (abs(candidate[0]), candidate[0]) < (abs(old[0]), old[0]):
                    best[seq_id] = candidate
            except (ValueError, OSError):
                continue
        scan_seconds = time.perf_counter() - started
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO bfile_search_hits(
                    value, generation, seq_id, n, abs_n, abs_n_digits, negative, line_number, relpath
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (value_txt, generation, seq_id, str(n), str(abs(n)), len(str(abs(n))), int(n < 0), line_number, relpath)
                    for seq_id, (n, line_number, relpath) in best.items()
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO bfile_searches(value, generation, total, scan_seconds, searched_utc) VALUES (?, ?, ?, ?, ?)",
                (value_txt, generation, len(best), scan_seconds, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        total = len(best)
    else:
        total, scan_seconds = int(cached_row[0]), float(cached_row[1])

    with sqlite3.connect(db_path) as conn:
        matches = _ranked_hits(conn, value_txt, generation, limit, oeis_db)
    return {
        "schema_version": 1,
        "value": value_txt,
        "total": total,
        "matches": matches,
        "limit": limit,
        "truncated": total > limit,
        "cached": cached,
        "scan_seconds": round(scan_seconds, 3),
        "generation": generation,
        "ranking": "OEIS core/nice/easy keywords, then smallest absolute b-file index",
        "semantics": "one best index per canonical b-file; auxiliary b-files are excluded",
    }
