from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.api import analyze_sequence


def _paths(tmp_path: Path):
    base = Path(__file__).parent / "data" / "mini_oeis"
    return (
        base / "stripped.txt",
        base / "names.txt",
        base / "keywords.txt",
        tmp_path / "oeis.db",
    )


def test_analyze_fibonacci_prefix(tmp_path: Path):
    stripped, names, keywords, db = _paths(tmp_path)
    build_index(stripped, names, keywords, db, max_terms=20)

    res = analyze_sequence("0,1,1,2,3,5", db_path=db, exact_limit=5, transform_limit=0, similarity=0, combos=0)
    ids = [m["id"] for m in res["exact_matches"]]
    assert "A000045" in ids


def test_transform_and_combo_on_mini_fixture(tmp_path: Path):
    stripped, names, keywords, db = _paths(tmp_path)
    build_index(stripped, names, keywords, db, max_terms=20)

    # Transform: scaling naturals to evens
    res_t = analyze_sequence("1,2,3,4,5", db_path=db, exact_limit=2, transform_limit=10, similarity=0, combos=0)
    t_ids = [m["id"] for m in res_t["transform_matches"]]
    assert "A000027" in t_ids  # identity

    # Combination: 2*A000027 + A000012 = odd numbers starting at 3
    res_c = analyze_sequence(
        "3,5,7,9,11",
        db_path=db,
        exact_limit=2,
        transform_limit=0,
        similarity=0,
        combos=10,
        combo_coeffs=(1, 2),
        combo_max_shift=1,
        combo_candidates=20,
    )
    combos = res_c["combinations"]
    assert any("A000027" in c["expression"] and "A000012" in c["expression"] for c in combos)


def test_combo_pronic_from_square_and_n(tmp_path: Path):
    stripped, names, keywords, db = _paths(tmp_path)
    build_index(stripped, names, keywords, db, max_terms=20)

    # Pronic numbers n(n+1) = squares + nonnegative integers
    res = analyze_sequence(
        "0,2,6,12,20",
        db_path=db,
        exact_limit=2,
        transform_limit=0,
        similarity=0,
        combos=10,
        combo_coeffs=(1, 2, 3, -1),  # include 1
        combo_max_shift=0,
        combo_candidates=30,
    )
    combos = res["combinations"]
    assert any("A000290" in c["expression"] and "A001477" in c["expression"] for c in combos)


def test_transform_partial_sum_hits_naturals(tmp_path: Path):
    stripped, names, keywords, db = _paths(tmp_path)
    build_index(stripped, names, keywords, db, max_terms=20)

    # partial_sum(ones) = naturals
    res = analyze_sequence(
        "1,1,1,1,1",
        db_path=db,
        exact_limit=0,
        transform_limit=10,
        similarity=0,
        combos=0,
        transform_args={"allow_diff": True, "allow_partial_sum": True, "allow_abs": True, "allow_gcd_norm": True},
    )
    t_ids = [m["id"] for m in res["transform_matches"]]
    assert "A000027" in t_ids


def test_transform_diff_hits_ones(tmp_path: Path):
    stripped, names, keywords, db = _paths(tmp_path)
    build_index(stripped, names, keywords, db, max_terms=20)

    # diff(naturals) = ones
    res = analyze_sequence(
        "1,2,3,4,5",
        db_path=db,
        exact_limit=0,
        transform_limit=10,
        similarity=0,
        combos=0,
    )
    t_ids = [m["id"] for m in res["transform_matches"]]
    assert "A000012" in t_ids
