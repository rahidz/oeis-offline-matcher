#!/usr/bin/env python
"""
Micro-profiles for exact, transform, and combo search on a built DB.
Outputs per-stage wall time. Use `python -m cProfile -s tottime scripts/profile_matchers.py`
for deeper detail.
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
    ("Exact short fib", "0,1,1,2,3,5", dict(transform_limit=0, similarity=0, combos=0)),
    ("Transform naturals", "1,2,3,4,5,6", dict(transform_limit=20, similarity=0, combos=0)),
    ("Combo small coeffs", "3,5,7,9,11", dict(transform_limit=0, similarity=0, combos=5, combo_coeffs=(1, 2), combo_max_shift=1)),
]


def main():
    cfg = load_config()
    db = Path(cfg["paths"]["db"])
    if not db.exists():
        print(f"DB missing at {db}. Build the index first.")
        return 1

    for label, seq, opts in CASES:
        start = time.perf_counter()
        res = analyze_sequence(seq, db_path=db, exact_limit=10, **opts)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"{label:20s} {elapsed:7.1f} ms  exact={len(res['exact_matches'])} transforms={len(res['transform_matches'])} combos={len(res['combinations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
