import json
import sqlite3

import pytest

from oeis_matcher.api import search_catalog
from oeis_matcher.cli import main
from oeis_matcher.models import SequenceRecord
from oeis_matcher.search import build_search_profiles
from oeis_matcher.search_metadata import build_search_metadata
from oeis_matcher.storage import init_db, write_records


@pytest.fixture
def catalog(tmp_path):
    db = tmp_path / "catalog.db"
    init_db(db)
    write_records([
        SequenceRecord("A000001", [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144], 12, "Polyomino graphs", ["more"], formula="a(n)=a(n-1)+a(n-2)"),
        SequenceRecord("A000002", list(range(12)), 12, "Famous polyomino", ["core", "nice"]),
        SequenceRecord("A000003", [11, 1, 2, 30, -4], 5, "Obscure entries", ["dead"]),
        SequenceRecord("A000004", [2, 1, 1, 2, 3, 5], 6, "Two words and 100% literal", ["more"]),
    ], db)
    return db


@pytest.mark.parametrize("query,expected", [
    ("polyomino", {"A000001", "A000002"}),
    ("keyword: more", {"A000001", "A000004"}),
    ("1,1,2,3", {"A000001", "A000004"}),
    ("1, 1, 2, 3", {"A000001", "A000004"}),
    ("prefix:1,1,2", {"A000001"}),
    ("terms:1,?,2,3", {"A000001", "A000004"}),
    ("terms:1,2,3", {"A000001", "A000002", "A000004"}),
    ('"two words" -keyword:dead', {"A000004"}),
    ("100%", {"A000004"}),
    ("A000003 OR keyword:core", {"A000002", "A000003"}),
    ("polyomino -keyword:core", {"A000001"}),
    ("id:a000001,A000003", {"A000001", "A000003"}),
    ("minterms:10 has:formula", {"A000001"}),
    ("maxterms:6 -keyword:dead", {"A000004"}),
    ("formula:a(n-1)", {"A000001"}),
    ("no-such-text", set()),
    ("' OR 1=1 --'", set()),
])
def test_search_language(catalog, query, expected):
    result = search_catalog(query, db_path=catalog)
    assert {row["id"] for row in result["results"]} == expected
    assert result["total"] == len(expected)


@pytest.mark.parametrize("query", ["", "keyword:", "unknown:x", "OR polyomino", "polyomino OR", "terms:1,x,3", "id:no", '"unterminated', "minterms:-1"])
def test_bad_queries(catalog, query):
    with pytest.raises(ValueError):
        search_catalog(query, db_path=catalog)


def test_distinct_rankings_index_parity_and_pagination(catalog):
    before = {rank: search_catalog("*", db_path=catalog, rank=rank) for rank in ("discovery", "notability", "balanced")}
    assert before["discovery"]["results"][0]["id"] == "A000001"
    assert before["notability"]["results"][0]["id"] == "A000002"
    assert build_search_profiles(catalog)["profiles"] == 4
    for rank, previous in before.items():
        after = search_catalog("*", db_path=catalog, rank=rank)
        assert after["results"] == previous["results"]
        assert after["diagnostics"]["profiles_indexed"]
        assert search_catalog("*", db_path=catalog, rank=rank, limit=1, offset=1)["results"] == after["results"][1:2]
        assert search_catalog("*", db_path=catalog, offset=200)["results"] == []


def test_index_invalidated_on_record_change(catalog):
    build_search_profiles(catalog)
    build_search_profiles(catalog)
    with sqlite3.connect(catalog) as conn:
        conn.execute("UPDATE sequences SET keywords='core,nice' WHERE id='A000003'")
    assert not search_catalog("*", db_path=catalog)["diagnostics"]["profiles_indexed"]


def test_corpus_affine_crowding_and_cache_invalidation(catalog):
    squares = [n*n for n in range(20)]
    write_records([SequenceRecord("A000005", squares, 20, "Squares")], catalog)
    single = search_catalog("A000005", db_path=catalog)["results"][0]
    write_records([SequenceRecord("A000006", [7-3*t for t in squares], 20, "Reflected scaled squares")], catalog)
    crowded = search_catalog("A000005", db_path=catalog)["results"][0]
    assert crowded["discovery"] < single["discovery"]
    build_search_profiles(catalog)
    assert search_catalog("A000005", db_path=catalog)["results"][0] == crowded
    write_records([SequenceRecord("A000007", [t+3 for t in squares], 20, "Shifted squares")], catalog)
    assert not search_catalog("A000005", db_path=catalog)["diagnostics"]["profiles_indexed"]
    assert search_catalog("A000005", db_path=catalog)["results"][0]["discovery"] < crowded["discovery"]


def test_rich_fields_and_metadata_notability(catalog, tmp_path):
    root = tmp_path / "mirror" / "seq" / "A000"
    root.mkdir(parents=True)
    (root / "A000001.seq").write_text("%C A000001 Quantum tilings\n%D A000001 A useful paper\n%Y A000001 Cf. A000002.\n")
    (root / "A000002.seq").write_text("%N A000002 Famous polyomino\n")
    build_search_metadata(catalog, root.parent.parent)
    assert search_catalog("comment:quantum reference:paper related:A000002", db_path=catalog)["total"] == 1
    record = search_catalog("A000002", db_path=catalog)["results"][0]
    assert record["notability"] > 55


def test_cli_search_and_index(catalog, tmp_path, capsys):
    assert main(["search-index", "--db", str(catalog), "--oeisdata", str(tmp_path / "absent"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["profiles"] == 4
    for query in ("polyomino", "keyword: more", "1,1,2,3"):
        assert main(["search", query, "--db", str(catalog), "--rank", "notability", "--json"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["total"] == 2
        assert result["ranking"] == "notability"
    assert main(["search", "*", "--db", str(catalog), "--limit", "0"]) == 2
    assert "limit" in capsys.readouterr().err
    assert main(["search", "*", "--db", str(tmp_path / "missing.db")]) == 2
    assert not (tmp_path / "missing.db").exists()
