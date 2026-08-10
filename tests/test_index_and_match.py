import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import oeis_matcher.build_index as build_index_module
from oeis_matcher.build_index import build_index
from oeis_matcher.matcher import match_exact
from oeis_matcher.query import parse_query
from oeis_matcher.storage import iter_sequences


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    keywords = tmp_path / "keywords.txt"
    stripped.write_text(
        "\n".join(
            [
                "A000045 0,1,1,2,3,5,8,13",
                "A000010 1,1,2,2,4,2,6,4",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000045 Fibonacci numbers",
                "A000010 Euler totient",
            ]
        ),
        encoding="utf-8",
    )
    keywords.write_text(
        "\n".join(
            [
                "A000045 nonn,easy",
                "A000010 easy",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names, keywords


def test_build_index_and_iter(tmp_path: Path):
    stripped, names, keywords = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    stats = build_index(stripped, names, keywords, db, max_terms=6)
    assert stats["inserted"] == 2
    seqs = list(iter_sequences(db))
    assert {s.id for s in seqs} == {"A000045", "A000010"}
    fib = next(s for s in seqs if s.id == "A000045")
    assert fib.terms == [0, 1, 1, 2, 3, 5]  # truncated
    assert fib.name == "Fibonacci numbers"
    assert fib.keywords == ["nonn", "easy"]


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_failed_rebuild_preserves_existing_database_and_removes_temp_files(
    tmp_path: Path, monkeypatch, error_type
):
    stripped, names, keywords = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, max_terms=8)
    original = db.read_bytes()

    def fail_indexes(_db_path):
        raise error_type("injected index failure")

    monkeypatch.setattr(build_index_module, "ensure_db_indexes", fail_indexes)
    with pytest.raises(error_type, match="injected index failure"):
        build_index(stripped, names, keywords, db, max_terms=6)

    assert db.read_bytes() == original
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(".oeis.db.build-")]


def test_rebuild_atomically_replaces_existing_database(tmp_path: Path):
    stripped, names, keywords = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, max_terms=8)
    stripped.write_text("A999999 2,4,8,16,32,64", encoding="utf-8")
    names.write_text("A999999 Replacement sequence", encoding="utf-8")
    keywords.write_text("A999999 easy", encoding="utf-8")

    stats = build_index(stripped, names, keywords, db, max_terms=8)

    assert stats == {"inserted": 1, "db": str(db)}
    assert [record.id for record in iter_sequences(db)] == ["A999999"]
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_rebuild_replaces_corrupt_existing_database(tmp_path: Path):
    stripped, names, keywords = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    db.write_bytes(b"not a sqlite database")

    stats = build_index(stripped, names, keywords, db, max_terms=8)

    assert stats == {"inserted": 2, "db": str(db)}
    assert {record.id for record in iter_sequences(db)} == {"A000045", "A000010"}


def test_rebuild_refuses_open_wal_reader_without_corrupting_database(tmp_path: Path):
    stripped, names, keywords = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, max_terms=8)
    reader = sqlite3.connect(db)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT COUNT(*) FROM sequences").fetchone() == (2,)
        stripped.write_text("A999999 2,4,8,16,32,64", encoding="utf-8")

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            build_index(stripped, names, keywords, db, max_terms=8)

        assert reader.execute("SELECT COUNT(*) FROM sequences").fetchone() == (2,)
    finally:
        reader.close()

    assert {record.id for record in iter_sequences(db)} == {"A000045", "A000010"}
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(".oeis.db.build-")]


def test_match_prefix_and_subsequence(tmp_path: Path):
    stripped, names, keywords = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, max_terms=8)

    # Prefix match
    query = parse_query("0,1,1,2", allow_subsequence=False)
    matches = match_exact(query, iter_sequences(db))
    assert matches
    assert matches[0].id == "A000045"
    assert matches[0].match_type == "prefix"

    # Subsequence match
    query2 = parse_query("2,3,5", allow_subsequence=True)
    matches2 = match_exact(query2, iter_sequences(db))
    assert any(m.id == "A000045" and m.match_type == "subsequence" and m.offset == 3 for m in matches2)
