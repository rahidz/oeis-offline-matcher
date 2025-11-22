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
# Optional: also clone oeisdata mirror (more metadata, slower download)
scripts/fetch_oeis_data.sh --clone-oeisdata
# Python alternative (no bash dependency)
oeis sync
# Offline/sandboxed? `oeis sync --stripped /tmp/stripped.gz --names /tmp/names.gz`
# accepts local paths or file:// URIs and will simply copy the files.

# Build SQLite index in data/processed/oeis.db
oeis build-index

# Match a sequence (prefix by default)
oeis match "0,1,1,2,3,5,8"

# Allow subsequence search (auto-fallback runs if no prefix hit)
oeis match "2,3,5" --subsequence --limit 5

# Show first 8 terms of each hit
oeis match "0,1,1,2,3,5,8" --show-terms 8

# Transform search (scale/shift/diff/sum/abs up to depth 2 by default)
oeis tsearch "1,2,3,4,5"
oeis tsearch "1,2,3,4,5" --max-time 1.5   # cap transform search runtime
oeis tsearch "1,2,3,4,5" --min-score 1.5  # drop weak/degenerate transforms

# Extra transforms (diff^2, cumprod, popcount/digitsum, mod, reverse, even/odd, movsumN, binomial/euler/mobius, rle/rledec, concat, log/exp)
oeis tsearch "1,2,3,4" --extra-transforms "diff2,cumprod,reverse,binomial,mobius,movsum4,digitsum10,mod2,rle,concat,log2,exp2"

# Presets: fast, deep, or max (override many knobs)
oeis analyze "1,2,3,4,5" --preset fast
oeis analyze "1,2,3,4,5" --preset deep --json
oeis analyze "1,2,3,4,5" --preset max   # “find everything”: deeper transforms, combos+triples, wide limits, ~10 min caps
```

### What the presets mean (plain English)
- **fast** – quickest skim. Single-step transforms, small candidate/combination pools, short timeouts. Good for “is there an obvious hit?” moments.
- **deep** – broader but still everyday-friendly. Two-step transforms, wider scale/shift ranges, decimation/reverse/etc., modest combo/triple search with multi-second caps.
- **max** – exhaustive mode. Deep transforms plus combo/triple search with large candidate pools and long (~minutes) time budgets. Use when you really need to dredge everything up and don’t mind waiting.

```bash

# Two-sequence integer combinations (experimental)
oeis combo "3,5,7,9,11" --coeffs "1,2" --candidates 40 --max-shift 1 --max-shift-back 0 --max-checks 200000
oeis combo "2,3,4,5" --rational  # solve coefficients over rationals (pairs)
oeis combo "2,10,100,1004,9991" --coeffs "1,1" --combo-unfiltered  # wider candidate pool for mismatched prefixes

# Full pipeline (exact + transforms) with JSON output
oeis analyze "1,2,3,4,5" --json

# Full pipeline including combination search (experimental)
oeis analyze "3,5,7,9,11" --combos 5 --combo-coeffs "1,2" --combo-max-shift 1 --combo-max-checks 200000
oeis analyze "3,5,7,9,11" --combos 5 --combo-max-shift 1 --combo-max-shift-back 1 --timings
oeis analyze "3,5,7,9,11" --combos 5 --combo-min-score 1.0  # filter low-confidence combos
oeis analyze "1,2,3,4,5" --transform-max-time 2.0  # cap transform stage

# Three-sequence combinations (experimental, slower)
oeis analyze "2,1,0,-1,-2" --triples 3 --combo-coeffs "1,-1" --triple-max-checks 200000

# Per-component transforms in combos (diff/partial_sum)
oeis combo "1,1,1,1" --coeffs "1,0" --component-transforms "diff,id"

# Presets (fast|deep|max) include combo/time caps
oeis analyze "2,1,0,-1,-2" --preset fast --triples 0
oeis analyze "2,1,0,-1,-2" --preset deep
oeis analyze "2,10,100,1004,9991" --preset max --combo-unfiltered   # exhaustive search including mismatched prefixes

# Include similarity-ranked candidates
oeis match "1,2,3,4,5" --similar 5 --min-corr 0.9 --variance-band 20 --growth-band 3 --json

# Python library usage (see `src/oeis_matcher/api.py`)
>>> from oeis_matcher.api import analyze_sequence
>>> analyze_sequence("0,1,1,2", combos=0, similarity=3)["exact_matches"][0]["id"]
'A000045'
>>> analyze_sequence("0,1,1,2", as_dataclass=True).exact_matches[0].id
'A000045'

# Transform explanations now include human readable text
oeis tsearch "1,2,3,4,5" --json | jq '.matches[0].explanation'

# LaTeX-ish transform renderings
oeis tsearch "1,2,3,4,5" --json | jq '.matches[0].latex'

# Show terms for matches (transforms include transformed terms; combos include component/result)
oeis analyze "2,10,100,1004,9991" --combos 3 --combo-unfiltered --show-terms 10
```

## Architecture
See `docs/architecture.md` for the current data flow, storage schema, and key structures.

## FAQ
See `docs/FAQ.md` for common questions, limits, and performance tips.

## Benchmark
Run `scripts/bench.py` (after building the DB) to time common query paths on your machine. You can tweak presets/limits if it's too slow.
Run `scripts/bench_build.py --stripped data/raw/stripped.gz --names data/raw/names.gz --keywords data/raw/keywords.txt --db /tmp/oeis_bench.db` to measure build time/size.
Use `scripts/profile_matchers.py --profile out.pstats --sort tottime` to capture hotspots for a specific case (`--case "Transform naturals"`).

## Notebook quickstart (optional)
If you prefer notebooks, create `.venv`, install `jupyter`, then:
```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
pip install jupyter
jupyter notebook
```
Use the Python examples from above inside a notebook cell to explore results.

## Attribution
OEIS content © The OEIS Foundation Inc., distributed under CC BY-SA 4.0. Include proper attribution and share-alike when redistributing derived outputs.

## Mini test fixture
For quick offline checks, see `tests/data/mini_oeis` with stripped/names/keywords plus `tests/test_integration_mini_oeis.py` that exercises exact/transform/combo paths.
## Configuration
- Optional `config.toml` (see `config.example.toml`) controls default paths and limits.
- Environment overrides:
  - `OEIS_STRIPPED_PATH`, `OEIS_NAMES_PATH`, `OEIS_DB_PATH`
  - `OEIS_MAX_TERMS`, `OEIS_MAX_RESULTS`
  - `OEIS_MATCHER_CONFIG` to point at an alternate TOML file
  - Wildcards: parser allows `?/*` but caps wildcards to avoid overbroad queries.

## Design Notes
- Language: Python 3.11+
- Data lives in `data/raw` (downloaded `stripped.gz`, `names.gz`) and `data/processed` (parsed/indexed artifacts).
- Configuration: `config.toml` (optional) plus env overrides for paths/limits.
- Storage: simple SQLite with invariants (prefix5 hash, min/max, gcd, monotonic flags, sign pattern, nonzero count, first-diff sign). Easy to evolve later.

## License Notice
OEIS data is licensed under CC BY-SA 4.0. Keep attribution and share-alike when redistributing data or outputs derived from OEIS content. See <https://oeis.org/LICENSE> and `LICENSE_OEIS.md`.
