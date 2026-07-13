from __future__ import annotations

import math
import random
from fractions import Fraction
from pathlib import Path

import pytest

from oeis_matcher.build_index import build_index
from oeis_matcher.combination_search import (
    resolve_component_transforms,
    search_three_sequence_combinations,
    search_three_sequence_combinations_expanded,
    search_two_sequence_combinations,
    search_two_sequence_combinations_expanded,
    search_pointwise_two_sequence_combinations,
    search_convolution_two_sequence_combinations,
)
from oeis_matcher.query import parse_query
from oeis_matcher.storage import iter_sequences


def _build_db(tmp_path: Path, sequences: dict[str, list[int]]) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(f"{sid} {','.join(str(t) for t in terms)}" for sid, terms in sequences.items()),
        encoding="utf-8",
    )
    names.write_text("\n".join(f"{sid} {sid} test sequence" for sid in sequences) + "\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    max_terms = max((len(v) for v in sequences.values()), default=0)
    build_index(stripped, names, None, db, max_terms=max_terms)
    return db


def _random_sequences(rng: random.Random, *, n: int, length: int) -> dict[str, list[int]]:
    seqs: dict[str, list[int]] = {}
    for i in range(n):
        sid = f"A9{i:05d}"
        # Keep values moderately sized but with enough diversity to avoid accidental linear dependencies.
        terms = [rng.randint(-20, 30) for _ in range(length)]
        if all(t == 0 for t in terms):
            terms[0] = 1
        seqs[sid] = terms
    return seqs


def test_fuzz_random_pair_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(0)
    seqs = _random_sequences(rng, n=14, length=10)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    i, j = 2, 9
    id1, id2 = ids[i], ids[j]
    a, b = -2, 3

    qlen = 7
    query_terms = [a * seqs[id1][k] + b * seqs[id2][k] for k in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(a, b),
        max_shift=0,
        max_shift_back=0,
        limit=10,
        max_candidates=None,
        max_checks=200_000,
    )
    assert any(m.ids == (id1, id2) and m.coeffs == (a, b) and m.combined_terms == query_terms for m in hits)


def test_fuzz_random_triple_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(1)
    seqs = _random_sequences(rng, n=10, length=10)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    i, j, k = 1, 4, 7
    id1, id2, id3 = ids[i], ids[j], ids[k]
    a, b, c = 1, -1, 2

    qlen = 6
    query_terms = [a * seqs[id1][t] + b * seqs[id2][t] + c * seqs[id3][t] for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_three_sequence_combinations(
        query,
        candidates,
        coeffs=(a, b, c),
        max_shift=0,
        max_shift_back=0,
        limit=10,
        max_candidates=None,
        max_checks=500_000,
    )
    assert any(m.ids == (id1, id2, id3) and m.coeffs == (a, b, c) and m.combined_terms == query_terms for m in hits)


def test_fuzz_expanded_pair_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(2)
    seqs = _random_sequences(rng, n=18, length=12)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2 = ids[5], ids[11]
    a, b = 2, -3
    qlen = 5
    query_terms = [a * seqs[id1][t] + b * seqs[id2][t] for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)

    hits = search_two_sequence_combinations_expanded(
        query,
        db,
        coeffs=(a, b),
        limit=20,
        scan_strides=(1,),
        max_time_s=2.0,
        snippet_len=qlen,
    )
    assert any(set(m.ids) == {id1, id2} and set(m.coeffs) == {a, b} and m.combined_terms == query_terms for m in hits)


def test_fuzz_expanded_triple_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(3)
    seqs = _random_sequences(rng, n=12, length=12)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2, id3 = ids[0], ids[3], ids[10]
    a, b, c = -1, 1, 1
    qlen = 5
    query_terms = [a * seqs[id1][t] + b * seqs[id2][t] + c * seqs[id3][t] for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)

    hits = search_three_sequence_combinations_expanded(
        query,
        db,
        coeffs=(a, b, c),
        limit=20,
        max_anchors=len(seqs),  # exhaustive over this tiny DB
        scan_strides=(1,),
        max_time_s=2.0,
        snippet_len=qlen,
    )
    assert any(set(m.ids) == {id1, id2, id3} and set(m.coeffs) == {a, b, c} and m.combined_terms == query_terms for m in hits)


def test_fuzz_real_oeis_sequences_pair_combo(tmp_path: Path):
    # "Random OEIS sequences" in a deterministic, offline-friendly sense:
    # pick a random pair from a tiny built-in OEIS-ish fixture and ensure combo search recovers it.
    rng = random.Random(4)
    seqs = {
        "A000045": [0, 1, 1, 2, 3, 5, 8, 13, 21, 34],  # Fibonacci
        "A000040": [2, 3, 5, 7, 11, 13, 17, 19, 23, 29],  # primes
        "A000290": [0, 1, 4, 9, 16, 25, 36, 49, 64, 81],  # squares
        "A000012": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],  # ones
        "A000027": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  # naturals
    }
    db = _build_db(tmp_path, seqs)
    ids = sorted(seqs.keys())
    id1, id2 = rng.sample(ids, 2)
    id1, id2 = sorted((id1, id2))
    a, b = rng.choice([-2, -1, 1, 2]), rng.choice([-2, -1, 1, 2])
    if a == 0 or b == 0:
        raise AssertionError("unexpected zero coeff in test")

    qlen = 7
    query_terms = [a * seqs[id1][t] + b * seqs[id2][t] for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(a, b),
        max_shift=0,
        limit=20,
    )
    assert any(m.ids == (id1, id2) and m.coeffs == (a, b) and m.combined_terms == query_terms for m in hits)


def test_fuzz_random_pointwise_mul_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(5)
    seqs = _random_sequences(rng, n=12, length=12)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2 = ids[2], ids[8]
    qlen = 6
    query_terms = [seqs[id1][t] * seqs[id2][t] for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_pointwise_two_sequence_combinations(
        query,
        candidates,
        ops=("mul",),
        max_shift=0,
        max_shift_back=0,
        limit=10,
        max_candidates=None,
        max_checks=200_000,
    )
    assert any(set(m.ids) == {id1, id2} and m.combined_terms == query_terms for m in hits)


def test_fuzz_random_cauchy_convolution_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(6)
    seqs = _random_sequences(rng, n=10, length=12)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2 = ids[1], ids[7]
    qlen = 6

    # Cauchy convolution: c_n = sum_{k=0..n} a_k b_{n-k}
    query_terms: list[int] = []
    for n in range(qlen):
        s = 0
        for k in range(n + 1):
            s += seqs[id1][k] * seqs[id2][n - k]
        query_terms.append(s)

    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_convolution_two_sequence_combinations(
        query,
        candidates,
        ops=("cauchy",),
        max_length=16,
        limit=10,
        max_candidates=None,
        max_checks=200_000,
    )
    assert any(set(m.ids) == {id1, id2} and m.combined_terms == query_terms for m in hits)


def test_fuzz_random_dirichlet_convolution_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(7)
    seqs = _random_sequences(rng, n=10, length=16)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2 = ids[0], ids[6]
    qlen = 8

    # Dirichlet convolution on 1-based indices:
    #   c(n) = sum_{d|n} A(d) B(n/d)
    # using seq[i] as A(i+1).
    query_terms: list[int] = []
    for n in range(1, qlen + 1):
        s = 0
        for d in range(1, n + 1):
            if n % d != 0:
                continue
            i = d - 1
            j = n // d - 1
            s += seqs[id1][i] * seqs[id2][j]
        query_terms.append(s)

    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_convolution_two_sequence_combinations(
        query,
        candidates,
        ops=("dirichlet",),
        max_length=32,
        limit=10,
        max_candidates=None,
        max_checks=200_000,
    )
    assert any(set(m.ids) == {id1, id2} and m.combined_terms == query_terms for m in hits)


def test_fuzz_random_pointwise_gcd_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(8)
    seqs = _random_sequences(rng, n=12, length=12)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2 = ids[3], ids[10]
    qlen = 7
    query_terms = [math.gcd(seqs[id1][t], seqs[id2][t]) for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_pointwise_two_sequence_combinations(
        query,
        candidates,
        ops=("gcd",),
        max_shift=0,
        max_shift_back=0,
        limit=10,
        max_candidates=None,
        max_checks=200_000,
    )
    assert any(set(m.ids) == {id1, id2} and m.combined_terms == query_terms for m in hits)


def test_fuzz_random_pointwise_lcm_combo_is_discoverable(tmp_path: Path):
    rng = random.Random(9)
    seqs = _random_sequences(rng, n=12, length=12)
    db = _build_db(tmp_path, seqs)

    ids = sorted(seqs.keys())
    id1, id2 = ids[4], ids[11]
    qlen = 7

    def _lcm(a: int, b: int) -> int:
        g = math.gcd(a, b)
        if g == 0:
            return 0
        return abs(a // g * b)

    query_terms = [_lcm(seqs[id1][t], seqs[id2][t]) for t in range(qlen)]
    query = parse_query(",".join(str(x) for x in query_terms), min_match_length=3, allow_subsequence=False)
    candidates = list(iter_sequences(db))

    hits = search_pointwise_two_sequence_combinations(
        query,
        candidates,
        ops=("lcm",),
        max_shift=0,
        max_shift_back=0,
        limit=10,
        max_candidates=None,
        max_checks=200_000,
    )
    assert any(set(m.ids) == {id1, id2} and m.combined_terms == query_terms for m in hits)


@pytest.mark.parametrize("seed", [11, 29, 73])
def test_replay_seeded_rational_shift_and_component_paths(tmp_path: Path, seed: int):
    rng = random.Random(seed)
    seqs = _random_sequences(rng, n=8, length=12)
    seqs = {id_: [2 * term for term in terms] for id_, terms in seqs.items()}
    db = _build_db(tmp_path, seqs)
    candidates = list(iter_sequences(db))
    ids = sorted(seqs)

    id1, id2 = ids[0], ids[3]
    rational_terms = [seqs[id1][i] // 2 + 3 * seqs[id2][i] // 2 for i in range(7)]
    rational_query = parse_query(
        ",".join(map(str, rational_terms)), min_match_length=3, allow_subsequence=False
    )
    rational_hits = search_two_sequence_combinations(
        rational_query,
        candidates,
        coeffs=(),
        use_rational=True,
        max_checks=100_000,
        limit=20,
    )
    assert any(
        m.ids == (id1, id2) and m.coeffs == (Fraction(1, 2), Fraction(3, 2))
        for m in rational_hits
    ), f"replay with seed={seed}"

    id1, id2 = ids[1], ids[5]
    shifted_terms = [2 * seqs[id1][i + 1] - seqs[id2][i + 2] for i in range(6)]
    shifted_query = parse_query(
        ",".join(map(str, shifted_terms)), min_match_length=3, allow_subsequence=False
    )
    shifted_hits = search_two_sequence_combinations(
        shifted_query,
        candidates,
        coeffs=(2, -1),
        max_shift=2,
        max_checks=500_000,
        limit=20,
    )
    assert any(
        m.ids == (id1, id2) and m.coeffs == (2, -1) and m.shifts == (1, 2)
        for m in shifted_hits
    ), f"replay with seed={seed}"

    id1, id2 = ids[2], ids[6]
    diff = [b - a for a, b in zip(seqs[id1], seqs[id1][1:])]
    partial_sum: list[int] = []
    total = 0
    for term in seqs[id2]:
        total += term
        partial_sum.append(total)
    component_terms = [diff[i] - partial_sum[i] for i in range(7)]
    component_query = parse_query(
        ",".join(map(str, component_terms)), min_match_length=3, allow_subsequence=False
    )
    component_hits = search_two_sequence_combinations(
        component_query,
        candidates,
        coeffs=(1, -1),
        component_transforms=resolve_component_transforms(("id", "diff", "partial_sum")),
        max_checks=500_000,
        limit=20,
    )
    assert any(
        m.ids == (id1, id2)
        and m.coeffs == (1, -1)
        and m.component_transforms == ("diff", "partial_sum")
        for m in component_hits
    ), f"replay with seed={seed}"
