from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def _build_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A990000 1,2,3,4,5,6",
                "A990001 2,4,6,8,10,12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text("A990000 Naturals\nA990001 Evens\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=16)
    return db


def test_tsearch_accepts_shorthand_profile_and_time_cap(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(
        [
            "tsearch",
            "1,2,3,4,5",
            "--db",
            str(db),
            "--max",
            "--time-cap",
            "0",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == [1, 2, 3, 4, 5]
    assert isinstance(payload["matches"], list)


def test_profile_shorthand_conflict_returns_error(capsys):
    rc = main(["match", "1,2,3,4,5", "--fast", "--max"])
    assert rc == 2
    assert "Choose only one profile" in capsys.readouterr().err


def test_legacy_search_flag_rejected(capsys):
    rc = main(["match", "keyword:more", "--limit", "5"])
    assert rc == 2
    assert "Unsupported flag for `match`: --limit" in capsys.readouterr().err


def test_search_help_is_lean():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    proc = subprocess.run(
        [sys.executable, "-m", "oeis_matcher.cli", "analyze", "--help"],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "--fast" in out
    assert "--deep" in out
    assert "--max" in out
    assert "--time-cap" in out
    assert "--preset" not in out
    assert "--max-depth" not in out
    assert "--combo-max-checks" not in out
