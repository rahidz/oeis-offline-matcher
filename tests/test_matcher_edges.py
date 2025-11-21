from pathlib import Path

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
                "A500000 -1,-2,-3,-5,-8",
                "A500001 0,0,0,0",
                "A500002 1,2,3",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A500000 Negative fib-ish",
                "A500001 Zeros",
                "A500002 Naturals",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_matcher_handles_negative_numbers(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=8)

    query = parse_query("-1,-2,-3", allow_subsequence=False)
    matches = match_exact(query, iter_sequences(db))
    assert matches and matches[0].id == "A500000"


def test_matcher_respects_min_length(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=8)

    query = parse_query("0,0", allow_subsequence=True, min_match_length=3)
    matches = match_exact(query, iter_sequences(db))
    assert matches == []
