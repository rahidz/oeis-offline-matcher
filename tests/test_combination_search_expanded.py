from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.combination_search import search_two_sequence_combinations_expanded
from oeis_matcher.combination_search import search_three_sequence_combinations_expanded
from oeis_matcher.combination_search import search_pointwise_two_sequence_combinations_expanded
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


def test_expanded_pair_search_supports_shifts_when_prefix_columns_exist(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 100,200,300,400,500,600,700,800,900,1000,1100",
                "A200000 1,2,3,4,5,6,7,8,9,10,11,12",
                # Noise sequences (should not matter)
                "A000001 0,0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000001 Zeros",
                "A000002 Ones",
                "A100000 Hundreds",
                "A200000 Naturals",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=32)

    # q = A100000(n+2) + A200000(n+5) (first 5 terms).
    query = parse_query("306,407,508,609,710", min_match_length=5, allow_subsequence=False)
    combos = search_two_sequence_combinations_expanded(
        query,
        db,
        coeffs=(1,),
        limit=10,
        max_shift=5,
        scan_strides=(1,),
        max_time_s=2.0,
        snippet_len=5,
    )
    assert combos
    assert any(m.ids == ("A100000", "A200000") and m.coeffs == (1, 1) and m.shifts == (2, 5) for m in combos), combos


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


def test_expanded_pointwise_mul_search_finds_shifted_product(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                # A100000: primes
                "A100000 2,3,5,7,11,13,17,19,23,29,31,37",
                # A200000: naturals starting at 1
                "A200000 1,2,3,4,5,6,7,8,9,10,11,12,13,14",
                # Noise sequences (should not matter)
                "A000001 0,0,0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1,1,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000001 Zeros",
                "A000002 Ones",
                "A100000 Primes",
                "A200000 Naturals",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=32)

    # Query is A100000(n+2) * A200000(n+5), length 8.
    query = parse_query("30,49,88,117,170,209,276,377", min_match_length=5, allow_subsequence=False)
    matches = search_pointwise_two_sequence_combinations_expanded(
        query,
        db,
        ops=("mul",),
        max_shift=5,
        limit=5,
        scan_strides=(1,),
        max_time_s=2.0,
        snippet_len=8,
    )
    assert matches
    assert any(m.ids == ("A100000", "A200000") and m.shifts == (2, 5) for m in matches), matches
