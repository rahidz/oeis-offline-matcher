from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.combination_search import search_mod_class_combinations
from oeis_matcher.query import parse_query


def test_modclass_search_finds_interleave_with_shifts(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 10,20,30,40,50,60,70,80,90,100,110,120",
                "A200000 1,2,3,4,5,6,7,8,9,10,11,12,13,14",
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
                "A100000 Tens",
                "A200000 Naturals",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=64)

    # a(2n) = A100000(n+1), a(2n+1) = A200000(n+2), length 12.
    evens = [20, 30, 40, 50, 60, 70]
    odds = [3, 4, 5, 6, 7, 8]
    q = []
    for a, b in zip(evens, odds):
        q.extend([a, b])
    query = parse_query(",".join(str(x) for x in q), min_match_length=5, allow_subsequence=False)

    matches = search_mod_class_combinations(
        query,
        db,
        moduli=(2,),
        limit=10,
        max_shift=5,
        max_time_s=2.0,
        snippet_len=12,
    )
    assert matches
    assert any(m.ids == ("A100000", "A200000") and m.shifts == (1, 2) for m in matches), matches

    excluded = search_mod_class_combinations(
        query,
        db,
        moduli=(2,),
        limit=10,
        max_shift=5,
        max_time_s=2.0,
        exclude_ids={"A100000"},
    )
    assert not excluded


def test_modclass_search_supports_modulus_3(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 100,200,300,400,500,600,700,800,900,1000,1100,1200",
                "A200000 1,2,3,4,5,6,7,8,9,10,11,12,13,14",
                "A300000 -1,-2,-3,-4,-5,-6,-7,-8,-9,-10,-11,-12,-13,-14",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A100000 Hundreds",
                "A200000 Naturals",
                "A300000 Negative naturals",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=64)

    # a(3n) = A100000(n), a(3n+1) = A200000(n+1), a(3n+2) = A300000(n+2), length 18.
    r0 = [100, 200, 300, 400, 500, 600]
    r1 = [2, 3, 4, 5, 6, 7]
    r2 = [-3, -4, -5, -6, -7, -8]
    q = []
    for a, b, c in zip(r0, r1, r2):
        q.extend([a, b, c])
    query = parse_query(",".join(str(x) for x in q), min_match_length=5, allow_subsequence=False)

    matches = search_mod_class_combinations(
        query,
        db,
        moduli=(3,),
        limit=10,
        max_shift=5,
        max_time_s=2.0,
        snippet_len=18,
    )
    assert matches
    assert any(m.ids == ("A100000", "A200000", "A300000") and m.shifts == (0, 1, 2) for m in matches), matches
