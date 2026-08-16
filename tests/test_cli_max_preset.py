from pathlib import Path
import subprocess
import sys


def _run_cli(tmp_path: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = dict(**{k: v for k, v in os.environ.items()}, PYTHONPATH=str(Path("src").resolve()))
    return subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli"] + args,
        cwd=str(tmp_path.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        check=False,
    )


import os


def test_preset_max_analyze_runs_with_extras(tmp_path: Path):
    # Build a tiny DB so analyze has something to hit.
    from oeis_matcher.build_index import build_index

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A800100 1,2,3,4,5,6,7,8,9,10",
                "A800101 2,3,5,7,11,13,17,19,23,29",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A800100 Simple\nA800101 Primes\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    # This query produces factorial-sized terms in some depth-two transform
    # chains; those terms should be skipped rather than crashing exact lookup.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "analyze",
            "1,4,12,31,73,162,346,721,1478,3002",
            "--db",
            str(db),
            "--max",
            "--time-cap",
            "2",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr


def test_preset_max_tsearch_streams_by_default(tmp_path: Path, capsys):
    from oeis_matcher.build_index import build_index
    from oeis_matcher.cli import main

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A900100 1,2,3,4,5,6,7,8,9,10\n", encoding="utf-8")
    names.write_text("A900100 Simple\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)

    rc = main(
        [
            "tsearch",
            "1,2,3,4,5",
            "--db",
            str(db),
            "--max",
            "--time-cap",
            "0.1",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Transform matches:" in out
