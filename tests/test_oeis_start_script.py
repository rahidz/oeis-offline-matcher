from __future__ import annotations

from pathlib import Path
import subprocess


def test_startup_wrapper_preserves_child_stdout():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [str(root / "scripts" / "oeis-start"), "--no-status", "--", "python", "-c", "print('machine-output')"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "machine-output\n"
    assert "[oeis-start] root=" in proc.stderr
