from __future__ import annotations

from pathlib import Path

from oeis_matcher.bfiles import build_bfile_index, fetch_bfiles, search_bfile_index


def test_build_bfile_index_and_search_skips_lfs_pointers(tmp_path: Path):
    root = tmp_path / "files" / "A000"
    root.mkdir(parents=True)
    (root / "b000001.txt").write_text("# comment\n0 5\n1 8\n2 13\n", encoding="utf-8")
    (root / "b000002_1.txt").write_text("10 13\n", encoding="utf-8")
    (root / "b000003.txt").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n",
        encoding="utf-8",
    )

    db = tmp_path / "bfiles.db"
    stats = build_bfile_index(tmp_path / "files", db)
    assert stats["files_seen"] == 3
    assert stats["files_indexed"] == 2
    assert stats["lfs_pointers"] == 1
    assert stats["rows_written"] == 4

    res = search_bfile_index(db, "13", limit=10)
    assert res["total"] == 2
    assert [row["id"] for row in res["matches"]] == ["A000001", "A000002"]


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
