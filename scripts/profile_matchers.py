#!/usr/bin/env python
"""
Micro-profiles for exact, transform, and combo search on a built DB.
Default: print wall time per canned case.

Extras:
- `--case NAME` to profile a specific case.
- `--profile OUT.pstats` to emit cProfile stats for inspection.
- `--sort tottime` choose cProfile sort key.
"""

import argparse
import cProfile
import pstats
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
    ("Transform short", "1,2,3,4,5", dict(transform_limit=20, similarity=0, combos=0)),
    ("Combo small coeffs", "3,5,7,9,11", dict(transform_limit=0, similarity=0, combos=5, combo_coeffs=(1, 2), combo_max_shift=1)),
    ("Mod-class", "0,1,2,3,4,5,6,7,8,9,10,11", dict(transform_limit=0, similarity=0, combos=0, modclass_limit=5, modclass_moduli=(2,))),
]


def _run_case(label, seq, opts, db):
    start = time.perf_counter()
    res = analyze_sequence(seq, db_path=db, exact_limit=10, **opts)
    elapsed = (time.perf_counter() - start) * 1000
    print(f"{label:20s} {elapsed:7.1f} ms  exact={len(res['exact_matches'])} transforms={len(res['transform_matches'])} combos={len(res['combinations'])}")
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="SQLite DB path (defaults from config)")
    parser.add_argument("--case", help="Run a single case label", choices=[c[0] for c in CASES])
    parser.add_argument("--profile", metavar="OUT.pstats", help="Write cProfile stats to file")
    parser.add_argument("--sort", default="tottime", help="cProfile sort key (default: tottime)")
    args = parser.parse_args()

    cfg = load_config()
    db = Path(args.db or cfg["paths"]["db"])
    if not db.exists():
        print(f"DB missing at {db}. Build the index first.")
        return 1

    chosen = [c for c in CASES if args.case is None or c[0] == args.case]

    if args.profile:
        pr = cProfile.Profile()
        pr.enable()
        for label, seq, opts in chosen:
            _run_case(label, seq, opts, db)
        pr.disable()
        pr.dump_stats(args.profile)
        print(f"Profile written to {args.profile}")
        pstats.Stats(pr).sort_stats(args.sort).print_stats(20)
    else:
        for label, seq, opts in chosen:
            _run_case(label, seq, opts, db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
