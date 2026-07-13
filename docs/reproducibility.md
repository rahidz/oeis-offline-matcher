# Reproducibility

OEIS changes continuously, so a reproducible result needs both the code revision and the local data snapshot—not just the query.

## Record a run

Save these alongside important output:

```bash
git rev-parse HEAD
scripts/oeis-start -- oeis status --json > status.json
sha256sum data/raw/stripped.gz data/raw/names.gz data/raw/keywords.txt data/processed/oeis.db > snapshot.sha256
scripts/oeis-start -- oeis analyze "1,1,2,3,5,8,13" --max --time-cap 600 --json > result.json
```

The status report includes timestamps, byte sizes, database health/counts, and the `oeisdata` commit when that checkout exists. SHA-256 hashes make the three exports and built database unambiguous.

Also record the exact command. Presets are concrete contracts in a given code revision, but their defaults may grow additively between releases. Use `--help-advanced` when you need to pin individual stage limits in addition to the preset.

## Determinism guarantees

- Non-random search ordering and result merges are deterministic for the same code, database, query, and options.
- `selfcheck` random trials are deterministic under `--seed`; save failing seeds for replay.
- JSON arrays are emitted in deterministic ranked order and carry `schema_version: 1`.
- Wall-time caps can stop at slightly different boundaries across machines. For exact cross-machine comparisons, use explicit check/candidate limits and a time cap generous enough not to fire.
- SQLite/OS cache state changes timings, not intended result ordering when all configured stages finish.

Checkpoint files include the query, database marker, and search-shaping arguments. `--resume` only reuses a checkpoint when that context is compatible.

## Benchmark protocol

For numbers intended to be compared:

1. Record CPU, Python version, WSL/Linux version, code commit, and snapshot hashes.
2. Close unrelated heavy processes and state whether the run is cold- or warm-cache.
3. Run `scripts/bench_sweep.py --repeats 5`; it reports the best repeat for stable kernel comparisons.
4. Run `scripts/bench.py --repeats 5 --strict` for median end-to-end API envelopes.
5. Run `OEIS_BENCH_CPU=0 scripts/bench_hyperfine.sh /tmp/oeis-hyperfine.json` when process startup and preset comparisons matter.
6. Use `scripts/profile_matchers.py --case ... --profile out.pstats` before optimizing.
7. Keep a before/after table and verify the full test suite; do not accept a speedup that changes uncapped results.

The maintained baseline and its environment are in `docs/benchmarks.md`.
