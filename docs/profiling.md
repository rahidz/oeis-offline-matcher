# Profiling / Hotspots

This project is designed to run fully offline after `oeis sync` + `oeis build-index`.

When performance regresses, it’s usually because of one of:
- subsequence scans on very short queries (less pruning),
- `--combo-unfiltered` + short queries (large candidate buckets),
- expanded DB-wide combo fallback under `--preset max` (intentionally wide search).

## Quick timings

Use `scripts/bench.py` for a quick smoke check on your machine:

```bash
python scripts/bench.py
```

## cProfile (pstats)

Run a few canned cases and write cProfile output:

```bash
python scripts/profile_matchers.py --profile out.pstats --sort tottime
```

Then inspect the profile:

```bash
python -m pstats out.pstats
```

Or (optional, external) use a GUI viewer like `snakeviz`:

```bash
snakeviz out.pstats
```

## What to look for

- If the hot path is *SQLite fetch*, consider whether you’re triggering full scans (e.g. very short queries).
- If the hot path is *combination loops*, reduce candidate caps / shift ranges, or disable expanded fallback.
- If the hot path is *transform enumeration*, reduce `--max-depth` or `--extra-transforms`.

Benchmarks and scaling notes live in `docs/benchmarks.md`.

