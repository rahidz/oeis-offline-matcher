from __future__ import annotations

import json
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


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


def _build_fib_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A000045 0,1,1,2,3,5,8,13,21,34\n", encoding="utf-8")
    names.write_text("A000045 Fibonacci\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=30)
    return db


def test_cli_combo_json_includes_discovery_candidate_diagnostics(tmp_path: Path, capsys):
    db = _build_recurrence_db(tmp_path)
    rc = main(
        [
            "combo",
            "2,1,3,4,7,11,18,29",
            "--db",
            str(db),
            "--json",
            "--max",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    diag = payload.get("diagnostics") or {}
    bucket = diag.get("candidate_bucket") or {}
    assert "discovery_diagnostics" in bucket
    assert (bucket.get("discovery_diagnostics") or {}).get("enabled") is True


def test_cli_combo_json_includes_candidate_provenance_on_results(tmp_path: Path, capsys):
    db = _build_fib_db(tmp_path)
    rc = main(
        [
            "combo",
            "2,1,3,4,7,11",
            "--db",
            str(db),
            "--json",
            "--max",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    combos = payload.get("combinations") or []
    assert combos
    assert any("candidate_provenance" in row and any("seed" in rs for rs in row["candidate_provenance"]) for row in combos)


def test_cli_combo_candidate_provider_diagnostics_are_exposed(tmp_path: Path, capsys):
    db = _build_fib_db(tmp_path)
    rc = main(
        [
            "combo",
            "2,1,3,4,7,11",
            "--db",
            str(db),
            "--json",
            "--max",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    diag = payload.get("diagnostics") or {}
    bucket = diag.get("candidate_bucket") or {}
    prov = bucket.get("provider_diagnostics") or {}
    enabled = set(prov.get("enabled") or [])
    assert {"seed", "exact", "similarity", "expanded", "discovery"}.issubset(enabled)
