#!/usr/bin/env python
"""
Measure index build time on supplied stripped/names/keywords files.
Usage:
  scripts/bench_build.py --stripped data/raw/stripped.gz --names data/raw/names.gz --keywords data/raw/keywords.txt --db /tmp/oeis_bench.db
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oeis_matcher.build_index import build_index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stripped", required=True)
    ap.add_argument("--names", required=False)
    ap.add_argument("--keywords", required=False)
    ap.add_argument("--oeisdata", required=False)
    ap.add_argument("--db", required=True)
    ap.add_argument("--max-terms", type=int, default=128)
    args = ap.parse_args()

    start = time.perf_counter()
    stats = build_index(
        Path(args.stripped),
        Path(args.names) if args.names else None,
        Path(args.keywords) if args.keywords else None,
        Path(args.db),
        max_terms=args.max_terms,
        oeisdata_root=Path(args.oeisdata) if args.oeisdata else None,
    )
    elapsed = time.perf_counter() - start
    size_mb = Path(args.db).stat().st_size / (1024 * 1024) if Path(args.db).exists() else 0
    print(f"build time: {elapsed:.1f}s  inserted={stats['inserted']}  db_size={size_mb:.1f} MB  path={args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
