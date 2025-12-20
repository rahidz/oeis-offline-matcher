# TODO: OEIS Offline Matcher / “Mini-Superseeker”

High-level goal:  
Build a local tool that

1. Maintains an offline OEIS snapshot.
2. Matches user-provided integer sequences to:
   - direct OEIS entries (exact/prefix/subsequence),
   - simple transformations of OEIS entries,
   - small linear combinations of a few OEIS entries plus transforms.

---

## Phase 0 – Project framing & scope (CLI-first)

- [x] CLI + library only; GUI/notebook out of scope for now.
- [x] v0: offline OEIS + exact/prefix/subsequence matching.
- [x] v1: single-sequence transform search (Superseeker-lite).
- [x] v2: multi-sequence linear combination search (2–3 sequences, small integer/rational coeffs, shifts).
- [x] Config via TOML + env overrides; defaults tuned for offline use.

---

## Phase 1 – Data acquisition & indexing (accuracy-leaning)

### 1.1 Download + licensing
- [x] Fetch stripped/names (plus optional oeisdata clone); document CC BY-SA duties.

### 1.2 Parsing
- [x] Parse stripped + names.
- [x] Parse keywords (from oeisdata or keywords file).
- [x] Parse offsets.
- [x] Parse FORMULA text (when provided) for ranking/metadata.

### 1.3 Storage/index
- [x] SQLite primary store with invariants/prefix index.
- [x] Add extended invariants: variance and diff variance for tighter filtering (banded).
- [x] Add composite indexes + `oeis optimize-db` for fast invariant scans (avoid ORDER BY temp B-tree on broad filters).
- (Future idea) Alternative backend (mmap/custom) if perf becomes limiting.

---

## Phase 2 – Exact & similarity matching

### 2.1 Query handling

- [x] Implement `SequenceQuery` structure:
  - [x] `terms: int[]`,
  - [x] `min_match_length`,
  - [x] optional flags: exact prefix only, allow subsequence, allow scaling, etc.
- [x] Parser enhancements:
  - [x] Accept comma- or space- separated integers.
  - [x] Handle `?` or `*` placeholders with strict controls (avoid overmatching).
  - [x] Normalize whitespace and plus/minus signs.

### 2.2 Exact prefix / subsequence matching

- [x] Implement naive matcher (baseline, correct but not optimized):
  - [x] For each OEIS sequence:
    - [x] Check if query is prefix.
    - [x] Check if query appears as contiguous subsequence.
- [x] Optimized matcher polish:
  - [x] Use hash of first k terms as a key to find candidate sequences quickly (prefix5 index).
  - [x] Optionally use rolling hash/KMP to scan subsequences (implemented KMP).
  - [x] Early exit on mismatch to reduce comparisons (prefix loop).
- [x] Expose API:
  - [x] `match_exact_prefix(query) -> list[Match]`.
  - [x] `match_subsequence(query) -> list[Match]`.
  - Note: unified `match_exact` covers both via flag; wrappers still to add if desired.
- [x] Define `Match` structure:
  - [x] A-number,
  - [x] match type (prefix/subsequence),
  - [x] offset in OEIS sequence,
  - [x] matched length,
  - [x] optional snippet.

### 2.3 CLI and output formatting

- [x] CLI command `oeis match`:
  - [x] Input: sequence via CLI arg or stdin.
  - [x] Options:
    - [x] `--subsequence`
    - [x] `--limit N`
    - [x] `--json`
    - [x] `--show-terms`
  - [x] Output:
    - [x] Ranked list of A-numbers with offset, name, snippet (if requested).
- [x] JSON output schema:
  - [x] `query` terms field.
  - [x] `matches: [ { id, offset, length, name, match_type, terms? } ]`.

---

## Phase 3 – Transform engine (accuracy first)

### 3.1 Transform vocabulary
- [x] Current set: scale/affine, shift, diff/diff^2, partial_sum, abs, gcd_norm, decimate, reverse, even/odd, movsum(2+N), cumprod, popcount, digit sum, binomial (opt-in), Euler (opt-in), Möbius (opt-in).
- [x] Add vetted accuracy-focused transforms: movsum(k>3), sign/digit-aware variants, stricter penalties (further tuning tracked in 3.5).
  - [x] Arithmetic-function transforms on terms: omega/Omega (prime factor counts), tau/sigma (divisor counts/sums), phi, v2.
  - [x] Index-based transforms: values at square indices, prime indices, powers of 2, and factorial indices.

### 3.1b Transform backlog (enable all in `--preset max`)
- [x] Promote **binomial** to on-by-default in `max` (keep opt-in elsewhere).
- [x] Promote **Euler** to on-by-default in `max` (guard complexity).
- [x] Include **affine(k,b)** with nonzero `b` in presets (currently only if user passes `--beta-values`).
- [x] Add **backward/negative shifts** in chains (not just drop-first-k).
- [x] Add **base-k digit sums** (k ≠ 10) and expose base selection.
- [x] Add **modulus/bitwise** style transforms (e.g., seq mod m, xor with index) with strong penalties.
- [x] Add **run-length encoding** (lengths) and **decode** (len,val pairs).
- [x] Add **concatenate digits/blocks** transforms (concat index with a_n; base-param).
- [x] Add **log/exp-like smoothing** (log bases 2/e/10 opt-in; exp opt-in, capped).
- [x] Add **Möbius** transform (opt-in, enabled in `max`; Dirichlet variants still stretch).
- [x] Improve **moving sums >3** support and scoring (currently only movsum2/3 presets).
- [x] Update `max` preset config to enable the above once implemented; keep `fast`/`deep` conservative.

### 3.2 Implement transform engine

- [x] Implement core transform functions (scale, shift+, diff, partial_sum, abs).
- [x] Implement transform composition (chains with depth limit).
- [x] Implement transform enumerator (all chains up to depth N; dedup basic).

### 3.3 Transform search quality
- [x] Generate/score transform chains with complexity penalties; dedupe identical transformed outputs; time caps.
- [x] Tighten noise filters: reject constant/low-diversity outputs unless query is low-diversity; variance-based drop for collapsed outputs.
- [x] Add noisy-chain guards (RLE/popcount/mod/etc.) to drop trivial arith/progression outputs on random data.
- [x] Add coverage/diversity/variance bonuses; presets set `transform_min_score` / `transform_max_complexity`.
- [x] Add keyword/popularity bonuses to scoring.

### 3.4 CLI for transform search

- [x] CLI command `oeis tsearch`:
  - [x] Options: depth, subsequence, limit, scale/shift lists, disable diff/psum/abs, json, show-terms.
  - [x] Output: includes transform chain description.

### 3.5 Scoring
- [x] Heuristic score length/(1+complexity).
- [x] Add variance bonus and invariants rarity bonus to scoring.
- [x] Further re-tune weights; penalize degenerate chains more aggressively.

### 8.1 Unit tests

- [x] Transform tests:
  - [x] Verify output of `Diff`, `Sum`, `Shift`, etc. on known sequences.
- [x] Matcher edge-case tests for negatives/short queries.

---

## Phase 4 – Candidate ranking & similarity filtering

### 4.1 Numeric signatures / features

- [x] Define simple numeric features per sequence:
  - [x] Length of usable prefix.
  - [x] `gcd`, `min`, `max`.
  - [x] First-diff sign pattern.
  - [x] Sign pattern of terms.
  - [x] Nonzero count.
  - [x] Approximate growth rate.
- [x] Precompute and store these features during index build (in SQLite).

### 4.2 Similarity scoring

- [x] Implement a similarity metric between two finite sequences:
  - [x] normalized mean squared error after scaling and offset.
  - [x] correlation coefficient of `(q_n)` vs `(S_n)`.
- [x] Implement function `rank_candidates_for_query(q)`:
  - [x] Filter sequences quickly by invariants.
  - [x] Compute similarity scores against the filtered subset.
  - [x] Return top-K candidate sequences with highest similarity.
- [x] Add thresholds (`--min-corr`, `--max-mse`) to reduce noisy suggestions.

### 4.3 Integration with previous phases

- [x] After running:
  - [x] direct matches,
  - [x] transform-based matches,
  - [x] add similarity-ranked candidates:
    - [x] Ensure union of candidates ≤ some K (e.g., 100–200).
- [x] Expose API to get “candidate bucket” for multi-sequence search:
  - [x] `get_candidate_bucket(q, K) -> list[Candidate]`.
  - [x] Option to skip prefix index and relax nonzero filter for combos (handles mismatched prefixes; `--combo-unfiltered`).
- [x] Use additional invariants (variance, growth buckets) to trim candidate sets further for transforms/combos.

---

## Phase 5 – Multi-sequence linear combination search (2b, plural)

### 5.1 Define search class

  - [x] Decide on the class of expressions to search:
    - [x] Number of component sequences `m`:
      - [x] v2: `m ≤ 2` (implemented, forward + optional backward shifts),
      - [x] optional extension: `m ≤ 3` (implemented, guarded/capped).
    - [x] Coefficient constraints:
      - [x] small integers, e.g. |c_i| ≤ 5 or 10 (configurable list).
    - [x] Shift constraints:
      - [x] index shifts `s_i` in range, e.g., `-k ≤ s_i ≤ max_shift` (backward shifts supported).
    - [x] Optional per-component transforms:
      - [x] simple things like `Diff`/`PartialSum` (component-transforms).

### 5.2 Two-sequence combinations (accuracy focus)

- [x] API design:
  - [x] `search_two_sequence_combinations(q, candidates, options) -> list[CombinationMatch]` (brute-force small integer coefficients).
- [x] (Future) Use linear algebra over ℚ for wider coefficient ranges. -> added rational solver for pair search.
- [x] For each unordered pair of candidates `(S_i, S_j)` in the candidate bucket:
  - [x] Precompute truncated sequences with possible shifts.
  - [x] For each allowed pair of shifts `(s_i, s_j)`:
    - [x] Build vectors without per-component transforms (scope MVP).
    - [x] Optionally add per-component transforms later.
    - [x] Use linear algebra over ℚ for wider coefficient ranges (pairs + triples supported).
    - [x] Verify equality on all k terms.
    - [x] Record `Combination` with A-numbers, coefficients, shifts, expression string.

### 5.3 Optional: Three-sequence combinations

- [x] Extend above method:
  - [x] Use 3 columns in matrix, solve for `(a, b, c)`.
  - [x] Only run if:
    - [x] candidate bucket size is small, and/or
    - [x] user explicitly enables 3-term combinations.
- [x] Guard with strong limits on:
  - [x] number of pairs/triples,
  - [x] coefficient ranges,
  - [x] transform depth.  (capped shifts/coeffs, bucket trimming, time/check limits)

### 5.4 Complexity safeguards

- [x] Hard-limit candidate bucket size (e.g. K ≤ 100).
- [x] Hard-limit total combinations checked per query (max_checks guard).
- [x] Add time caps to combo/triple search; “max” preset sets wide caps (~10m) for exhaustive runs.
- [x] Add expanded (DB-wide prefix index) pair/triple fallback to catch decompositions where components don’t resemble the query.
- [x] Add coeff-norm caps/condition checks for rational solutions to cut false positives.
- [x] Provide configuration:
  - [x] `max_combinations`,
  - [x] `max_time_per_query` (if implementing time budgets),
  - [x] `max_coeff_abs` (via CLI coeff list),
  - [x] `max_shift_abs` (via CLI `--max-shift`).

### 5.6 Pointwise and convolution combinations

- [x] Pointwise two-sequence operations:
  - [x] Products `a(n) = A(n)*B(n)`.
  - [x] `gcd(A(n), B(n))`, `lcm(A(n), B(n))`.
  - [x] Exposed via `oeis combo --pointwise-ops` and `oeis analyze --pointwise-ops/--pointwise-limit` with strong `max_checks`/time caps.
- [x] Convolution combinations:
  - [x] Cauchy convolution `c_n = Σ_{k<=n} A_k B_{n-k}`.
  - [x] Dirichlet convolution `c(n) = Σ_{d|n} A(d) B(n/d)` (1-based).
  - [x] Guarded by `max_length`, `max_candidates`, `max_checks`, and `max_time_s`; exposed via `--convolution-ops/--convolution-limit`.
- [x] Avoid redundant commutative self-pair duplicates when streaming (e.g. `A*diff(A)` vs `diff(A)*A`), and include component transforms in convolution expressions.

### 5.5 Scoring & ranking

- [x] Define complexity measure for a combination:
  - [x] number of component sequences (fixed 2),
  - [x] sum of |coefficients|,
  - [x] sum of |shifts|,
  - [x] per-component transform weights (single-step; chaining is a future extension).
- [x] Sort results by:
  - [x] simplest explanation first (lower complexity),
  - [x] then by length of match,
  - [x] then by sequence popularity/importance (via keyword-weight bonus in scoring).
- [x] Deduplicate combo/triple outputs per sequence+transform family to keep only the top explanation.

---

## Phase 6 – User-facing CLI / API design

### 6.1 Unified CLI interface

- [x] Single entrypoint `oeis analyze`:
  - [x] Runs exact + transform pipeline.
  - [x] Add combos when available.
  - [x] Common options: add max-candidates/combos.
- [x] `--preset` works across subcommands (match/tsearch/combo/analyze) and acts like defaults (explicit flags override preset).
- [x] Streaming + time budgeting for long runs:
  - [x] `oeis analyze --stream` prints matches as stages complete (and streams transform/combo hits as found).
  - [x] `oeis analyze --total-max-time SECONDS` caps the entire pipeline.
  - [x] `oeis combo --total-max-time SECONDS` caps the entire combo pipeline (candidate bucket + pair/pointwise/convolution + triples).
  - [x] `oeis tsearch --stream` streams transform hits as they are found (enabled in `--preset max`).
  - [x] Two-sequence combos can reuse the same OEIS id with different shifts (enables self-shift identities like Lucas from Fibonacci).
  - [x] Defer expanded DB-wide pair fallback until after other combo stages in streaming mode (better time-to-first-hit for triples/pointwise/convolution).

### 6.2 Library API

- [x] Define high-level functions:
  - [x] `analyze_sequence(query_terms, config)` (dict payload).
  - [x] `match_exact` wrapper.
  - [x] `search_transforms`.
  - [x] `search_combinations`.
- [x] Provide data structures:
  - [x] `AnalysisResult` dataclass with diagnostics (dict-compatible).

### 6.3 Output formatting + explanation

- [x] Human-readable explanation strings.
- [x] Optional LaTeX-friendly output for use in papers/notes.

Progress: Combination matches now emit `a(n) = c1*Axxxx(n+s1)+c2*Ayyyy(n+s2)` with LaTeX; transform matches include human + LaTeX-ish chain descriptions and symbolic renderings.

---

## Phase 7 – Performance, profiling, and optimization (keep fast + accurate)

- [x] Benchmark core operations (run + record, not just harnesses):
  - [x] Index build time and memory footprint on full snapshot; stash numbers in `docs/benchmarks.md`.
  - [x] Exact matcher latency vs OEIS size (prefix vs subsequence) with caps documented.
  - [x] Transform search cost per transform family/depth (see `scripts/bench_sweep.py` + `docs/benchmarks.md`).
  - [x] Combination search cost vs candidate bucket size/shift ranges (see `scripts/bench_sweep.py` + `docs/benchmarks.md`).
  - [x] Add quick timing harness (`scripts/bench.py`) to measure common cases.
  - [x] Add profiling helper (`scripts/profile_matchers.py`) for stage timing.
  - [x] Add build benchmark script (`scripts/bench_build.py`).
  - [x] Perf smoke test for analyze path (mini fixture, <200ms).
- [x] Expose per-stage timings in CLI (`oeis analyze --timings`) and API (`collect_timings=True`).
- [x] Add time caps to transform search to bound worst-case runs; dedupe repeated transformed queries.
- [x] Profile hotspots (regular runs with current snapshot; store flamegraphs/notebook):
  - [x] Identify slow parts (e.g. inner comparison loops, transform application) with `scripts/profile_matchers.py --profile ...`.
- [x] Optimize:
  - [x] Reduce Python-level hot loops where possible (e.g., faster binomial/euler transforms; reuse depth-2 transform intermediates; avoid duplicate stride scans in expanded combo fallback).
  - [x] Speed up short (4-term) prefix matching by leveraging `prefix5` via partial prefix queries (avoids full invariant scans for common transform outputs like shifts/diffs).
  - [x] Avoid allocating full convolution vectors when verifying convolution combos (early-exit matching).
  - (Future idea) Consider compiled extensions (C/Rust) for tight loops.
  - [x] Cache intermediate results (e.g., transformed sequences).
- [x] Add configuration presets:
  - [x] “Fast” preset (small transform set, few candidates).
  - [x] “Deep” preset (more transforms, combos, but bounded).
  - [x] “Max” preset (exhaustive search: deeper transforms, combos/triples, generous limits/time caps).

---

## Phase 8 – Testing & validation

### 8.1 Unit tests

- [x] Parser tests:
  - [x] `parse_stripped` on sample lines.
  - [x] `parse_names` on sample lines.
- [x] Transform tests:
  - [x] Verify output of `Diff`, `Sum`, `Shift`, etc. on known sequences.
- [x] Matcher tests:
  - [x] Exact prefix/subsequence cases.
  - [x] Edge cases: too short, mismatched lengths, negative numbers.
- [x] Combination tests:
  - [x] Real OEIS-derived pairs to validate expressions beyond synthetic fixtures.

### 8.2 Integration tests

- [x] Use known OEIS sequences as fixtures:
  - [x] Feed them to the tool and ensure they map back to their A-numbers.
- [x] Test transform matches:
  - [x] Use pairs like `(Fibonacci, first differences)`, `(square numbers, second differences constant)`, etc.
- [x] Test combination matches:
  - [x] Construct synthetic sequences as `2*A + B` and verify tool finds that relationship.
  - [x] Add real OEIS-derived combo case (Lucas from Fibonacci shifts).
- [x] Add notebook-driven regression set for whole pipeline.

### 8.3 Regression tests

- [x] Collect interesting real-world sequences and their OEIS IDs.
- [x] Run tool periodically and ensure output remains stable or improves.
- [x] Detect performance regressions (benchmark snapshots) — mini perf smoke test.
- [x] Add `oeis selfcheck` command for regressions + random combo sanity.
- [x] Extend random sanity checks to include pointwise (`mul`) and convolution (Cauchy/Dirichlet) combos.

---

## Phase 9 – Documentation & examples

- [x] Write top-level `README.md`:
  - [x] Project description and goals.
  - [x] Installation instructions.
  - [x] How to fetch and index OEIS data.
  - [x] Basic usage examples.
- [x] Write `docs/architecture.md`:
  - [x] Data flow diagram (query → transforms → matchers → combos) — textual for now.
  - [x] Description of internal data structures and storage schema.
- [x] Provide example notebooks (if using Python):
  - [x] “Exploring a sequence” (docs/notebook_template.ipynb stub).
  - [x] “Using combination search to explain a sequence” (docs/notebook_combo.ipynb).
- [x] Add FAQ:
  - [x] Limitations (what the tool can’t realistically find).
  - [x] Performance tips.
  - [x] Licensing clarification.

---

## Phase 10 – Stretch goals / research directions

- [x] Explore additional transform families (baseline implemented; future: richer/parameterized variants):
  - [x] Binomial/Euler transforms.
  - [x] Möbius transform and Dirichlet convolutions.
  - [x] Digit-based transforms (binary, decimal).
- (Future idea) Integrate with external CAS tools:
  - Optional hooks to Maple/Mathematica/Pari for advanced transforms/recurrence guessing.
- (Future idea) Experiment with learning-based candidate selection:
  - Train a model to suggest promising OEIS candidates for combos.
- (Future idea) Add small web UI:
  - Paste sequence → interactive explanation tree.
- [x] Export found relations in machine-readable format:
  - [x] Structured JSON output for `oeis analyze --json` / `oeis combo --json`, with schemas in `docs/schemas/`.

---

## Milestones

- [x] **v0.1** – Offline OEIS index + exact/prefix/subsequence matcher (Phase 1–2).
- [x] **v0.2** – Single-sequence transform engine and search (Phase 3).
- [x] **v0.3** – Candidate ranking + 2-sequence linear combo search (Phase 4–5).
- [x] **v0.4** – CLI polish, config presets, docs (Phase 6–7–9).
- [x] **v0.5** – 3-sequence combos + expanded fallback, more transforms, and regression notebook (Phase 8–9).
- **v0.6+** – Research directions / stretch goals (Phase 10). (Future ideas; not part of the v0.x core milestones.)
