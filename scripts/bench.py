#!/usr/bin/env python
"""
Quick timing harness for OEIS matcher pipeline.
Requires a built SQLite db (defaults from config).
Usage: python scripts/bench.py
Optional env:
  OEIS_DB_PATH=/path/to/oeis.db
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oeis_matcher.api import analyze_sequence
from oeis_matcher.config import load_config


CASES = [
    ("Exact Fibonacci", "0,1,1,2,3,5,8", dict(similarity=0, combos=0, transform_limit=0)),
    ("Transform (scale)", "1,2,3,4,5", dict(similarity=0, combos=0, transform_limit=20)),
    ("Combo (small)", "3,5,7,9,11", dict(similarity=0, combos=5, combo_coeffs=(1, 2), combo_max_shift=1)),
    ("Triple (demo)", "2,1,0,-1,-2,-3", dict(similarity=0, combos=0, triples=5, combo_coeffs=(1, -1), combo_candidates=30, triple_candidates=30)),
]


def main():
    cfg = load_config()
    db = Path(cfg["paths"]["db"])
    print(f"Using db: {db}")
    if not db.exists():
        print("DB file missing; run oeis build-index first.")
        return 1

    for label, seq, opts in CASES:
        start = time.perf_counter()
        res = analyze_sequence(seq, db_path=db, **opts)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"{label:18s}: {elapsed:6.1f} ms  exact={len(res['exact_matches'])} transforms={len(res['transform_matches'])} combos={len(res['combinations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
