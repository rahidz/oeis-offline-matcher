# OEIS Offline Matcher

Offline helper inspired by OEIS Superseeker.

It downloads an OEIS snapshot once, builds a local SQLite index, then lets you paste a numeric sequence and search for:
- Exact/prefix/subsequence OEIS matches.
- Transform matches (scale/affine, shifts, diffs/partial sums, digit/mod/arithmetical-function transforms, etc.).
- Combination matches:
  - Linear combinations of 2–3 sequences with small integer (or optional rational) coefficients and shifts.
  - Pointwise operations (mul/gcd/lcm).
  - Cauchy and Dirichlet convolutions (guarded by strict caps).
  - Optional expanded “DB-wide” pair/triple fallback using a prefix index (enabled in `--preset max`).

After the initial `oeis sync` + `oeis build-index`, analysis runs fully offline.

## Status
Works end-to-end; still actively tuning scoring and performance heuristics. See `TODO.md` for the roadmap.

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .

# Download raw OEIS exports (cached in data/raw)
oeis sync
# Optional bash alternative:
#   scripts/fetch_oeis_data.sh
#   scripts/fetch_oeis_data.sh --clone-oeisdata

# Build SQLite index in data/processed/oeis.db
oeis build-index

# If you built your DB with an older version, you can add newer performance
# indexes in-place (one-time, safe to re-run):
oeis optimize-db --db data/processed/oeis.db
# If you see a CLI warning like "DB is missing recommended index(es)", run the command above.

# Full pipeline (exact + transforms + similarity + combos), “find everything”
# - Streams results as they are found
# - Includes expanded DB-wide combo fallback
# - Uses a long total runtime budget (see --total-max-time)
oeis analyze "5,17,103,1011,10042" --preset max

# Prefer a single consolidated report?
oeis analyze "5,17,103,1011,10042" --preset max --no-stream

# Hard cap the entire pipeline runtime (seconds)
oeis analyze "5,17,103,1011,10042" --preset max --total-max-time 600

# Combo-only mode (pairs/triples/pointwise/convolution), “find combinations”
# Note: `--preset max` enables streaming + expanded fallback + a long total budget (default ~1 hour).
oeis combo "5,17,103,1011,10042" --preset max --triples 10

# Hard cap the entire combo pipeline runtime (seconds)
oeis combo "5,17,103,1011,10042" --preset max --triples 10 --total-max-time 600
```

## Self-check (regressions + random sanity)

If you want a quick “did I build the DB correctly?” check:

```bash
# Runs `docs/regressions.json` (fast, deterministic)
oeis selfcheck --db data/processed/oeis.db

# Also run random combo recovery trials (deterministic given --seed)
oeis selfcheck --db data/processed/oeis.db --random-trials 20 --seed 1
```

Notes:
- Random trials need a reasonably sized DB; for very small/custom DBs, pass `--min-length` lower.
- For custom DBs that don’t include the regression A-numbers, use `--no-regressions`.

## Presets

Presets are `fast`, `deep`, `max`.

Important: presets are implemented by expanding `--preset NAME` into explicit flags inserted before your flags, so anything you pass explicitly afterwards overrides the preset. Example:

```bash
# preset max normally enables combos/triples/expanded fallback
oeis analyze "5,17,103,1011,10042" --preset max --combos 0 --triples 0 --no-combo-expanded
```

### What they mean (plain English)
- **fast**: quick skim (small search space, short timeouts).
- **deep**: broader, still “everyday” friendly.
- **max**: “find everything” mode. Long total budget (up to ~1 hour by default), large candidate pools, expanded DB-wide combo fallback, and streaming output by default.

## Combination Search

### Candidate-pool search (fast path)
`oeis combo` and `oeis analyze` primarily work by building a candidate bucket (exact-ish + similarity-ish sequences), then trying combinations within that bucket. This is the only approach that’s remotely practical for triples in general.

Note: the candidate bucket is also automatically seeded with a small set of “building block” sequences (zeros, ones, n, n+1, squares). This helps the tool discover explanations like `n^2 + n` or `n*(n+1)` even when those components don’t resemble the query’s prefix.

Also note: two-sequence combo search can reuse the *same* OEIS sequence more than once (with different shifts and/or per-component transforms). This lets it discover “self-shift” identities like:
- `Lucas(n) = Fibonacci(n-1) + Fibonacci(n+1)`

Under `--preset max`, combo/pointwise/convolution searches also enable simple per-component transforms (`id,diff,partial_sum`) and allow a small backward-shift window. This is slower, but can uncover more “explanation-style” decompositions.

For pointwise and convolution matches, the tool also avoids redundant commutative duplicates when streaming (e.g. it won’t print both `A(n)*diff(A(n))` and `diff(A(n))*A(n)` for the same underlying self-pair).

Ordering note: in streaming mode, triple search is scheduled after pair/pointwise/convolution searches to improve time-to-first-hit (triple search can be much more expensive).

Triple search note: even when you enable shifts/transforms, the triple solver starts with a fast, shift=0 + transform=id prefix-hash pass to surface “plain” decompositions early, then falls back to the slower general search for shifted/transformed triples.

### Expanded DB-wide fallback (slower, catches mismatched components)
Sometimes the components don’t resemble the target query at all. In those cases, `--expanded` (or `--preset max`) enables an expanded fallback that uses the DB-wide prefix index to search pairs/triples without needing you to know the component A-numbers.

Note: the expanded fallback builds an in-memory prefix index from your SQLite DB (typically sub-second on a full snapshot). It requires at least 5 query terms, and it is bounded by `--expanded-max-time` and the global `--total-max-time`.
In streaming mode, expanded pair fallback is deferred until after the regular candidate-bucket stages (including triples/pointwise/convolution) to improve time-to-first-hit.

Examples:

```bash
# Two/three-sequence combos
oeis combo "5,17,103,1011,10042" --triples 10

# Stream combo hits as they’re found (enabled by `--preset max`)
oeis combo "5,17,103,1011,10042" --preset max --triples 10

# Expanded fallback if regular search finds nothing
oeis combo "5,17,103,1011,10042" --triples 10 --expanded --expanded-max-time 30

# Full pipeline with expanded fallback (enabled by preset max)
oeis analyze "5,17,103,1011,10042" --preset max
```

### Reality check: exhaustive triples
Exhaustively testing “all triples of all OEIS sequences” is not feasible.

Pairs are *much* more tractable: the expanded pair fallback is close to an exhaustive scan (for shift=0, transform=id)
because the prefix index turns “find A + B = Q” into a mostly linear pass with fast lookups (still bounded by time caps).

The tool keeps triples reasonable by:
- Using candidate-bucket search first (strong pruning).
- Using strict caps (`--max-checks`, `--*-max-time`, `--total-max-time`).
- Only attempting expanded DB-wide fallback under `max` (and still time-capped).

## Useful Flags

```bash
# Show per-stage timing
oeis analyze "1,2,3,4,5" --preset deep --timings

# Cap the whole pipeline runtime
oeis analyze "1,2,3,4,5" --preset max --total-max-time 120

# Timings for combo-only runs
oeis combo "1,2,3,4,5" --preset max --timings --total-max-time 120

# Disable expanded combo fallback (faster)
oeis analyze "1,2,3,4,5" --preset max --no-combo-expanded

# Disable the very-wide candidate pool used in max
oeis analyze "1,2,3,4,5" --preset max --no-combo-unfiltered

# Stream transform hits as they are found (enabled by `--preset max`)
oeis tsearch "1,2,3,4,5" --preset max --stream

# Machine-readable output
oeis analyze "1,2,3,4,5" --preset max --json > out.json
# Schemas: docs/schemas/analyze.schema.json, docs/schemas/combo.schema.json
```

## Architecture
See `docs/architecture.md` for the current data flow, storage schema, and key structures.

## FAQ
See `docs/FAQ.md` for limits and performance tips.

## Benchmarks / Profiling
- `scripts/bench.py` times a few common cases (after building the DB).
- `scripts/bench_sweep.py --repeats 5` runs small sweeps (transform families/depth, combo bucket size/shift ranges).
- `scripts/bench_build.py --stripped data/raw/stripped.gz --names data/raw/names.gz --keywords data/raw/keywords.txt --db /tmp/oeis_bench.db` measures build time/size.
- `scripts/profile_matchers.py --profile out.pstats --sort tottime` helps identify hotspots for specific cases.
- `scripts/validate_random_combos.py --db data/processed/oeis.db --trials 20` runs random sanity checks for pair/triple combo recovery (requires a built DB).
- `scripts/validate_random_combos.py --db data/processed/oeis.db --trials 20 --pointwise-trials 20 --convolution-trials 20` also checks pointwise and convolution combos.
- `oeis selfcheck --db data/processed/oeis.db --random-trials 20` runs regressions + random combo trials in one command.
- `oeis selfcheck --db data/processed/oeis.db --pointwise-trials 20 --convolution-trials 20` adds random pointwise/convolution sanity checks.
- `docs/notebook_regressions.ipynb` runs `docs/regressions.json` as a full-pipeline regression check (requires a built DB).
- Bench numbers live in `docs/benchmarks.md`.

## Configuration
- Optional `config.toml` (see `config.example.toml`) controls default paths and limits.
- Environment overrides:
  - `OEIS_STRIPPED_PATH`, `OEIS_NAMES_PATH`, `OEIS_DB_PATH`
  - `OEIS_MAX_TERMS`, `OEIS_MAX_RESULTS`
  - `OEIS_MATCHER_CONFIG` to point at an alternate TOML file

## Attribution / License Notice
OEIS data is CC BY-SA 4.0. Include proper attribution and share-alike when redistributing data or outputs derived from OEIS content. See `LICENSE_OEIS.md`.
