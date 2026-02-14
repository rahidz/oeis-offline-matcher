#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Sequence

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oeis_matcher.api import match_exact_terms
from oeis_matcher.pattern_probe import (
    ModClassSlice,
    normalize_by_m_pow_cm,
    split_by_mod_class,
    try_fit_affine,
    valuations_2_5,
)
from oeis_matcher.query import parse_query


def _parse_int_terms(text: str) -> List[int]:
    q = parse_query(text, min_match_length=1, allow_subsequence=False)
    if any(t is None for t in q.terms):
        raise SystemExit("Wildcards ('?' or '*') are not supported in pattern probing input.")
    return [int(t) for t in q.terms if t is not None]


def _fmt_frac(x) -> str:
    if x.denominator == 1:
        return str(x.numerator)
    return f"{x.numerator}/{x.denominator}"


def _print_match_hits(
    label: str,
    terms: Sequence[int],
    *,
    db_path: Optional[Path],
    allow_subsequence: bool,
    limit: int,
    min_match_length: int,
) -> None:
    if len(terms) < min_match_length:
        return
    hits = match_exact_terms(
        terms,
        db_path=str(db_path) if db_path else None,
        min_match_length=min_match_length,
        allow_subsequence=allow_subsequence,
        limit=limit,
        show_terms=None,
    )
    if not hits:
        return
    print(f"\nMatches for {label}:")
    for h in hits[:limit]:
        off = f" @ {h.offset}" if h.offset else ""
        mt = f"{h.match_type}{off}"
        print(f"  {h.id} [{mt}] len={h.length} - {h.name}")


def _print_mod_slice(slice_: ModClassSlice, *, show: int) -> None:
    preview = ",".join(str(x) for x in slice_.terms[:show])
    print(f"n ≡ {slice_.r} (mod {slice_.k}): len={len(slice_.terms)} terms={preview}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Probe patterns by mod classes + simple normalizations, then try OEIS matches offline.",
    )
    ap.add_argument("sequence", help="Comma- or space-separated integers (no wildcards).")
    ap.add_argument("--k", type=int, default=4, help="Split by n mod k (default: 4).")
    ap.add_argument(
        "--n0",
        type=int,
        default=1,
        help="Index of the first provided term (default: 1, meaning terms[0] is a(1)).",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default from config).")
    ap.add_argument("--show", type=int, default=10, help="Preview this many terms per slice.")
    ap.add_argument("--no-match", action="store_true", help="Skip OEIS matching on derived sequences.")
    ap.add_argument("--match-limit", type=int, default=5, help="Max match hits per derived sequence.")
    ap.add_argument("--match-min-len", type=int, default=5, help="Minimum derived length to attempt match.")
    ap.add_argument("--subsequence", action="store_true", help="Allow subsequence matches (slower).")
    ap.add_argument(
        "--try-mpow",
        action="store_true",
        help="Try normalization a(n)/m^(2m) where n = k*m + r (prints ratios and simple affine fits).",
    )

    args = ap.parse_args(list(argv) if argv is not None else None)

    terms = _parse_int_terms(args.sequence)
    if not terms:
        raise SystemExit("No integers parsed from input.")

    print(f"Input length={len(terms)}; assuming a(n0)=a({args.n0}).")

    # Quick valuation scan for 2 and 5 (useful for spotting powers / 5-adic patterns).
    rows = valuations_2_5(terms, n0=args.n0)
    print("\nPer-term 2/5 valuations (first 12 rows):")
    for r in rows[:12]:
        print(f"  n={r.n:>3} a={r.value}  v2={r.v2:>2} v5={r.v5:>2}  rest={r.rest_2_5}")

    slices = split_by_mod_class(terms, args.k, n0=args.n0)
    print(f"\nSplit by n mod {args.k}:")
    for r in range(args.k):
        _print_mod_slice(slices[r], show=args.show)

    if args.try_mpow:
        print("\nNormalization: ratio(m) = a(k*m+r) / m^(2m)")
        for r in range(args.k):
            norm = normalize_by_m_pow_cm(slices[r], exp_coeff=2, require_m_positive=True)
            if not norm.ratios:
                continue
            ratios_preview = ", ".join(_fmt_frac(x) for x in norm.ratios[: min(8, len(norm.ratios))])
            print(f"  r={r}: ratios={ratios_preview}")
            if all(x.denominator == 1 for x in norm.ratios):
                ys = [int(x) for x in norm.ratios]
                fit = try_fit_affine(norm.m_values, ys)
                if fit is not None:
                    a, b = fit
                    print(f"       affine fit: ratio(m) = {_fmt_frac(a)}*m + {_fmt_frac(b)}")
                if len(set(ys)) == 1:
                    c = ys[0]
                    print(f"       constant: a(k*m+{r}) = {c} * m^(2m)")

    if not args.no_match:
        for r in range(args.k):
            _print_match_hits(
                f"n ≡ {r} (mod {args.k})",
                slices[r].terms,
                db_path=args.db,
                allow_subsequence=bool(args.subsequence),
                limit=int(args.match_limit),
                min_match_length=int(args.match_min_len),
            )
        v2_terms = [rr.v2 for rr in rows]
        v5_terms = [rr.v5 for rr in rows]
        _print_match_hits(
            "v2(a(n))",
            v2_terms,
            db_path=args.db,
            allow_subsequence=bool(args.subsequence),
            limit=int(args.match_limit),
            min_match_length=int(args.match_min_len),
        )
        _print_match_hits(
            "v5(a(n))",
            v5_terms,
            db_path=args.db,
            allow_subsequence=bool(args.subsequence),
            limit=int(args.match_limit),
            min_match_length=int(args.match_min_len),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
