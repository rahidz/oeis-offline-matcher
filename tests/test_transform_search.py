from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.query import parse_query
from oeis_matcher.transform_search import search_transform_matches
from oeis_matcher.transforms import (
    abs_transform,
    cumulative_product_transform,
    default_transforms,
    make_affine,
    make_scale,
    make_shift,
)


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 2,4,6,8,10",
                "A100001 1,2,3,4,5",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A100000 Twice the naturals",
                "A100001 Naturals",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_transform_scale_hits_scaled_sequence(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,2,3,4,5", allow_subsequence=False)
    transforms = default_transforms(scale_values=(2,), shift_values=(), allow_diff=False, allow_partial_sum=False, allow_abs=False)

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        snippet_len=5,
    )

    ids = [m.id for m in matches]
    assert "A100000" in ids
    hit = next(m for m in matches if m.id == "A100000")
    assert hit.transform_desc is not None and "scale(2)" in hit.transform_desc
    assert hit.explanation and "Multiply by 2" in hit.explanation


def test_transform_extra_ops(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100100 1,2,3,4,5,6",
                "A100101 1,1,1,1,1,1",
                "A100102 1,3,5,7,9,11",
                "A100103 1,2,6,24,120",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A100100 Naturals",
                "A100101 Ones",
                "A100102 Odds",
                "A100103 Factorials-ish",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=8)

    query = parse_query("1,2,3,4")

    transforms = default_transforms(
        scale_values=(2,),
        shift_values=(),
        allow_diff=False,
        allow_partial_sum=False,
        allow_abs=False,
        allow_gcd_norm=False,
        allow_cumprod=True,
        allow_even_odd=True,
        allow_reverse=True,
        moving_sum_windows=(2,),
    )

    matches = search_transform_matches(query, db, max_depth=1, transforms=transforms, limit=10)
    ids = {m.id for m in matches}
    assert "A100103" in ids


def test_zero_collapsing_chain_is_dropped(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A900000 0,0,0,0,0",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A900000 Zeroes",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("2,4,7,13")
    transforms = [
        make_affine(-1, 2),
        cumulative_product_transform(),
    ]

    matches = search_transform_matches(
        query,
        db,
        max_depth=2,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )
    assert matches == []


def test_binomial_transform_hits_powers_of_two(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A930000 1,2,4,8,16\nA930001 1,1,1,1,1\n", encoding="utf-8")
    names.write_text("A930000 Powers of two\nA930001 Ones\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=6)

    query = parse_query("1,1,1,1,1")
    transforms = default_transforms(
        scale_values=(),
        shift_values=(),
        allow_diff=False,
        allow_partial_sum=False,
        allow_abs=False,
        allow_gcd_norm=False,
        allow_binomial=True,
    )

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )
    ids = {m.id for m in matches}
    assert "A930000" in ids


def test_euler_transform_hits_omega_like(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A940000 0,1,1,1,1,1\nA940001 0,1,3,4,7,6\n", encoding="utf-8")
    names.write_text("A940000 Ones-offset\nA940001 Euler transform of ones\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=8)

    query = parse_query("0,1,1,1,1,1")
    transforms = default_transforms(
        scale_values=(),
        shift_values=(),
        allow_diff=False,
        allow_partial_sum=False,
        allow_abs=False,
        allow_gcd_norm=False,
        allow_euler=True,
    )

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )
    ids = {m.id for m in matches}
    assert "A940001" in ids

def test_constant_collapsing_chain_is_dropped(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A900010 2,2,2,2,2",
                "A900011 3,4,5,6,7",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A900010 Constant twos",
                "A900011 Sample linear",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("3,4,5,6")
    transforms = [make_affine(0, 2)]

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )
    ids = [m.id for m in matches]
    # Constant transform outputs are now filtered for non-constant queries
    assert "A900010" not in ids


def test_full_scan_prefers_best_scoring_match(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A910000 2,3,4",
                "A910001 2,4,6,8",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A910000 Shifted naturals",
                "A910001 Doubled naturals",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,2,3,4")
    transforms = [make_shift(1), make_scale(2)]

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=1,
        full_scan=True,
    )

    assert matches
    assert matches[0].id == "A910001"


def test_transform_search_respects_max_time(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,2,3,4,5")
    transforms = [make_shift(0), make_scale(2)]  # produces two chains at depth=1

    times = iter([0.0, 0.0, 2.0])  # start, first chain, second chain

    def fake_time():
        return next(times)

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        full_scan=True,
        max_time_s=1.0,
        time_fn=fake_time,
    )
    # Only first chain processed before time cap triggers
    assert len(matches) == 1


def test_transform_search_deduplicates_same_transformed_terms(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A920000 1,1,1,1\n", encoding="utf-8")
    names.write_text("A920000 Ones\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,-1,1,-1")
    transforms = [abs_transform(), make_scale(-1)]

    matches = search_transform_matches(
        query,
        db,
        max_depth=2,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )
    # abs(q) and scale(-1)->abs both collapse to constants; filtered for non-constant query
    ids = [m.id for m in matches]
    assert ids == []


def test_transform_results_dedup_by_id(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A920000 2,4,6,8",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A920000 Doubled naturals", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,2,3,4")
    transforms = [make_scale(2), make_affine(2, 0)]

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )

    assert len(matches) == 1
    assert matches[0].id == "A920000"


def test_constant_outputs_filtered_for_nonconstant_query(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A930100 1,1,1,1,1",
                "A930101 1,2,3,4,5",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A930100 Ones\nA930101 Naturals\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("1,2,3,4,5")
    from oeis_matcher.transforms import run_length_encode_transform

    transforms = [run_length_encode_transform()]

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        full_scan=True,
    )
    ids = {m.id for m in matches}
    assert "A930100" not in ids
