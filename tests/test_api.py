from pathlib import Path

from oeis_matcher.api import analyze_sequence, match_exact_terms, search_combinations, search_transforms
from oeis_matcher.build_index import build_index
from oeis_matcher.models import AnalysisResult


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A400000 0,1,1,2,3,5",
                "A400001 1,2,3,4,5,6",
                "A400002 0,2,4,6,8,10",
                "A400003 1,1,1,1,1,1",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A400000 Fib partial",
                "A400001 Naturals",
                "A400002 Evens",
                "A400003 Ones",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_match_exact_terms(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    hits = match_exact_terms([0, 1, 1, 2], db_path=db, allow_subsequence=False)
    assert hits and hits[0].id == "A400000"


def test_match_exact_terms_fallback_subsequence(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    hits = match_exact_terms([2, 3, 4], db_path=db, allow_subsequence=False, fallback_subsequence=True)
    assert hits and hits[0].match_type == "subsequence"


def test_search_transforms_wrapper(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    matches = search_transforms(
        [1, 2, 3, 4, 5],
        db_path=db,
        max_depth=1,
        scale_values=(2,),
        shift_values=(),
        allow_diff=False,
        allow_partial_sum=False,
        allow_abs=False,
        allow_gcd_norm=False,
        allow_subsequence=True,
    )
    ids = [m.id for m in matches]
    assert "A400002" in ids


def test_analyze_sequence_combo_included(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    result = analyze_sequence(
        [3, 4, 5, 6],
        db_path=db,
        exact_limit=5,
        transform_limit=5,
        similarity=0,
        combos=5,
        combo_coeffs=(1, 2),
        combo_max_shift=1,
        combo_candidates=20,
    )
    combos = result["combinations"]
    assert combos
    exprs = [c["expression"] for c in combos]
    assert any("A400001" in e and "A400003" in e for e in exprs)


def test_analyze_sequence_triples(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    # Construct sequence: naturals + ones - evens = [1,1,1,1,1,1] + [1..6] - [0,2,4,6,8,10] = 2,1,0,-1,-2,-3
    res = analyze_sequence(
        "2,1,0,-1,-2",
        db_path=db,
        exact_limit=3,
        transform_limit=0,
        similarity=0,
        combos=0,
        triples=5,
        combo_coeffs=(1, -1),
        combo_max_shift=0,
        triple_candidates=10,
        combo_max_combinations=50,
        triple_max_combinations=50,
        fallback_subsequence=True,
    )
    triples = res["triple_combinations"]
    assert triples
    ids = triples[0]["ids"]
    assert set(ids) == {"A400001", "A400002", "A400003"}


def test_analyze_sequence_dataclass(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    res = analyze_sequence(
        "0,1,1,2",
        db_path=db,
        exact_limit=3,
        transform_limit=0,
        similarity=0,
        combos=0,
        as_dataclass=True,
    )
    assert isinstance(res, AnalysisResult)
    assert res.query[:3] == [0, 1, 1]
    assert res.exact_matches


def test_analyze_sequence_timings(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    res = analyze_sequence(
        "0,1,1,2",
        db_path=db,
        exact_limit=3,
        transform_limit=0,
        similarity=0,
        combos=0,
        collect_timings=True,
        fallback_subsequence=True,
    )
    assert "diagnostics" in res
    assert "timings_ms" in res["diagnostics"]
    assert res["diagnostics"]["timings_ms"]["exact_ms"] >= 0.0


def test_combo_unfiltered_finds_mismatched_prefix(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A500000 1,5,49,502,4996",
                "A500001 1,5,51,502,4995",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A500000 First",
                "A500001 Second",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    res = analyze_sequence(
        "2,10,100,1004,9991",
        db_path=db,
        exact_limit=0,
        transform_limit=0,
        similarity=0,
        combos=3,
        combo_coeffs=(1, 1),
        combo_max_shift=0,
        combo_candidates=20,
        combo_unfiltered=True,
    )
    combos = res["combinations"]
    assert combos
    ids = combos[0]["ids"]
    assert set(ids) == {"A500000", "A500001"}
