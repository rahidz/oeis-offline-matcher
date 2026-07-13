from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from oeis_matcher.api import analyze_sequence
from oeis_matcher.build_index import build_index


def _db_with_identity_noise(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A910000 0,1,2,3,4,5,6,7,8,9",
                "A910001 0,0,0,0,0,0,0,0,0,0",
                "A910002 1,1,1,1,1,1,1,1,1,1",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A910000 Naturals from 0",
                "A910001 All zeros",
                "A910002 All ones",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)
    return db


def _run(repo_root: Path, argv: list[str]) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    proc = subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli", *argv],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_deep_and_max_exclude_exact_ids_from_other_analyze_stages(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _db_with_identity_noise(tmp_path)
    query = "0,1,2,3,4,5"

    baseline = analyze_sequence(
        query,
        db_path=db,
        exact_limit=5,
        transform_limit=10,
        similarity=5,
        combos=5,
    )
    exact_id = baseline["exact_matches"][0]["id"]
    assert exact_id == "A910000"
    assert (
        any(m["id"] == exact_id for m in baseline["transform_matches"])
        or any(row["id"] == exact_id for row in baseline["similarity"])
        or any(exact_id in m["ids"] for m in baseline["combinations"])
    ), baseline

    for preset in ("deep", "max"):
        payload = _run(
            repo_root,
            [
                "analyze",
                query,
                "--db",
                str(db),
                f"--{preset}",
                "--json",
                "--time-cap",
                "5.0",
            ],
        )
        assert payload["exact_matches"][0]["id"] == exact_id
        assert all(m["id"] != exact_id for m in payload["transform_matches"]), payload
        assert all(row["id"] != exact_id for row in payload["similarity"]), payload
        for family in (
            "combinations",
            "triple_combinations",
            "modclass_combinations",
            "pointwise_combinations",
            "convolution_combinations",
            "combined_combinations",
        ):
            assert all(exact_id not in m["ids"] for m in payload.get(family, [])), payload
        for ranked in payload.get("ranked_explanations", []):
            if ranked.get("family") == "transform":
                assert ranked.get("id") != exact_id, payload
            else:
                assert exact_id not in ranked.get("ids", []), payload
