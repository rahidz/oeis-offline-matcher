# Profiling and performance gates

Run the maintained local gate first:

```bash
python scripts/bench.py --repeats 5 --strict
```

It uses `docs/perf_envelopes.json` and exits nonzero on regression. Use `--json` for machine-readable results. The normal test suite also has a generous mini-DB smoke threshold in `tests/test_perf_smoke.py`.

For CLI startup and preset comparisons:

```bash
scripts/bench_hyperfine.sh /tmp/oeis-hyperfine.json
OEIS_BENCH_CPU=0 OEIS_BENCH_RUNS=12 scripts/bench_hyperfine.sh /tmp/pinned.json
```

For a call profile:

```bash
python scripts/profile_matchers.py --case "Transform short" \
  --profile /tmp/oeis.pstats --sort cumulative
python -m pstats /tmp/oeis.pstats
```

Use `scripts/bench_sweep.py --repeats 5` for transform-depth and candidate/shift scaling, and `scripts/bench_build.py` for full-snapshot build time and size.

Interpret the dominant frame before changing code:

- SQLite fetch/filter time usually calls for a better indexed query or avoiding record parsing.
- Combination-loop time should first be controlled with candidate, shift, check, and wall-time caps.
- Transform enumeration should first be controlled with depth, vocabulary, and complexity guards.
- Expanded prefix-index construction is intentionally exhaustive and memory-heavy; do not hide it behind an unbounded fallback.

The current before/after evidence, full commands, environment, acceleration decision, and worst cases are recorded in `docs/benchmarks.md`.
