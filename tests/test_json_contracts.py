from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator

from oeis_matcher.api import analyze_sequence
from oeis_matcher.build_index import build_index


ROOT = Path(__file__).resolve().parents[1]


def _mini_db(tmp_path: Path) -> Path:
    base = Path(__file__).parent / "data" / "mini_oeis"
    db = tmp_path / "oeis.db"
    build_index(base / "stripped.txt", base / "names.txt", base / "keywords.txt", db, max_terms=20)
    return db


def _run_json(*args: str) -> dict:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _schema(name: str) -> dict:
    return json.loads((ROOT / "docs" / "schemas" / name).read_text(encoding="utf-8"))


def test_analyze_cli_and_api_share_versioned_json_contract(tmp_path: Path):
    db = _mini_db(tmp_path)
    cli = _run_json(
        "analyze",
        "1,2,3,4,5,6",
        "--db",
        str(db),
        "--fast",
        "--json",
        "--tlimit",
        "0",
        "--no-subsequence-fallback",
    )
    api = analyze_sequence(
        "1,2,3,4,5,6",
        db_path=db,
        exact_limit=5,
        transform_limit=0,
        fallback_subsequence=False,
        show_formula=False,
    )

    validator = Draft202012Validator(_schema("analyze.schema.json"))
    validator.validate(cli)
    validator.validate(api)
    assert cli["schema_version"] == api["schema_version"] == 1
    assert cli["exact_matches"] == api["exact_matches"]
    assert set(cli) == set(api)


def test_combo_cli_matches_versioned_schema(tmp_path: Path):
    payload = _run_json(
        "combo",
        "0,2,6,12,20,30",
        "--db",
        str(_mini_db(tmp_path)),
        "--fast",
        "--json",
    )
    Draft202012Validator(_schema("combo.schema.json")).validate(payload)
    assert payload["schema_version"] == 1
