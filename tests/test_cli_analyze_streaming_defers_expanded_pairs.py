from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from oeis_matcher.build_index import build_index


def _mini_db(tmp_path: Path) -> Path:
    base = Path(__file__).parent / "data" / "mini_oeis"
    db = tmp_path / "oeis.db"
    build_index(base / "stripped.txt", base / "names.txt", base / "keywords.txt", db, max_terms=20)
    return db


def test_analyze_streaming_defers_expanded_pairs_until_after_other_combo_stages(tmp_path: Path):
    """
    Streaming UX regression test: expanded DB-wide pair fallback should not run
    immediately after the regular pair search, since it can be expensive and can
    delay triple/pointwise/convolution hits.
    """
    db = _mini_db(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent

    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())

    # Use large values so the tiny fixture DB cannot accidentally explain the
    # query via pair/triple/pointwise/convolution operations with small coeffs.
    query = "10000,10001,10002,10003,10004,10005"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "oeis_matcher.cli",
            "analyze",
            query,
            "--db",
            str(db),
            "--max",
            "--time-cap",
            "5.0",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr

    out = proc.stdout
    pos_combo = out.find("Combination matches:")
    pos_pw = out.find("Pointwise combination matches:")
    pos_conv = out.find("Convolution combination matches:")
    pos_triple = out.find("Triple combination matches:")
    pos_exp = out.find("Expanded pair combinations:")

    assert pos_combo >= 0, out
    assert pos_pw >= 0, out
    assert pos_conv >= 0, out
    assert pos_triple >= 0, out
    assert pos_exp >= 0, out

    assert pos_combo < pos_pw < pos_conv < pos_triple < pos_exp, out
