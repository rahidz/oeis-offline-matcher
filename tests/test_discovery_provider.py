from __future__ import annotations

from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.candidates import get_candidate_bucket
from oeis_matcher.discovery import discover_candidate_ids
from oeis_matcher.query import parse_query


def _build_recurrence_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A930001 2,1,3,4,7,11,18,29,47,76,123,199,322,521",
                "A930002 0,1,1,2,3,5,8,13,21,34,55,89,144,233",
                "A930003 1,0,1,1,2,3,5,8,13,21,34,55,89,144",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A930001 Lucas-like demo",
                "A930002 Fibonacci demo",
                "A930003 Basis demo",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=30)
    return db


def test_discover_candidate_ids_sympy_recurrence_hits_basis_sequences(tmp_path: Path):
    db = _build_recurrence_db(tmp_path)
    lucas_like = [2, 1, 3, 4, 7, 11, 18, 29, 47, 76]
    res = discover_candidate_ids(lucas_like, db, limit=12, tools=("sympy",))

    ids = set(res.ids)
    assert "A930001" in ids
    assert "A930002" in ids
    assert any(r.startswith("sympy:recurrence_basis") for r in (res.provenance.get("A930002") or []))
    assert res.diagnostics.get("enabled") is True


def test_candidate_bucket_discovery_injects_provenance(tmp_path: Path):
    db = _build_recurrence_db(tmp_path)
    query = parse_query("2,1,3,4,7,11,18,29", allow_subsequence=False)
    bucket = get_candidate_bucket(
        query,
        db,
        exact_limit=3,
        similar_limit=3,
        max_records=6,
        fill_unfiltered=False,
        skip_prefix_filter=True,
        enable_discovery=True,
        discovery_limit=8,
        discovery_max_time_s=2.0,
        discovery_tools=("sympy",),
    )

    assert bucket.discovery_ids
    assert "A930001" in {r.id for r in bucket.records}
    reasons = bucket.provenance.get("A930001") or []
    assert any(r.startswith("sympy:recurrence") for r in reasons), reasons
