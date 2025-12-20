#!/usr/bin/env python
"""
Small, reproducible benchmark sweeps for the OEIS matcher.

This is meant to answer the TODO questions:
- How does transform search cost change by transform family + depth?
- How does combo search cost change by candidate bucket size + shift range?

It intentionally avoids network calls and uses deterministic synthetic data
for combo sweeps, so results are comparable across runs.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oeis_matcher.combination_search import search_two_sequence_combinations
from oeis_matcher.config import load_config
from oeis_matcher.models import SequenceQuery, SequenceRecord
from oeis_matcher.query import parse_query
from oeis_matcher.transform_search import search_transform_matches
from oeis_matcher.transforms import default_transforms


def _ms(fn):
    start = time.perf_counter()
    out = fn()
    return (time.perf_counter() - start) * 1000.0, out


def _bench(fn, *, repeats: int) -> tuple[float, object]:
    best_ms: float | None = None
    best_out: object | None = None
    for _ in range(max(1, int(repeats))):
        ms, out = _ms(fn)
        if best_ms is None or ms < best_ms:
            best_ms = ms
            best_out = out
    return float(best_ms or 0.0), best_out


def _print_md_table(headers: list[str], rows: list[list[str]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        print("| " + " | ".join(r) + " |")


def run_transform_sweep(db: Path, *, repeats: int) -> None:
    print("\n## Transform sweep\n")
    query = parse_query("0,1,1,2,3,5,8,13", min_match_length=3, allow_subsequence=False)

    cases = [
        (
            "affine+shift only",
            dict(
                scale_values=(-3, -2, -1, 2, 3),
                shift_values=(1, 2),
                allow_diff=False,
                allow_partial_sum=False,
                allow_abs=False,
                allow_gcd_norm=False,
            ),
        ),
        (
            "basic (+diff,+psum,+abs,+gcd)",
            dict(
                scale_values=(-3, -2, -1, 2, 3),
                shift_values=(1, 2),
                allow_diff=True,
                allow_partial_sum=True,
                allow_abs=True,
                allow_gcd_norm=True,
            ),
        ),
        (
            "basic + (digitsum10, mod2, popcount)",
            dict(
                scale_values=(-3, -2, -1, 2, 3),
                shift_values=(1, 2),
                allow_diff=True,
                allow_partial_sum=True,
                allow_abs=True,
                allow_gcd_norm=True,
                allow_digit_sum=True,
                digit_sum_bases=(10,),
                modulus_values=(2,),
                allow_popcount=True,
            ),
        ),
    ]

    rows: list[list[str]] = []
    for depth in (1, 2):
        for label, kwargs in cases:
            transforms = default_transforms(**kwargs)

            def _run():
                return search_transform_matches(
                    query,
                    db,
                    max_depth=depth,
                    transforms=transforms,
                    limit=20,
                    full_scan=False,
                    max_time_s=2.0,
                )

            ms, hits = _bench(_run, repeats=repeats)
            rows.append(
                [
                    label,
                    str(depth),
                    str(len(transforms)),
                    f"{ms:.1f}",
                    str(len(hits)),
                ]
            )

    _print_md_table(["family", "depth", "#transforms", "ms", "#hits"], rows)


def _synthetic_candidates(*, n: int, length: int, seed: int) -> list[SequenceRecord]:
    rng = random.Random(seed)
    out: list[SequenceRecord] = []
    for i in range(n):
        sid = f"S{i:05d}"
        terms = [rng.randint(-20, 30) for _ in range(length)]
        if all(t == 0 for t in terms):
            terms[0] = 1
        out.append(SequenceRecord(id=sid, terms=terms, length=len(terms), name=f"synthetic {sid}"))
    out.sort(key=lambda r: r.id)
    return out


def run_combo_sweep(*, repeats: int) -> None:
    print("\n## Combo sweep (synthetic candidates)\n")
    coeffs = tuple([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])

    base = _synthetic_candidates(n=80, length=12, seed=0)
    a, b = 2, -3
    qlen = 8
    query_terms = [a * base[0].terms[i] + b * base[1].terms[i] for i in range(qlen)]
    query = SequenceQuery(terms=query_terms, min_match_length=3, allow_subsequence=False)

    rows: list[list[str]] = []
    for n in (20, 40, 80):
        cand = base[:n]
        for max_shift in (0, 1, 2, 3):
            alignments = (n * (n - 1) // 2) * (max_shift + 1) * (max_shift + 1)
            max_checks = alignments * (len(coeffs) * len(coeffs)) + 10

            def _run():
                return search_two_sequence_combinations(
                    query,
                    cand,
                    coeffs=coeffs,
                    max_shift=max_shift,
                    max_shift_back=0,
                    limit=5,
                    max_candidates=None,
                    max_checks=max_checks,
                    max_time_s=None,
                )

            ms, hits = _bench(_run, repeats=repeats)
            rows.append(
                [
                    str(n),
                    str(max_shift),
                    str(alignments),
                    f"{ms:.1f}",
                    str(len(hits)),
                ]
            )

    _print_md_table(["candidates", "max_shift", "alignments", "ms", "#hits"], rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite db path (defaults from config)")
    parser.add_argument("--repeats", type=int, default=3, help="Repeat each case N times and keep the best time")
    args = parser.parse_args()

    cfg = load_config()
    db = Path(args.db or cfg["paths"]["db"])
    if not db.exists():
        print(f"DB missing at {db}. Run oeis build-index first.")
        return 1

    run_transform_sweep(db, repeats=args.repeats)
    run_combo_sweep(repeats=args.repeats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
