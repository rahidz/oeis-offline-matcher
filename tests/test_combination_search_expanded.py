from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.combination_search import search_two_sequence_combinations_expanded
from oeis_matcher.combination_search import search_three_sequence_combinations_expanded
from oeis_matcher.query import parse_query


def test_expanded_pair_search_finds_sum_of_two_sequences(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 3,6,4,8,10,5,5,7",
                "A200000 1,1,0,4,42,9050,6965359",
                # Noise sequences (should not matter)
                "A000001 0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000001 Zeros",
                "A000002 Ones",
                "A100000 Ishango middle column",
                "A200000 Meanders",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=20)

    query = parse_query("4,7,4,12,52", min_match_length=3, allow_subsequence=False)
    combos = search_two_sequence_combinations_expanded(
        query,
        db,
        coeffs=(1,),
        limit=5,
        scan_strides=(1,),
        max_time_s=2.0,
        snippet_len=5,
    )
    assert combos
    assert any(set(m.ids) == {"A100000", "A200000"} and set(m.coeffs) == {1} for m in combos)


def test_expanded_triple_search_finds_sum_of_three_sequences(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 3,6,4,8,10,5,5,7",
                "A200000 1,1,0,4,42,9050,6965359",
                "A300000 1,10,99,999,9990,99900,999000",
                # Noise sequences (should not matter)
                "A000001 0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000001 Zeros",
                "A000002 Ones",
                "A100000 Ishango middle column",
                "A200000 Meanders",
                "A300000 Concatenation sum",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=20)

    query = parse_query("5,17,103,1011,10042", min_match_length=3, allow_subsequence=False)
    triples = search_three_sequence_combinations_expanded(
        query,
        db,
        coeffs=(1,),
        limit=5,
        max_anchors=20,
        scan_strides=(1,),
        max_time_s=2.0,
        snippet_len=5,
    )
    assert triples
    assert any(set(m.ids) == {"A100000", "A200000", "A300000"} and set(m.coeffs) == {1} for m in triples)
