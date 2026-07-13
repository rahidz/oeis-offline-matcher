from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from oeis_matcher.build_index import build_index


def _mini_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 3,14,26",
                "A100001 1,3,14,26,99",
                "A100002 3,14,2026",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A100000 Exact",
                "A100001 Contains subsequence later",
                "A100002 Different date form",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)
    return db


def test_oeis_date_prints_expected_queries_for_pi_day():
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "oeis-date"
    proc = subprocess.run(
        [sys.executable, str(script), "--print-only", "2026-03-14"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "date\t2026-03-14"
    got = dict(line.split("\t", 1) for line in lines[1:])
    assert got["m,d,yyyy"] == "3,14,2026"
    assert got["m,d,yy"] == "3,14,26"
    assert got["digits(m,d,yyyy)"] == "3,1,4,2,0,2,6"
    assert got["digits(m,d,yy)"] == "3,1,4,2,6"
    assert got["md,yyyy"] == "314,2026"
    assert got["md,yy"] == "314,26"
    assert got["yyyy,m,d"] == "2026,3,14"
    assert got["yy,m,d"] == "26,3,14"
    assert got["century,yy,m,d"] == "20,26,3,14"
    assert got["m,d,century,yy"] == "3,14,20,26"
    assert got["digits(yyyy,m,d)"] == "2,0,2,6,3,1,4"
    assert got["digits(yy,m,d)"] == "2,6,3,1,4"
    assert got["yyyy,md"] == "2026,314"
    assert got["ymd"] == "20260314"
    assert got["yyyy,day_of_year"] == "2026,73"


def test_oeis_date_reports_exact_and_subsequence_matches(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "oeis-date"
    db = _mini_db(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(script), "2026-03-14", "--db", str(db), "--limit", "10"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "[2/15] m,d,yy: 3,14,26" in proc.stdout
    assert "A100000 [prefix @ 0] len=3 - Exact" in proc.stdout
    assert "A100001 [subsequence @ 1] len=3 - Contains subsequence later" in proc.stdout
    assert "Transform matches:" not in proc.stdout
