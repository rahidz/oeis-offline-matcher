# OEIS Offline Matcher

Python-based offline helper inspired by OEIS Superseeker. It downloads a local snapshot of OEIS data, builds lightweight indexes, and matches user-provided integer sequences against:
- Direct OEIS entries (exact, prefix, subsequence).
- (Planned) transformations of a single sequence (e.g., scale, shift, diff, partial sums).
- (Planned) small linear combinations of a few sequences with simple transforms.

## Status
Early scaffolding. See `TODO.md` for the detailed roadmap.

## Quick Start
```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .

# Download raw OEIS exports (once, cached in data/raw)
scripts/fetch_oeis_data.sh

# Build SQLite index in data/processed/oeis.db
oeis build-index

# Match a sequence (prefix by default)
oeis match "0,1,1,2,3,5,8"

# Allow subsequence search
oeis match "2,3,5" --subsequence --limit 5

# Show first 8 terms of each hit
oeis match "0,1,1,2,3,5,8" --show-terms 8

# Transform search (scale/shift/diff/sum/abs up to depth 2 by default)
oeis tsearch "1,2,3,4,5"

# Full pipeline (exact + transforms) with JSON output
oeis analyze "1,2,3,4,5" --json
```

## Configuration
- Optional `config.toml` (see `config.example.toml`) controls default paths and limits.
- Environment overrides:
  - `OEIS_STRIPPED_PATH`, `OEIS_NAMES_PATH`, `OEIS_DB_PATH`
  - `OEIS_MAX_TERMS`, `OEIS_MAX_RESULTS`
  - `OEIS_MATCHER_CONFIG` to point at an alternate TOML file

## Design Notes
- Language: Python 3.11+
- Data lives in `data/raw` (downloaded `stripped.gz`, `names.gz`) and `data/processed` (parsed/indexed artifacts).
- Configuration: `config.toml` (optional) plus env overrides for paths/limits.
- Storage: simple SQLite with invariants (prefix5 hash, min/max, gcd, monotonic flags, sign pattern, nonzero count, first-diff sign). Easy to evolve later.

## License Notice
OEIS data is licensed under CC BY-SA 4.0. Keep attribution and share-alike when redistributing data or outputs derived from OEIS content. See <https://oeis.org/LICENSE> and `LICENSE_OEIS.md`.
