import sqlite3
from pathlib import Path

import pytest

from oeis_matcher.build_index import build_index
from oeis_matcher.search_metadata import build_search_metadata
from oeis_matcher.storage import init_db


def write_entry(root, seq_id, text):
    path = root / "seq" / seq_id[:4] / f"{seq_id}.seq"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rows(db):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return {row["id"]: dict(row) for row in conn.execute("SELECT * FROM search_metadata")}


def test_text_and_distinct_inbound_sources(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    mirror = tmp_path / "mirror"
    write_entry(mirror, "A000001",
                "%C A000001 Counts trees; see A000002 and A000002.\n"
                "%D A000001 A book.\n%D A000001 Another reference.\n"
                "%H A000001 <a href='url'>Paper</a> A000003\n"
                "%F A000001 A000002(n) + A000001(n).\n"
                "%Y A000001 Cf. A000002, A000001.\n")
    write_entry(mirror, "A000002", "%Y A000002 A000001\n%C A000002 A000001\n")
    write_entry(mirror, "A000003", "%N A000003 No references.\n")
    stats = build_search_metadata(db, mirror)
    assert stats["entries"] == 3 and stats["reference_edges"] == 2
    data = rows(db)
    assert data["A000001"]["comments"] == "Counts trees; see A000002 and A000002."
    assert data["A000001"]["references_text"] == "A book.\nAnother reference."
    assert data["A000001"]["links"].startswith("<a href=")
    assert data["A000001"]["inbound_links"] == 1
    assert data["A000002"]["inbound_links"] == 1
    assert data["A000003"]["inbound_links"] == 0
    assert build_search_metadata(db, mirror)["entries"] == 3
    assert rows(db) == data


def test_empty_source_preserves_previous_metadata(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    write_entry(tmp_path, "A000001", "%C A000001 Original.\n")
    build_search_metadata(db, tmp_path)
    before = rows(db)
    assert not build_search_metadata(db, tmp_path / "missing")["available"]
    assert rows(db) == before


def test_bad_entry_rolls_back_existing_metadata(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    write_entry(tmp_path, "A000001", "%C A000001 Original.\n")
    build_search_metadata(db, tmp_path)
    write_entry(tmp_path, "A000001", "%C A000001 Changed.\n")
    write_entry(tmp_path, "A000002", "%C A000003 Wrong ID.\n")
    with pytest.raises(ValueError, match="does not match"):
        build_search_metadata(db, tmp_path)
    assert rows(db)["A000001"]["comments"] == "Original."


def test_build_includes_metadata_in_same_scan(tmp_path: Path):
    write_entry(tmp_path, "A000001", "%K A000001 core\n%C A000001 Trees.\n")
    stripped = tmp_path / "stripped"
    stripped.write_text("A000001 ,1,2,3,\n", encoding="utf-8")
    db = tmp_path / "test.db"
    build_index(stripped, None, None, db, oeisdata_root=tmp_path)
    assert rows(db)["A000001"]["comments"] == "Trees."


def test_missing_db_does_not_create_empty_file(tmp_path):
    db = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        build_search_metadata(db, tmp_path)
    assert not db.exists()


def test_metadata_refresh_invalidates_profiles_but_empty_source_does_not(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    write_entry(tmp_path, "A000001", "%C A000001 Original.\n")
    build_search_metadata(db, tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE search_profiles (id TEXT PRIMARY KEY, score REAL)")
        conn.execute("INSERT INTO search_profiles VALUES ('A000001', 10)")
        conn.execute("CREATE TRIGGER metadata_changed AFTER UPDATE ON search_metadata "
                     "BEGIN DELETE FROM search_profiles; END")
    build_search_metadata(db, tmp_path / "missing")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM search_profiles").fetchone()[0] == 1
    write_entry(tmp_path, "A000001", "%C A000001 Changed.\n")
    build_search_metadata(db, tmp_path)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM search_profiles").fetchone()[0] == 0


def test_failed_profile_invalidation_rolls_back_metadata_replacement(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    write_entry(tmp_path, "A000001", "%C A000001 Original.\n")
    build_search_metadata(db, tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE search_profiles (id TEXT PRIMARY KEY, score REAL)")
        conn.execute("INSERT INTO search_profiles VALUES ('A000001', 10)")
        conn.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON search_profiles "
                     "BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    write_entry(tmp_path, "A000001", "%C A000001 Changed.\n")
    with pytest.raises(sqlite3.IntegrityError, match="blocked"):
        build_search_metadata(db, tmp_path)
    assert rows(db)["A000001"]["comments"] == "Original."
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM search_profiles").fetchone()[0] == 1


def test_build_imports_search_text_with_complete_aggregate_exports(tmp_path):
    write_entry(tmp_path, "A000001", "%C A000001 Trees.\n%K A000001 easy\n")
    seq = tmp_path / "seq"
    (seq / "KEYWORDS").write_text("A000001 core\n", encoding="utf-8")
    (seq / "OFFSET").write_text("A000001 1,2\n", encoding="utf-8")
    (seq / "FORMULA").write_text("A000001 a(n)=n\n", encoding="utf-8")
    stripped = tmp_path / "stripped"
    stripped.write_text("A000001 ,1,2,3,\n", encoding="utf-8")
    db = tmp_path / "test.db"
    build_index(stripped, None, None, db, oeisdata_root=tmp_path)
    assert rows(db)["A000001"]["comments"] == "Trees."
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT keywords, formula FROM sequences").fetchone() == ("core", "a(n)=n")
