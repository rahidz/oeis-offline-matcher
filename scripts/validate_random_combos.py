#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from oeis_matcher.selfcheck import run_random_combo_trials


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    ap = argparse.ArgumentParser(description="Random sanity checks for combo discovery against a built OEIS DB")
    ap.add_argument("--db", default="data/processed/oeis.db", help="Path to built OEIS SQLite DB")
    ap.add_argument("--seed", type=int, default=0, help="RNG seed (deterministic)")
    ap.add_argument("--trials", type=int, default=10, help="How many random trials to run")
    ap.add_argument("--qlen", type=int, default=8, help="Query length to synthesize per trial (>=5 recommended)")
    ap.add_argument("--min-length", type=int, default=30, help="Minimum OEIS stored length for component sequences")
    ap.add_argument("--scan-stride", type=int, default=100, help="Prefer A-numbers divisible by this for expanded pair tests")
    ap.add_argument("--pair-max-time", type=float, default=6.0, help="Max seconds per expanded-pair trial")
    ap.add_argument("--pointwise-trials", type=int, default=0, help="Also run N random pointwise (mul) trials")
    ap.add_argument("--convolution-trials", type=int, default=0, help="Also run N random convolution trials (cauchy/dirichlet)")
    ap.add_argument("--pointwise-max-time", type=float, default=0.75, help="Max seconds per pointwise trial")
    ap.add_argument("--convolution-max-time", type=float, default=0.75, help="Max seconds per convolution trial")
    ap.add_argument("--pairs-only", action="store_true", help="Only run expanded pair trials")
    ap.add_argument("--triples-only", action="store_true", help="Only run triple-in-bucket trials")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        ap.error(f"DB not found: {db_path} (run: oeis sync && oeis build-index)")

    trials, summary = run_random_combo_trials(
        db_path=db_path,
        trials=int(args.trials),
        pointwise_trials=int(args.pointwise_trials),
        convolution_trials=int(args.convolution_trials),
        seed=int(args.seed),
        qlen=int(args.qlen),
        min_length=int(args.min_length),
        scan_stride=int(args.scan_stride),
        pair_max_time_s=float(args.pair_max_time),
        pointwise_max_time_s=float(args.pointwise_max_time),
        convolution_max_time_s=float(args.convolution_max_time),
        pairs_only=bool(args.pairs_only),
        triples_only=bool(args.triples_only),
    )

    # Preserve the prior human-readable output style.
    counts: dict[str, int] = {}
    for t in trials:
        counts[t.kind] = counts.get(t.kind, 0) + 1
        label = f"{t.kind} {counts[t.kind]:02d}"
        status = "OK  " if t.ok else "FAIL"
        print(f"[{label}] {status} {t.expression}")

    print(f"\nSummary: {summary['passes']} ok, {summary['fails']} failed")
    return 0 if int(summary["fails"]) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
