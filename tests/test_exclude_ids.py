from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from oeis_matcher.api import analyze_sequence, match_exact_terms, search_combinations, search_transforms
from oeis_matcher.build_index import build_index


def _build_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A910000 0,1,2,3,4,5,6,7,8,9",
                "A910001 0,1,2,3,4,5,6,7,8,9",
                "A910002 2,2,2,2,2,2,2,2,2,2",
                "A910003 2,2,2,2,2,2,2,2,2,2",
                "A920000 0,2,4,6,8,10,12,14,16,18",
                "A920001 1,1,1,1,1,1,1,1,1,1",
                "A920002 1,3,5,7,9,11,13,15,17,19",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A910000 Naturals copy one",
                "A910001 Naturals copy two",
                "A910002 Twos copy one",
                "A910003 Twos copy two",
                "A920000 Even numbers",
                "A920001 Ones",
                "A920002 Odd numbers",
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
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_cli_exclude_ids_applies_to_all_search_commands(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    db = _build_db(tmp_path)

    exact = _run(
        repo_root,
        [
            "match",
            "0,1,2,3,4,5",
            "--db",
            str(db),
            "--fast",
            "--limit",
            "1",
            "--exclude-id",
            "a910000",
            "--json",
        ],
    )
    assert [match["id"] for match in exact["matches"]] == ["A910001"]

    fielded = _run(
        repo_root,
        [
            "match",
            "name:naturals",
            "--db",
            str(db),
            "--exclude-ids",
            "A910000,A910001",
            "--json",
        ],
    )
    assert not fielded["matches"]

    transformed = _run(
        repo_root,
        [
            "tsearch",
            "1,3,5,7,9,11",
            "--db",
            str(db),
            "--fast",
            "--limit",
            "1",
            "--exclude-ids",
            "A910002,A920002",
            "--json",
        ],
    )
    assert [match["id"] for match in transformed["matches"]] == ["A910003"]

    combo_args = [
        "combo",
        "1,3,5,7,9,11",
        "--db",
        str(db),
        "--fast",
        "--coeffs",
        "1",
        "--candidates",
        "20",
        "--limit",
        "10",
        "--json",
    ]
    baseline_combo = _run(repo_root, combo_args)
    assert any("A920000" in match["ids"] for match in baseline_combo["combinations"])
    filtered_combo = _run(
        repo_root,
        combo_args
        + [
            "--exclude-id",
            "A920000",
            "--exclude-ids",
            "A910000,A910001",
        ],
    )
    assert filtered_combo["diagnostics"]["excluded_ids"] == ["A910000", "A910001", "A920000"]
    for family in (
        "combinations",
        "triple_combinations",
        "modclass_combinations",
        "pointwise_combinations",
        "convolution_combinations",
        "combined_combinations",
    ):
        assert all("A920000" not in match["ids"] for match in filtered_combo.get(family, []))

    analyzed = _run(
        repo_root,
        [
            "analyze",
            "0,1,2,3,4,5",
            "--db",
            str(db),
            "--deep",
            "--time-cap",
            "5",
            "--exclude-id",
            "A910000",
            "--json",
        ],
    )
    assert analyzed["diagnostics"]["excluded_ids"] == ["A910000"]
    assert all(match["id"] != "A910000" for match in analyzed["exact_matches"])
    assert all(match["id"] != "A910000" for match in analyzed["transform_matches"])
    assert all(row["id"] != "A910000" for row in analyzed["similarity"])
    for family in (
        "combinations",
        "triple_combinations",
        "modclass_combinations",
        "pointwise_combinations",
        "convolution_combinations",
        "combined_combinations",
    ):
        assert all("A910000" not in match["ids"] for match in analyzed.get(family, []))


def test_python_api_exclude_ids_preserves_requested_limits(tmp_path: Path):
    db = _build_db(tmp_path)

    exact = match_exact_terms(
        [0, 1, 2, 3, 4, 5],
        db_path=db,
        limit=1,
        exclude_ids="a910000",
    )
    assert [match.id for match in exact] == ["A910001"]

    transformed = search_transforms(
        [1, 3, 5, 7, 9, 11],
        db_path=db,
        max_depth=1,
        limit=1,
        scale_values=(),
        shift_values=(),
        allow_partial_sum=False,
        allow_abs=False,
        allow_gcd_norm=False,
        exclude_ids=["A910002"],
    )
    assert [match.id for match in transformed] == ["A910003"]

    combos = search_combinations(
        [1, 3, 5, 7, 9, 11],
        db_path=db,
        coeffs=(1,),
        candidate_cap=20,
        exclude_ids="A920000",
    )
    assert all("A920000" not in match.ids for match in combos)

    analyzed = analyze_sequence(
        [0, 1, 2, 3, 4, 5],
        db_path=db,
        exact_limit=1,
        transform_limit=5,
        similarity=5,
        combos=5,
        exclude_ids=["a910000"],
    )
    assert [match["id"] for match in analyzed["exact_matches"]] == ["A910001"]
    assert analyzed["diagnostics"]["excluded_ids"] == ["A910000"]
    assert all(match["id"] != "A910000" for match in analyzed["transform_matches"])
    assert all(row["id"] != "A910000" for row in analyzed["similarity"])
    assert all("A910000" not in match["ids"] for match in analyzed["combinations"])
