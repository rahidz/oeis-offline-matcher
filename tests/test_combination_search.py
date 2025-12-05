from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.combination_search import (
    search_two_sequence_combinations,
    search_pointwise_two_sequence_combinations,
    search_convolution_two_sequence_combinations,
)
from oeis_matcher.query import parse_query
from oeis_matcher.storage import iter_sequences
from oeis_matcher.candidates import get_candidate_bucket


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A300000 1,2,3,4,5,6",
                "A300001 1,1,1,1,1,1",
                "A300002 0,2,4,6,8,10",
                "A300003 10,10,10,10,10,10",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A300000 Naturals",
                "A300001 Ones",
                "A300002 Evens",
                "A300003 Tens",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_combination_sum_of_two_sequences(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("3,5,7,9,11")
    candidates = list(iter_sequences(db))

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(1, 2),
        max_shift=0,
        limit=5,
    )

    assert combos
    match = next(m for m in combos if m.ids == ("A300000", "A300001"))
    assert match.coeffs == (2, 1)
    assert match.shifts == (0, 0)
    assert match.latex_expression and "\\mathrm{" in match.latex_expression


def test_combo_scoring_prefers_smaller_coeffs():
    # Same length, different coeff magnitudes → smaller coeffs get higher score
    from oeis_matcher.combination_search import _combo_score

    score_small = _combo_score(5, (1, 1), (0, 0))
    score_big = _combo_score(5, (3, 2), (0, 0))
    assert score_small > score_big


def test_combo_score_popularity_bonus():
    from oeis_matcher.combination_search import _combo_score

    base = _combo_score(5, (1, 1), (0, 0), pop_bonus=0)
    boosted = _combo_score(5, (1, 1), (0, 0), pop_bonus=2)  # two popular keyword hits
    assert boosted > base


def test_combination_with_shift(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("14,16,18")
    candidates = list(iter_sequences(db))

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(1,),
        max_shift=3,
        limit=5,
    )

    assert combos
    match = next(m for m in combos if m.ids == ("A300002", "A300003"))
    assert match.coeffs == (1, 1)
    assert match.shifts == (2, 0)


def test_combination_with_negative_shift(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A320000 20,30,40,50",
                "A320001 90,190,290,390",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A320000 Seq1\nA320001 Seq2\n", encoding="utf-8")

    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    # Combination: a(n) = A320000(n) + A320001(n-1) matches q_slice [120,230,340]
    query = parse_query("999,120,230,340")
    candidates = list(iter_sequences(db))

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(1,),
        max_shift=0,
        max_shift_back=1,
        limit=5,
    )

    assert combos
    match = next(m for m in combos if m.ids == ("A320000", "A320001"))
    assert match.shifts == (0, -1)
    assert match.length == 3  # overlap after accounting for back shift
    assert "n-1" in match.expression
    assert match.latex_expression and "n-1" in match.latex_expression


def test_combination_max_checks_respected(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("3,5,7,9,11")
    candidates = list(iter_sequences(db))

    # With coeffs ordered so match occurs after two trials, allow two checks.
    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(2, 1),
        max_shift=0,
        limit=5,
        max_checks=2,
    )
    assert combos  # found before hitting limit

    # With reversed coeff ordering, the first check will fail and search stops.
    combos2 = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(1, 2),
        max_shift=0,
        limit=5,
        max_checks=1,
    )
    assert combos2 == []


def test_combination_respects_max_time(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("3,5,7,9,11")
    candidates = list(iter_sequences(db))

    def make_time_fn():
        calls = [0.0, 1.0]  # second call exceeds threshold

        def _time():
            return calls.pop(0) if calls else 1.0

        return _time

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=tuple(range(-3, 4)),
        max_shift=2,
        limit=5,
        max_time_s=0.5,
        time_fn=make_time_fn(),
    )
    # Early exit before finding the known combination
    assert combos == []


def test_combination_respects_max_combinations(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("3,5,7,9,11")
    candidates = list(iter_sequences(db))

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(2, 1),
        max_shift=0,
        limit=5,
        max_combinations=1,  # too small to find solution on second try
    )
    assert combos == []


def test_bucket_prefers_length_when_trimming(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A000100 1,2,3",
                "A000200 1,2,3,4,5,6,7,8,9,10",
                "A000150 1,2,3,4",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000100 Len3",
                "A000200 Len10",
                "A000150 Len4",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    query = parse_query("1,2,3")
    bucket = get_candidate_bucket(query, db, max_records=2, fill_unfiltered=False)
    kept_ids = [rec.id for rec in bucket.records]
    assert kept_ids == ["A000100", "A000150"]  # lengths closest to query length 3


def test_three_sequence_combination_found(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    # q = A300000 + A300001 - A300002
    query = parse_query("2,1,0,-1,-2,-3")
    candidates = list(iter_sequences(db))

    from oeis_matcher.combination_search import search_three_sequence_combinations

    triples = search_three_sequence_combinations(
        query,
        candidates,
        coeffs=(-1, 1),
        max_shift=0,
        limit=5,
        max_candidates=4,
    )

    assert triples
    match = next(m for m in triples if m.ids == ("A300000", "A300001", "A300002"))
    assert match.coeffs == (1, 1, -1)


def test_component_transform_diff_enables_match(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A310000 1,2,3,4,5,6",
                "A310001 0,0,0,0,0,0",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A310000 Naturals",
                "A310001 Zeros",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    # diff of naturals = ones
    query = parse_query("1,1,1,1,1")
    candidates = list(iter_sequences(db))

    from oeis_matcher.combination_search import search_two_sequence_combinations, resolve_component_transforms

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(1, 0),
        max_shift=0,
        limit=5,
        max_candidates=4,
        component_transforms=resolve_component_transforms(["diff", "id"]),
    )

    assert combos
    match = next(m for m in combos if m.ids[0] == "A310000")
    assert match.component_transforms and match.component_transforms[0] == "diff"


def test_real_combo_lucas_from_fibonacci(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A000045 0,1,1,2,3,5,8,13",
                "A999011 0,1,1,2,3,5,8,13",  # fib copy to allow two-sequence combo
                "A000204 2,1,3,4,7,11,18,29",  # Lucas numbers
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000045 Fibonacci",
                "A999011 Fibonacci copy",
                "A000204 Lucas",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    query = parse_query("2,1,3,4,7,11")
    candidates = list(iter_sequences(db))

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(-3, -2, -1, 1, 2, 3),
        max_shift=0,
        max_shift_back=1,
        limit=5,
    )
    assert combos
    hits = [
        c
        for c in combos
        if c.ids == ("A000045", "A999011")
        and set(c.coeffs) == {1, 2}
        and (c.shifts in {(0, -1), (-1, 0)})
    ]
    assert hits
def test_rational_coefficients_found(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A700000 2,4,6,8,10\nA700001 1,1,1,1,1\n", encoding="utf-8")
    names.write_text("A700000 Evens\nA700001 Ones\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    # q = 0.5 * evens + 1 * ones -> forces fractional coefficient on evens
    query = parse_query("2,3,4,5,6")
    candidates = list(iter_sequences(db))

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(),  # ignored
        max_shift=0,
        limit=5,
        use_rational=True,
    )
    assert combos
    match = combos[0]
    assert str(match.coeffs[0]) in {"1/2", "0.5"}
    assert str(match.coeffs[1]) in {"1", "1/1"}


def test_pointwise_product_combo(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A600000 1,2,3,4,5",
                "A600001 2,3,4,5,6",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A600000 S1\nA600001 S2\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)

    # Product sequence 2,6,12,20 comes from S1*S2 with no shifts
    query = parse_query("2,6,12,20")
    candidates = list(iter_sequences(db))

    combos = search_pointwise_two_sequence_combinations(
        query,
        candidates,
        ops=("mul",),
        max_shift=0,
        limit=5,
        max_candidates=2,
    )
    assert combos
    match = next(m for m in combos if set(m.ids) == {"A600000", "A600001"})
    assert "*" in match.expression


def test_cauchy_convolution_combo(tmp_path: Path):
    stripped = tmp_path / "stripped_cauchy.txt"
    names = tmp_path / "names_cauchy.txt"
    stripped.write_text(
        "\n".join(
            [
                "A610000 1,2,3,4,5,6",  # a_n = n+1
                "A610001 1,1,1,1,1,1",  # ones
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A610000 Incr\nA610001 Ones\n", encoding="utf-8")
    db = tmp_path / "oeis_cauchy.db"
    build_index(stripped, names, None, db, max_terms=8)

    # Cauchy conv of (n+1) with ones gives partial sums: 1,3,6,10
    query = parse_query("1,3,6,10")
    candidates = list(iter_sequences(db))

    combos = search_convolution_two_sequence_combinations(
        query,
        candidates,
        ops=("cauchy",),
        max_length=8,
        limit=5,
        max_candidates=4,
        max_checks=1000,
    )
    assert combos
    ids_pairs = [set(m.ids) for m in combos]
    assert {"A610000", "A610001"} in ids_pairs


def test_dirichlet_convolution_combo(tmp_path: Path):
    stripped = tmp_path / "stripped_dir.txt"
    names = tmp_path / "names_dir.txt"
    stripped.write_text(
        "\n".join(
            [
                "A620000 1,1,1,1,1,1",  # ones: a(n)=1
                "A620001 1,2,3,4,5,6",  # identity: a(n)=n
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A620000 Ones\nA620001 Id\n", encoding="utf-8")
    db = tmp_path / "oeis_dir.db"
    build_index(stripped, names, None, db, max_terms=8)

    # Dirichlet conv of ones with id gives sigma(n): 1,3,4,7 for n=1..4
    query = parse_query("1,3,4,7")
    candidates = list(iter_sequences(db))

    combos = search_convolution_two_sequence_combinations(
        query,
        candidates,
        ops=("dirichlet",),
        max_length=8,
        limit=5,
        max_candidates=4,
        max_checks=1000,
    )
    assert combos
    ids_pairs = [set(m.ids) for m in combos]
    assert {"A620000", "A620001"} in ids_pairs
