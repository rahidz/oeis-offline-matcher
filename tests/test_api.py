from pathlib import Path

from oeis_matcher.api import analyze_sequence, match_exact_terms, search_combinations, search_transforms
from oeis_matcher.build_index import build_index
from oeis_matcher.models import AnalysisResult
from oeis_matcher.oeis_data import load_formulas


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


def _make_fib_only_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A000045 0,1,1,2,3,5,8,13,21,34\n", encoding="utf-8")
    names.write_text("A000045 Fibonacci numbers\n", encoding="utf-8")
    return stripped, names


def test_analyze_sequence_includes_formula(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    formulas = tmp_path / "FORMULA"
    stripped.write_text("A500000 1,1,2,3,5\n", encoding="utf-8")
    names.write_text("A500000 Sample fib\n", encoding="utf-8")
    formulas.write_text("A500000 a(n)=a(n-1)+a(n-2)\n", encoding="utf-8")

    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, formulas_path=formulas, max_terms=10)

    res = analyze_sequence(
        "1,1,2,3",
        db_path=db,
        exact_limit=1,
        transform_limit=0,
        similarity=0,
        combos=0,
        show_terms=None,
        as_dataclass=False,
    )
    exact = res["exact_matches"][0]
    assert "formula" in exact
    assert "a(n-1)" in exact["formula"]


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


def test_analyze_sequence_rational_combo(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A800000 2,4,6,8\nA800001 1,1,1,1\n", encoding="utf-8")
    names.write_text("A800000 Evens\nA800001 Ones\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    res = analyze_sequence(
        [2, 3, 4, 5],
        db_path=db,
        exact_limit=0,
        transform_limit=0,
        similarity=0,
        combos=5,
        combo_rational=True,
        combo_candidates=10,
    )
    combos = res["combinations"]
    assert combos
    coeffs = combos[0]["coeffs"]
    assert any(c in {"1/2", "0.5"} for c in coeffs)


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


def test_analyze_subsequence_not_blocked_by_nonzero_filter(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    terms = "1,2,2,4,6,12,20,40,70,140,252"
    stripped.write_text(f"A910000 {terms}\n", encoding="utf-8")
    names.write_text("A910000 Test sequence\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=20)

    res = analyze_sequence(
        "2,4,6,12,20,40,70",
        db_path=db,
        exact_limit=5,
        transform_limit=0,
        similarity=0,
        combos=0,
        fallback_subsequence=True,
        fallback_full_scan=False,
    )
    matches = res["exact_matches"]
    assert any(m["id"] == "A910000" and m["match_type"] == "subsequence" and m["offset"] == 2 for m in matches)


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


def test_similarity_thresholds_filter(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    res = analyze_sequence(
        "1,2,3,4",
        db_path=db,
        exact_limit=0,
        transform_limit=0,
        similarity=5,
        similarity_min_corr=0.99,
        similarity_max_mse=0.01,
    )
    sims = res["similarity"]
    assert sims  # naturals should survive
    assert all(s["corr"] >= 0.99 for s in sims)


def test_search_combinations_negative_shift(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A420000 20,30,40,50",
                "A420001 90,190,290,390",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A420000 Seq1\nA420001 Seq2\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    combos = search_combinations(
        [999, 120, 230, 340],
        db_path=db,
        coeffs=(1,),
        max_shift=0,
        max_shift_back=1,
        candidate_cap=10,
    )
    assert combos
    m = combos[0]
    assert m.shifts == (0, -1)
    assert m.length == 3
    assert set(m.ids) == {"A420000", "A420001"}


def test_search_combinations_tracks_candidate_provenance(tmp_path: Path):
    stripped, names = _make_fib_only_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=20)

    combos = search_combinations(
        [2, 1, 3, 4, 7, 11],
        db_path=db,
        coeffs=(1,),
        max_shift=1,
        max_shift_back=1,
        candidate_cap=10,
        limit=10,
        max_checks=200_000,
    )
    assert combos
    assert any(
        m.ids == ("A000045", "A000045")
        and m.candidate_provenance
        and all("seed" in reasons for reasons in m.candidate_provenance)
        for m in combos
    )


def test_analyze_sequence_combo_rows_include_candidate_provenance(tmp_path: Path):
    stripped, names = _make_fib_only_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=20)

    result = analyze_sequence(
        [2, 1, 3, 4, 7, 11],
        db_path=db,
        exact_limit=0,
        transform_limit=0,
        similarity=0,
        combos=10,
        combo_coeffs=(1,),
        combo_max_shift=1,
        combo_max_shift_back=1,
        combo_candidates=10,
        combo_max_checks=200_000,
    )
    combos = result["combinations"]
    assert combos
    assert any("candidate_provenance" in c and any("seed" in rs for rs in c["candidate_provenance"]) for c in combos)


def test_analyze_combined_explanations_are_cross_family_and_fair(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A830000 1,2,3,4,5,6",
                "A830001 2,4,6,8,10,12",
                "A830002 1,1,1,1,1,1",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A830000 Naturals",
                "A830001 Evens",
                "A830002 Ones",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    res = analyze_sequence(
        "1,2,3,4,5,6",
        db_path=db,
        exact_limit=0,
        transform_limit=0,
        similarity=0,
        combos=5,
        combo_coeffs=(-1, 1),
        combo_candidates=10,
        triples=0,
        pointwise_limit=5,
        pointwise_ops=("gcd",),
        convolution_limit=5,
        convolution_ops=("cauchy",),
        combined_limit=2,
        combined_family_quota=1,
    )

    diag = res.get("diagnostics") or {}
    mixed = diag.get("combined_explanations") or []
    assert len(mixed) == 2
    families = {m["family"] for m in mixed}
    assert len(families) == 2
