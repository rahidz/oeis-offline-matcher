from pathlib import Path

from oeis_matcher.api import analyze_sequence
from oeis_matcher.build_index import build_index


def _mini_db(tmp_path: Path) -> Path:
    base = Path(__file__).parent / "data" / "mini_oeis"
    db = tmp_path / "oeis.db"
    build_index(base / "stripped.txt", base / "names.txt", base / "keywords.txt", db, max_terms=20)
    return db


def test_regression_fibonacci_exact_stable(tmp_path: Path):
    db = _mini_db(tmp_path)
    res = analyze_sequence(
        "0,1,1,2,3,5",
        db_path=db,
        exact_limit=3,
        transform_limit=0,
        similarity=0,
        combos=0,
    )
    ids = [m["id"] for m in res["exact_matches"]]
    assert ids and ids[0] == "A000045"


def test_regression_primes_exact_stable(tmp_path: Path):
    db = _mini_db(tmp_path)
    res = analyze_sequence(
        "2,3,5,7,11",
        db_path=db,
        exact_limit=3,
        transform_limit=0,
        similarity=0,
        combos=0,
    )
    ids = [m["id"] for m in res["exact_matches"]]
    assert ids and ids[0] == "A000040"


def test_regression_transform_stable_order(tmp_path: Path):
    db = _mini_db(tmp_path)
    res = analyze_sequence(
        "1,2,3,4,5",
        db_path=db,
        exact_limit=0,
        transform_limit=5,
        similarity=0,
        combos=0,
    )
    t_matches = res["transform_matches"]
    ids = [m["id"] for m in t_matches]
    assert "A000012" in ids  # diff(naturals) → ones remains a top transform


def test_regression_cauchy_convolution_self_pair(tmp_path: Path):
    db = _mini_db(tmp_path)
    res = analyze_sequence(
        "1,2,3,4,5,6",
        db_path=db,
        exact_limit=0,
        transform_limit=0,
        similarity=20,
        combos=0,
        convolution_limit=10,
        convolution_ops=("cauchy",),
        combo_candidates=50,
    )
    conv = res["convolution_combinations"]
    assert any(tuple(m["ids"]) == ("A000012", "A000012") for m in conv)
