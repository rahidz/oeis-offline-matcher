# OEIS Offline Matcher

Offline helper inspired by OEIS Superseeker.

It downloads an OEIS snapshot once, builds a local SQLite index, then lets you paste a numeric sequence and search for:
- Exact/prefix/subsequence OEIS matches.
- Transform matches (scale/affine, shifts, diffs/partial sums, digit/mod/arithmetical-function transforms, etc.).
- Combination matches:
  - Linear combinations of 2–3 sequences with small integer (or optional rational) coefficients and shifts.
  - Pointwise operations (mul/gcd/lcm).
  - Cauchy and Dirichlet convolutions (guarded by strict caps).
  - Optional expanded “DB-wide” pair/triple fallback using a prefix index (enabled in `--max`).

After the initial `oeis sync` + `oeis build-index`, analysis runs fully offline.

## Status
Core pipeline is implemented end-to-end. Current work is the v1.0 roadmap: broader explanation coverage, better ranking diversity/depth, startup and data-freshness UX, and stronger regression/performance gates. See `TODO.md`.

## Quick Start

```bash
# One-liner bootstrap helper (creates .venv, installs editable package, opens a venv shell)
scripts/oeis-start

# Or run a command directly inside the prepared env:
scripts/oeis-start -- oeis status

# Try today's date in several date-shaped sequence forms with exact/prefix/subsequence matching
scripts/oeis-date
# Or pin a specific date / widen the exact-match result cap:
scripts/oeis-date 2026-03-14 --limit 100

# Manual setup path:
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

# Optional: fetch canonical b-files for specific sequences
oeis bfetch "A000045,A000217"

# Build/search a b-file value index (exact integer lookup)
oeis bindex --files-root data/raw/bfiles --db data/processed/bfiles.db
oeis bsearch 514229 --db data/processed/bfiles.db
# Note: `oeisdata/files` entries are Git LFS pointers unless LFS content is fetched.
# `oeis bfetch` downloads real b-file text directly from OEIS.

# Health + freshness report (read-only):
oeis status

# Power-user refresh flow: if stale, refresh data + rebuild index non-interactively
oeis status --refresh-if-stale

# If you built your DB with an older version, you can add newer performance
# indexes in-place (one-time, safe to re-run):
oeis optimize-db --db data/processed/oeis.db
# If you see a CLI warning like "DB is missing recommended index(es)", run the command above.

# If you want expanded (DB-wide) pointwise multiplication to support
# "start at index k" (e.g. A(n+2)*B(n+5)), older DBs also need shifted prefix
# columns (one-time, safe to re-run):
oeis optimize-db --db data/processed/oeis.db --add-prefix-shifts --max-prefix-shift 5

# Full pipeline (exact + transforms + similarity + combos), exhaustive-ceiling mode
# - Streams results as they are found
# - Includes expanded DB-wide combo fallback
# - Uses a long total runtime budget (adjust with --time-cap)
oeis analyze "5,17,103,1011,10042" --max

# OEIS-style keyword tag lookup (exact tag match):
oeis match "keyword:more"

# Fielded lookup (AND semantics across filters):
oeis match "name:fibonacci keyword:nonn sign:nonneg has-formula:true"

# Positional/value constraints (`term@k:v` uses 0-based index):
oeis match "contains:8 excludes:0 term@0:1"

# Hard cap the entire pipeline runtime (seconds)
oeis analyze "5,17,103,1011,10042" --max --time-cap 600

# Combo-only mode (pairs/triples/pointwise/convolution), exhaustive-ceiling mode
# Note: `--max` enables streaming + expanded fallback + a long total budget (default ~1 hour, user-overridable).
oeis combo "5,17,103,1011,10042" --max

# Hard cap the entire combo pipeline runtime (seconds)
oeis combo "5,17,103,1011,10042" --max --time-cap 600
```

Fielded `oeis match` filters (combined with AND):
- `id:A000045,A000204`
- `name:fibonacci`
- `formula:"2*n"`
- `keyword:more` (or multiple: `keyword:nonn,more`)
- `sign:nonneg|nonpos|alternating|mixed|empty`
- `monotonic:nondecreasing|nonincreasing|either`
- `has-formula:true|false`
- `contains:1,2,3`
- `excludes:0,-1`
- `term@k:v` (0-based index)

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
- `oeis status --refresh-if-stale` is best-effort: if offline/rate-limited, it reports the failure and keeps current local files untouched.

## Presets

Presets are `fast`, `deep`, `max`.

Search commands expose a lean preset-first interface:
- `--fast`
- `--deep`
- `--max`
- `--time-cap`

```bash
# Deep preset (balanced) with a 2-minute cap
oeis analyze "5,17,103,1011,10042" --deep --time-cap 120
```

### What they mean (plain English)
- **fast**: exact-first quick check with a small extra search budget; intended to stay short (v1.0 target is usually around 10 seconds or less).
- **deep**: broader transform/combo search for “give it more time” runs (v1.0 target is typically around 1-2 minutes).
- **max**: exhaustive ceiling mode (no `ultra` tier), with the widest search families, large candidate pools, expanded DB-wide combo fallback, and streaming output by default.

`--time-cap` is the top-level wall-time cap for `tsearch` and for the full `combo`/`analyze` pipelines.

## Combination Search

### Candidate-pool search (fast path)
`oeis combo` and `oeis analyze` primarily work by building a candidate bucket (exact-ish + similarity-ish sequences), then trying combinations within that bucket. This is the only approach that’s remotely practical for triples in general.

Note: the candidate bucket is also automatically seeded with a small set of “building block” sequences (zeros, ones, n, n+1, squares). This helps the tool discover explanations like `n^2 + n` or `n*(n+1)` even when those components don’t resemble the query’s prefix.

Also note: two-sequence combo search can reuse the *same* OEIS sequence more than once (with different shifts and/or per-component transforms). This lets it discover “self-shift” identities like:
- `Lucas(n) = Fibonacci(n-1) + Fibonacci(n+1)`

Under `--max`, combo/pointwise/convolution searches also enable simple per-component transforms (`id,diff,partial_sum`) and allow a small backward-shift window. This is slower, but can uncover more “explanation-style” decompositions.

`--max` also enables an optional SymPy-backed discovery provider for combo candidate buckets. It tries short recurrence/closed-form guesses from the query, probes discovered sequences against the local DB, and injects matched ids with provenance into the bucket.

For pointwise and convolution matches, the tool also avoids redundant commutative duplicates when streaming (e.g. it won’t print both `A(n)*diff(A(n))` and `diff(A(n))*A(n)` for the same underlying self-pair).

Ordering note: in streaming mode, triple search is scheduled after pair/pointwise/convolution searches to improve time-to-first-hit (triple search can be much more expensive).

Triple search note: even when you enable shifts/transforms, the triple solver starts with a fast, shift=0 + transform=id prefix-hash pass to surface “plain” decompositions early, then falls back to the slower general search for shifted/transformed triples.

### Expanded DB-wide fallback (slower, catches mismatched components)
Sometimes the components don’t resemble the target query at all. In those cases, `--max` enables an expanded fallback that uses the DB-wide prefix index to search pairs/triples without needing you to know the component A-numbers.

Note: the expanded fallback builds an in-memory prefix index from your SQLite DB (typically sub-second on a full snapshot). It requires at least 5 query terms, and it is bounded by internal stage caps plus your global `--time-cap`.
In streaming mode, expanded pair fallback is deferred until after the regular candidate-bucket stages (including triples/pointwise/convolution) to improve time-to-first-hit.

Shift note: expanded pair search supports small forward shifts (e.g. `A(n+2) + B(n+5)`) when your DB includes shifted prefix columns (`prefix5_1..prefix5_5`). For older DBs, run `oeis optimize-db --add-prefix-shifts` once.

Examples:

```bash
# Stream combo hits as they’re found (enabled by `--max`)
oeis combo "5,17,103,1011,10042" --max --time-cap 120

# Full pipeline with expanded fallback (enabled by preset max)
oeis analyze "5,17,103,1011,10042" --max
```

### Reality check: exhaustive triples
Exhaustively testing “all triples of all OEIS sequences” is not feasible.

Pairs are *much* more tractable: the expanded pair fallback is close to an exhaustive scan (for shift=0, transform=id)
because the prefix index turns “find A + B = Q” into a mostly linear pass with fast lookups (still bounded by time caps).

The tool keeps triples reasonable by:
- Using candidate-bucket search first (strong pruning).
- Using strict internal stage caps plus `--time-cap`.
- Only attempting expanded DB-wide fallback under `max` (and still time-capped).

## Useful Flags

```bash
# Cap the whole pipeline runtime
oeis analyze "1,2,3,4,5" --max --time-cap 120
oeis combo "1,2,3,4,5" --max --time-cap 120
oeis tsearch "1,2,3,4,5" --deep --time-cap 30

# Machine-readable output
oeis analyze "1,2,3,4,5" --max --json > out.json
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
  - `OEIS_FRESHNESS_MAX_AGE_DAYS`, `OEIS_FRESHNESS_METADATA_PATH`, `OEIS_WARN_ON_STALE_DATA`
  - `OEIS_STARTUP_SHOW_STATUS`, `OEIS_STARTUP_REFRESH_IF_STALE`
  - `OEIS_MATCHER_CONFIG` to point at an alternate TOML file

## Attribution / License Notice
OEIS data is CC BY-SA 4.0. Include proper attribution and share-alike when redistributing data or outputs derived from OEIS content. See `LICENSE_OEIS.md`.
