#!/usr/bin/env python
"""Repeatable end-to-end API benchmark with an optional local strict gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oeis_matcher.api import analyze_sequence
from oeis_matcher.config import load_config


CASES = (
    ("exact_fibonacci", "Exact Fibonacci", "0,1,1,2,3,5,8", {"similarity": 0, "combos": 0, "transform_limit": 0}),
    ("transform_short", "Transform short", "1,2,3,4,5", {"similarity": 0, "combos": 0, "transform_limit": 20}),
    ("subsequence", "Subsequence", "2,3,5,8,13", {"similarity": 0, "combos": 0, "transform_limit": 0, "allow_subsequence": True}),
    ("transform_deep", "Transform deep", "1,2,3,4,5,6,7", {"similarity": 0, "combos": 0, "transform_limit": 150, "transform_depth": 2, "transform_max_time": 2.0}),
    ("combo_small", "Combo small", "3,5,7,9,11", {"similarity": 0, "transform_limit": 0, "combos": 5, "combo_coeffs": (1, 2), "combo_max_shift": 1, "combo_max_time": 2.0}),
    ("modclass", "Mod-class", "0,1,2,3,4,5,6,7,8,9,10,11", {"similarity": 0, "transform_limit": 0, "combos": 0, "modclass_limit": 5, "modclass_moduli": (2,), "modclass_max_time": 2.0}),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="SQLite DB path (defaults from config)")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--envelopes", default=ROOT / "docs" / "perf_envelopes.json", type=Path)
    parser.add_argument("--strict", action="store_true", help="Fail when a median exceeds its maintained envelope")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    db = Path(args.db or load_config()["paths"]["db"])
    if not db.exists():
        parser.error(f"DB missing at {db}; run oeis build-index first")
    envelope_doc = json.loads(args.envelopes.read_text()) if args.envelopes.exists() else {"cases": {}}
    rows = []
    for name, label, sequence, options in CASES:
        result = None
        for _ in range(max(0, args.warmups)):
            result = analyze_sequence(sequence, db_path=db, **options)
        samples = []
        for _ in range(max(1, args.repeats)):
            started = time.perf_counter()
            result = analyze_sequence(sequence, db_path=db, **options)
            samples.append(1000 * (time.perf_counter() - started))
        limit = (envelope_doc.get("cases", {}).get(name) or {}).get("max_median_ms")
        row = {
            "name": name,
            "label": label,
            "median_ms": round(median(samples), 3),
            "min_ms": round(min(samples), 3),
            "max_ms": round(max(samples), 3),
            "envelope_ms": limit,
            "passed": limit is None or median(samples) <= float(limit),
            "counts": {
                "exact": len(result["exact_matches"]),
                "transform": len(result["transform_matches"]),
                "combo": len(result["combinations"]),
                "modclass": len(result["modclass_combinations"]),
            },
        }
        rows.append(row)

    payload = {"schema_version": 1, "db": str(db), "repeats": max(1, args.repeats), "warmups": max(0, args.warmups), "cases": rows}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"DB: {db}  repeats={payload['repeats']} warmups={payload['warmups']}")
        for row in rows:
            gate = "" if row["envelope_ms"] is None else f" / {row['envelope_ms']:.0f} ms [{'ok' if row['passed'] else 'FAIL'}]"
            print(f"{row['label']:18s} {row['median_ms']:8.2f} ms median  ({row['min_ms']:.2f}-{row['max_ms']:.2f}){gate}")
    return int(args.strict and any(not row["passed"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
