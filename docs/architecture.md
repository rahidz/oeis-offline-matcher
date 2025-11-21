# OEIS Offline Matcher – Architecture Sketch

This snapshot describes the current v0/v1 pipeline.

## Data Flow (build)
- `scripts/fetch_oeis_data.sh` downloads `stripped.gz` + `names.gz` to `data/raw/`.
- `oeis build-index` parses stripped lines into `SequenceRecord` objects, attaches titles from names, computes invariants (prefix5, min/max, gcd, monotone flags, sign patterns, nonzero counts, first-diff sign, growth_rate), and stores them in `data/processed/oeis.db` (SQLite).

## Query Flow (CLI/API)
1) **Parse**: `parse_query` → `SequenceQuery` (terms, min_match_length, allow_subsequence).
2) **Candidate filter**: `matcher.candidate_sequences` picks:
   - prefix index (prefix5) if subsequence search is off and length ≥ 5,
   - otherwise invariant-filtered scan via SQLite.
3) **Exact match**: `_is_prefix` + optional KMP subsequence → `Match`.
4) **Transforms**: `transform_search` enumerates chains (scale/affine/shift/diff/psum/abs/gcd_norm/decimate), applies to query, re-runs exact matcher, scores with complexity penalty, adds human/LaTeX explanations.
5) **Similarity**: `rank_candidates_for_query` fits scale/offset (MSE + correlation) on filtered candidates.
6) **Combinations (experimental)**: `get_candidate_bucket` (capped, optional fill) → `search_two_sequence_combinations` / `search_three_sequence_combinations` brute-force small integer coeffs and forward shifts, with optional per-component transforms (id/diff/partial_sum) → `CombinationMatch` with expression.
7) **Aggregate**: `analyze_sequence` bundles exact, transform, similarity, combos (+ diagnostics) as dict or `AnalysisResult`.

## Key Data Structures
- `SequenceRecord`: id, terms, length, name, metadata.
- `SequenceQuery`: terms, min_match_length, allow_subsequence.
- `Match`: id, match_type, offset, length, score, transform_desc, explanation, latex, snippet.
- `CombinationMatch`: ids, coeffs, shifts, length, score, expression.
- `AnalysisResult`: aggregates matches plus diagnostics.

## Config & Presets
- Defaults: see `config.py` (paths, max_results/terms).
- Presets: CLI `--preset fast|deep` adjusts depth, limits, coeffs, candidate caps, combo checks.

## Storage
- SQLite table `sequences(id TEXT PRIMARY KEY, length INT, terms TEXT, name TEXT, prefix5 TEXT, min_val, max_val, gcd_val, is_nondecreasing, is_nonincreasing, sign_pattern, nonzero_count, first_diff_sign, growth_rate REAL)`.
- Indexes on prefix5, length, gcd_val, sign_pattern, first_diff_sign, nonzero_count, growth_rate.

## Extensibility Notes
- Drop-in new transforms by adding to `transforms.default_transforms`.
- Wider combo search: extend `combination_search` to negative shifts or per-component transforms.
- Metrics/benchmarks: hook into `analyze_sequence` to measure latency per stage.
 - Presets can be expanded (e.g., “balanced”) or tuned per use-case.
