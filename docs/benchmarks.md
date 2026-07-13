# Benchmarks (July 13, 2026)

Revision: `0cc05af` on `codex/v1-consolidation`. Snapshot: 397,352 sequences; `oeisdata` commit `7e846541fdca87dc2be0b6324ea96e3057310a24` (2026-07-13).

Environment: WSL2 Linux 6.6.114.1, Python 3.12.3, Intel Core i7-12700 (20 logical CPUs), local SSD. Query numbers below are warm-cache medians unless noted. They are guardrails, not cross-machine SLAs.

## Build

```bash
python scripts/bench_build.py \
  --stripped data/raw/stripped.gz \
  --names data/raw/names.gz \
  --keywords data/raw/keywords.txt \
  --db /tmp/oeis_bench_v1.db
```

Result: 20.6 s inside the harness, 397,352 rows, 331.4 MiB. Building indexes after the bulk insert reduced the same build from 31.3 s to 20.6 s (34%). The optimized working DB is 340 MiB because it acquired the new shifted-prefix indexes incrementally.

## End-to-end API envelope

Command: `python scripts/bench.py --repeats 5 --strict`. The maintained, deliberately loose failure thresholds live in `docs/perf_envelopes.json`.

| case | median ms | observed range ms | strict envelope ms |
| --- | ---: | ---: | ---: |
| Exact Fibonacci | 1.34 | 1.20-1.44 | 25 |
| Short transform search | 24.43 | 23.68-25.14 | 250 |
| Subsequence | 0.41 | 0.37-0.47 | 25 |
| Deep transform search | 25.46 | 24.86-27.48 | 250 |
| Small pair combination | 9.26 | 9.17-9.56 | 500 |
| Mod-class decomposition | 6.29 | 6.05-7.07 | 250 |

Strict mode exits nonzero only when a median crosses its envelope. This keeps normal machine noise from breaking the gate while still catching an order-of-magnitude regression.

## CLI process envelope (`hyperfine`)

Command: `OEIS_BENCH_RUNS=5 scripts/bench_hyperfine.sh /tmp/oeis-hyperfine.json`.

| command | mean ms | range ms |
| --- | ---: | ---: |
| `oeis match` Fibonacci | 81.0 | 78.7-84.2 |
| `oeis analyze --fast` pronic | 108.0 | 104.1-114.9 |
| `oeis analyze --deep --time-cap 10` pronic | 232.9 | 224.2-247.8 |

Set `OEIS_BENCH_CPU=0` to pin commands with `taskset`, and `OEIS_BENCH_RUNS=N` to change the repeat count.

## Kernel sweeps

Command: `python scripts/bench_sweep.py --repeats 5`.

| transform family | depth | transforms | ms | hits |
| --- | ---: | ---: | ---: | ---: |
| affine+shift only | 1 | 7 | 1.4 | 20 |
| basic (+diff,+psum,+abs,+gcd) | 1 | 11 | 2.6 | 20 |
| basic + digits/mod/popcount | 1 | 14 | 2.9 | 20 |
| affine+shift only | 2 | 7 | 1.2 | 20 |
| basic (+diff,+psum,+abs,+gcd) | 2 | 11 | 2.5 | 20 |
| basic + digits/mod/popcount | 2 | 14 | 3.0 | 20 |

Synthetic pair-combination scaling:

| candidates | max shift | alignments | ms |
| ---: | ---: | ---: | ---: |
| 20 | 0 | 190 | 0.3 |
| 20 | 3 | 3,040 | 2.9 |
| 40 | 0 | 780 | 1.0 |
| 40 | 3 | 12,480 | 12.1 |
| 80 | 0 | 3,160 | 3.9 |
| 80 | 3 | 50,560 | 50.4 |

## Profile-driven changes

- Short transformed queries previously fell back to parsing thousands of full records. Reusing the SQLite exact matcher reduced the representative warm case from about 188 ms to 24 ms while restoring deterministic ID ordering.
- Mod-class search previously materialized a DB-wide shifted-prefix map before looking up a few keys. Indexed SQLite lookups reduced the representative profile from its 3 s cap to about 12 ms cold-profiled / 6 ms warm.
- Cold SymPy discovery was accidentally invoking a broken Sage editable finder (roughly 9 s and 421 MiB). Suppressing that unrelated finder during discovery reduced the provider import/probe path to hundreds of milliseconds and restored global-budget behavior.
- Singleton prefix locations no longer allocate a list per key, trimming the exhaustive in-memory index, though DB-wide expanded search remains the principal memory-heavy path.

## Parallel/native acceleration decision

A same-process probe over representative deep transform and combination branches measured 37.8 ms sequential versus 42.5 ms with two threads (0.89x). A fresh two-process fork measured 38.5 ms versus 33.8 ms (1.14x), below the 20% material-win threshold and with extra memory/callback/checkpoint complexity. No parallel, NumPy/Numba, or Rust path is enabled for v1.0; the measured bottlenecks were SQLite access patterns, not a stable numeric kernel.

## Known worst cases

- `max` can build a full shifted-prefix map for expanded pair/pointwise/triple fallbacks. This is bounded by time/check caps but can use several hundred MiB on the full snapshot.
- `--combo-unfiltered` with short queries widens candidate ranking sharply.
- `--time-cap` governs analysis work. Python startup, JSON emission, and process teardown are outside that internal budget; exhaustive in-memory indexes can make teardown visibly slower.
- Wall-time cutoffs can stop at slightly different loop boundaries across machines. Fixed check/candidate caps are the reproducibility boundary.
