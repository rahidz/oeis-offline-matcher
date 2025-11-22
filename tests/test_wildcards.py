from pathlib import Path
import pytest

from oeis_matcher.build_index import build_index
from oeis_matcher.matcher import match_exact
from oeis_matcher.query import parse_query
from oeis_matcher.storage import iter_sequences


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A600000 1,3,5,7,9",
                "A600001 2,3,5,7,11",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A600000 odds\nA600001 primes up to 11\n", encoding="utf-8")
    return stripped, names


def test_prefix_wildcard(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,?,5")
    matches = match_exact(query, iter_sequences(db))
    assert any(m.id == "A600000" for m in matches)


def test_subsequence_wildcard(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("?,3,5", allow_subsequence=True)
    matches = match_exact(query, iter_sequences(db))
    assert any(m.id == "A600000" for m in matches)


def test_too_many_wildcards_rejected():
    from oeis_matcher.query import QueryParseError

    # four wildcards out of five terms exceeds ratio/limit
    with pytest.raises(QueryParseError):
        parse_query("?, ?, ?, ?, 5", min_match_length=3)
