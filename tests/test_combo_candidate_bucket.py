from __future__ import annotations

from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.candidates import get_candidate_bucket
from oeis_matcher.combination_search import search_two_sequence_combinations
from oeis_matcher.query import parse_query
from oeis_matcher.storage import get_sequence_by_id


def _build_noisy_lucas_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"

    # Fibonacci (first-diff sign is nonneg), plus many "mixed-diff" noise sequences.
    # This exercises loosened combo candidate selection where filtering too aggressively
    # can exclude valid components.
    lines: list[str] = ["A000045 0,1,1,2,3,5,8,13,21,34"]
    name_lines: list[str] = ["A000045 Fibonacci"]

    # Nonnegative + mixed first differences: [1,0,1,0,1,0,...].
    # Use a bunch of ids so candidate filters can fill to a cap without relying on
    # the later `fill_unfiltered` fallback.
    for i in range(120):
        sid = f"A9{i:05d}"
        terms = [1 if (k % 2 == 0) else 0 for k in range(12)]
        lines.append(f"{sid} {','.join(str(t) for t in terms)}")
        name_lines.append(f"{sid} Noise{i}")

    stripped.write_text("\n".join(lines) + "\n", encoding="utf-8")
    names.write_text("\n".join(name_lines) + "\n", encoding="utf-8")

    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=20)
    return db


def test_loosened_bucket_includes_fibonacci_for_lucas_like_query(tmp_path: Path):
    db = _build_noisy_lucas_db(tmp_path)

    # Lucas prefix: mixed first differences.
    query = parse_query("2,1,3,4,7,11", allow_subsequence=False)
    bucket = get_candidate_bucket(
        query,
        db,
        exact_limit=50,
        similar_limit=50,
        max_records=50,
        fill_unfiltered=True,
        skip_prefix_filter=True,
    )
    assert any(rec.id == "A000045" for rec in bucket.records)


def test_combo_search_finds_lucas_self_shift_in_noisy_bucket(tmp_path: Path):
    db = _build_noisy_lucas_db(tmp_path)
    query = parse_query("2,1,3,4,7,11", allow_subsequence=False)
    bucket = get_candidate_bucket(
        query,
        db,
        exact_limit=80,
        similar_limit=80,
        max_records=80,
        fill_unfiltered=True,
        skip_prefix_filter=True,
    )
    fib = get_sequence_by_id(db, "A000045")
    assert fib is not None
    candidates = [fib] + [r for r in bucket.records if r.id != "A000045"]

    combos = search_two_sequence_combinations(
        query,
        candidates,
        coeffs=(1,),
        max_shift=1,
        max_shift_back=1,
        limit=20,
        max_candidates=80,
        max_checks=200_000,
    )
    assert any(
        m.ids == ("A000045", "A000045") and set(m.coeffs) == {1} and m.shifts == (-1, 1) and m.length == 5
        for m in combos
    )


def test_candidate_bucket_supports_explicit_provider_selection(tmp_path: Path):
    db = _build_noisy_lucas_db(tmp_path)
    query = parse_query("2,1,3,4,7,11", allow_subsequence=False)
    bucket = get_candidate_bucket(
        query,
        db,
        exact_limit=20,
        similar_limit=20,
        max_records=20,
        fill_unfiltered=False,
        skip_prefix_filter=True,
        candidate_providers=("exact", "expanded", "bogus"),
    )
    diag = bucket.provider_diagnostics
    assert diag.get("enabled") == ["exact", "expanded"]
    assert diag.get("unknown") == ["bogus"]
    assert "seed" not in {r for rs in bucket.provenance.values() for r in rs}
    assert "similarity" not in {r for rs in bucket.provenance.values() for r in rs}


def test_wide_prefilter_enables_exact_provider_in_prefix_mode_defaults(tmp_path: Path):
    db = _build_noisy_lucas_db(tmp_path)
    query = parse_query("2,1,3,4,7,11", allow_subsequence=False)
    base = get_candidate_bucket(
        query,
        db,
        exact_limit=20,
        similar_limit=20,
        max_records=20,
        fill_unfiltered=False,
        skip_prefix_filter=False,
        widen_prefilter=False,
    )
    wide = get_candidate_bucket(
        query,
        db,
        exact_limit=20,
        similar_limit=20,
        max_records=20,
        fill_unfiltered=False,
        skip_prefix_filter=False,
        widen_prefilter=True,
    )
    assert "exact" not in (base.provider_diagnostics.get("enabled") or [])
    assert "exact" in (wide.provider_diagnostics.get("enabled") or [])
