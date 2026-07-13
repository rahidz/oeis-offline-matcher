from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_combo_subcommand_runs_without_missing_args(tmp_path: Path):
    # Regression test: "oeis combo" used to crash because argparse didn't define
    # a few fields accessed by the combo code path (variance_band/growth_band/show_terms).
    from oeis_matcher.build_index import build_index

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A300000 1,2,3,4,5,6",
                "A300001 1,1,1,1,1,1",
                "A300002 0,2,4,6,8,10",
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
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            "3,5,7,9,11",
            "--db",
            str(db),
            "--deep",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr


def test_combo_subcommand_supports_convolution_json(tmp_path: Path):
    from oeis_matcher.build_index import build_index

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
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
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            "1,3,6,10",
            "--db",
            str(db),
            "--json",
            "--max",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert isinstance(payload["convolution_combinations"], list)


def test_combo_total_max_time_caps_pipeline_json(tmp_path: Path):
    # Ensure `oeis combo --time-cap` is accepted and produces valid output
    # even when the budget is essentially zero.
    from oeis_matcher.build_index import build_index

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A700000 1,2,3,4,5,6,7,8,9,10",
                "A700001 1,1,2,3,5,8,13,21,34,55",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A700000 Naturals\nA700001 Fibonacci\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            "1,2,3,4,5,6",
            "--db",
            str(db),
            "--max",
            "--time-cap",
            "0",
            "--json",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["query"] == [1, 2, 3, 4, 5, 6]
    assert isinstance(payload["combinations"], list)
    assert isinstance(payload["triple_combinations"], list)
    assert isinstance(payload["modclass_combinations"], list)
    assert isinstance(payload["pointwise_combinations"], list)
    assert isinstance(payload["convolution_combinations"], list)


def test_combo_json_coeffs_are_strings(tmp_path: Path):
    # Lean CLI keeps coeffs serialized as strings in JSON rows.
    from oeis_matcher.build_index import build_index

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                # evens: 0,2,4,6,8,...  (2*n)
                "A800000 0,2,4,6,8,10,12,14,16",
                # constant twos: 2,2,2,... (2)
                "A800001 2,2,2,2,2,2,2,2,2",
                # ones
                "A800002 1,1,1,1,1,1,1,1,1",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A800000 Evens\nA800001 Twos\nA800002 Ones\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            # target = evens + ones => 1,3,5,7,9,...
            "1,3,5,7,9,11,13,15",
            "--db",
            str(db),
            "--json",
            "--max",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["combinations"], payload
    coeffs = payload["combinations"][0]["coeffs"]
    assert all(isinstance(c, str) for c in coeffs)


def test_combo_json_includes_diagnostics(tmp_path: Path):
    from oeis_matcher.build_index import build_index

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A810000 0,1,4,9,16,25,36,49",  # squares
                "A810001 0,1,2,3,4,5,6,7",  # integers
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A810000 Squares\nA810001 Integers\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "combo",
            "0,2,6,12,20",
            "--db",
            str(db),
            "--max",
            "--json",
            # Keep this tiny; we only assert schema/diagnostics presence.
            "--time-cap",
            "1.0",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert "diagnostics" in payload
    diag = payload["diagnostics"]
    assert isinstance(diag, dict)
    assert "candidate_bucket" in diag
