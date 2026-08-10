from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from oeis_matcher.bfiles import (
    build_bfile_index,
    fetch_bfiles,
    iter_bfile_paths,
    search_bfile_index,
)


def test_manifest_search_cache_and_resume(tmp_path: Path):
    root = tmp_path / "files" / "A000"
    root.mkdir(parents=True)
    huge_n = 10**50
    (root / "b000001.txt").write_text(f"# comment\n0 5\n1 8\n2 13\n{huge_n} 99\n", encoding="utf-8")
    (root / "b000002_1.txt").write_text("10 13\n", encoding="utf-8")
    (root / "b000003.txt").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n",
        encoding="utf-8",
    )

    db = tmp_path / "bfiles.db"
    stats = build_bfile_index(tmp_path / "files", db)
    assert stats["files_seen"] == 3
    assert stats["files_indexed"] == 1
    assert stats["manifest_rows"] == 2
    assert stats["auxiliary_ignored"] == 1
    assert stats["lfs_pointers"] == 1
    assert stats["legacy_value_rows_materialized"] == 0

    res = search_bfile_index(db, "13", limit=10, oeis_db=None)
    assert res["total"] == 1
    assert res["matches"][0]["id"] == "A000001"
    assert res["matches"][0]["n"] == 2
    assert res["cached"] is False
    assert search_bfile_index(db, "13", limit=10, oeis_db=None)["cached"] is True
    assert search_bfile_index(db, "99", limit=10, oeis_db=None)["matches"][0]["n"] == huge_n

    resumed = build_bfile_index(tmp_path / "files", db)
    assert resumed["files_updated"] == 0
    assert resumed["skipped_unchanged"] == 2
    assert resumed["generation"] == stats["generation"]

    canonical = root / "b000001.txt"
    canonical.write_text(canonical.read_text(encoding="utf-8") + "3 21\n", encoding="utf-8")
    changed = build_bfile_index(tmp_path / "files", db)
    assert changed["files_updated"] == 1
    assert changed["generation"] == stats["generation"] + 1
    assert search_bfile_index(db, "21", limit=10, oeis_db=None)["total"] == 1


def test_rebuild_replaces_existing_manifest(tmp_path: Path):
    root = tmp_path / "files" / "A000"
    root.mkdir(parents=True)
    old = root / "b000001.txt"
    old.write_text("0 1\n", encoding="utf-8")
    db = tmp_path / "bfiles.db"
    build_bfile_index(tmp_path / "files", db)

    old.unlink()
    (root / "b000002.txt").write_text("0 2\n", encoding="utf-8")
    stats = build_bfile_index(tmp_path / "files", db, rebuild=True)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT seq_id FROM bfiles").fetchall() == [("A000002",)]
    assert stats["db"] == str(db)


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_failed_rebuild_preserves_existing_database(tmp_path: Path, monkeypatch, error_type):
    root = tmp_path / "files" / "A000"
    root.mkdir(parents=True)
    canonical = root / "b000001.txt"
    canonical.write_text("0 1\n", encoding="utf-8")
    db = tmp_path / "bfiles.db"
    build_bfile_index(tmp_path / "files", db)
    original = db.read_bytes()

    canonical.write_text("0 2\n", encoding="utf-8")

    def fail(_path):
        raise error_type("interrupted")

    monkeypatch.setattr("oeis_matcher.bfiles._is_lfs_pointer", fail)
    with pytest.raises(error_type):
        build_bfile_index(tmp_path / "files", db, rebuild=True)

    assert db.read_bytes() == original
    assert not list(tmp_path.glob(".bfiles.db.*.tmp*"))


def test_iter_bfile_paths_excludes_auxiliary_variants(tmp_path: Path):
    root = tmp_path / "files" / "A123"
    root.mkdir(parents=True)
    (root / "b123456.txt").write_text("0 1\n", encoding="utf-8")
    (root / "b123456_1.txt").write_text("0 2\n", encoding="utf-8")
    assert list(iter_bfile_paths(tmp_path / "files")) == [("A123456", root / "b123456.txt")]


def test_fetch_bfiles_from_local_base_url(tmp_path: Path):
    src = tmp_path / "src" / "A123456"
    src.mkdir(parents=True)
    (src / "b123456.txt").write_text("0 42\n", encoding="utf-8")

    dest = tmp_path / "dest"
    stats = fetch_bfiles(["A123456"], dest_root=dest, base_url=(tmp_path / "src").as_uri())
    assert stats["downloaded"] == 1
    assert stats["failed"] == 0
    out = dest / "A123" / "b123456.txt"
    assert out.exists()
    assert out.read_text(encoding="utf-8") == "0 42\n"


def test_fetch_replaces_lfs_pointer_without_force(tmp_path: Path):
    src = tmp_path / "src" / "A123456"
    src.mkdir(parents=True)
    (src / "b123456.txt").write_text("0 42\n", encoding="utf-8")
    dest = tmp_path / "dest"
    pointer = dest / "A123" / "b123456.txt"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")
    stats = fetch_bfiles(["A123456"], dest_root=dest, base_url=(tmp_path / "src").as_uri())
    assert stats["downloaded"] == 1
    assert pointer.read_text(encoding="utf-8") == "0 42\n"
