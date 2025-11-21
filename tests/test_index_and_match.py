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
    return stripped, names


def test_build_index_and_iter(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"

    stats = build_index(stripped, names, db, max_terms=6)
    assert stats["inserted"] == 2
    seqs = list(iter_sequences(db))
    assert {s.id for s in seqs} == {"A000045", "A000010"}
    fib = next(s for s in seqs if s.id == "A000045")
    assert fib.terms == [0, 1, 1, 2, 3, 5]  # truncated
    assert fib.name == "Fibonacci numbers"


def test_match_prefix_and_subsequence(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, db, max_terms=8)

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
