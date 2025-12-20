# Benchmarks (Dec 20, 2025)

Environment: Linux (WSL2), Python 3.12.3, local SSD. Data from `data/raw/stripped.gz` and `data/raw/names.gz`; DB built from full snapshot.

Note: numbers are *very* sensitive to OS filesystem cache (cold vs warm). Treat these as order-of-magnitude sanity checks, not strict SLAs.

## Build
- Command: `python scripts/bench_build.py --stripped data/raw/stripped.gz --names data/raw/names.gz --keywords data/raw/keywords.txt --db /tmp/oeis_bench.db`
- Result: ~19.4s wall, 390,388 sequences inserted, DB size ~212.5 MB at `/tmp/oeis_bench.db`.

## Query microbench (scripts/bench.py)
Using `data/processed/oeis.db` (warm cache):
- Exact Fibonacci: ~1.0 ms (exact=10, transforms=0, combos=0)
- Transform (scale): ~2.0 ms (exact=10, transforms=20, combos=0)
- Subsequence (offset): ~0.5 ms (exact=10, transforms=0, combos=0)
- Transform (deep): ~8.2 ms (exact=10, transforms=150, combos=0; depth=2, 2s cap)
- Combo (small): ~137 ms (exact=10, transforms=10, combos=0)
- Triple (demo): ~13 ms (exact=1, transforms=10, combos=0)

Subsequence matching is now fast because exact+subsequence matching is pushed into SQLite string predicates (only parsing terms for returned hits).

## Transform sweep (scripts/bench_sweep.py)
Command: `python scripts/bench_sweep.py --repeats 5`

| family | depth | #transforms | ms | #hits |
| --- | --- | --- | --- | --- |
| affine+shift only | 1 | 7 | 3.1 | 20 |
| basic (+diff,+psum,+abs,+gcd) | 1 | 11 | 2.6 | 20 |
| basic + (digitsum10, mod2, popcount) | 1 | 14 | 2.6 | 20 |
| affine+shift only | 2 | 7 | 2.5 | 20 |
| basic (+diff,+psum,+abs,+gcd) | 2 | 11 | 2.6 | 20 |
| basic + (digitsum10, mod2, popcount) | 2 | 14 | 2.7 | 20 |

## Combo sweep (scripts/bench_sweep.py)
Synthetic candidates (deterministic), measuring scaling with candidate bucket size and shift range.

| candidates | max_shift | alignments | ms | #hits |
| --- | --- | --- | --- | --- |
| 20 | 0 | 190 | 0.3 | 1 |
| 20 | 1 | 760 | 0.8 | 1 |
| 20 | 2 | 1710 | 1.8 | 1 |
| 20 | 3 | 3040 | 3.1 | 1 |
| 40 | 0 | 780 | 1.0 | 1 |
| 40 | 1 | 3120 | 3.3 | 1 |
| 40 | 2 | 7020 | 7.3 | 1 |
| 40 | 3 | 12480 | 11.9 | 1 |
| 80 | 0 | 3160 | 3.8 | 1 |
| 80 | 1 | 12640 | 13.0 | 1 |
| 80 | 2 | 28440 | 27.9 | 1 |
| 80 | 3 | 50560 | 48.7 | 1 |

## Profiles (scripts/profile_matchers.py)
If you see a perf regression, prefer running:
- `python scripts/profile_matchers.py --profile out.pstats --sort tottime`

## Notes / follow-ups
- For real-world workloads, the biggest remaining runtime risks are `--combo-unfiltered` + short queries (candidate explosion), and expanded DB-wide combo fallback when `--preset max` enables it.
- Future speedups likely come from deeper indexing (e.g., windowed-subsequence indexes) or compiled/vectorized inner loops once the heuristics stabilize.
