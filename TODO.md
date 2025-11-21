# TODO: OEIS Offline Matcher / “Mini-Superseeker”

High-level goal:  
Build a local tool that

1. Maintains an offline OEIS snapshot.
2. Matches user-provided integer sequences to:
   - direct OEIS entries (exact/prefix/subsequence),
   - simple transformations of OEIS entries,
   - small linear combinations of a few OEIS entries plus transforms.

---

## Phase 0 – Project framing & architecture

- [x] Define scope for **v0**, **v1**, **v2** (keep as written; use to gate releases):
  - [x] v0: offline OEIS + exact/prefix/subsequence matching.
  - [x] v1: single-sequence transform search (Superseeker-lite).
  - [x] v2: multi-sequence linear combination search (2–3 sequences, small coefficients, small shifts).
- [x] Pick primary implementation language (e.g. Python, Rust, C++).
- [x] Decide packaging:
  - [x] Library + CLI (`oeis` entrypoint).
  - [ ] Optional notebook/GUI wrapper (backlog).
- [x] Define configuration strategy:
  - [x] Config file (`config.toml`) for paths/limits (config module in place).
  - [x] Environment-variable overrides for power users.

---

## Phase 1 – OEIS data acquisition & storage

### 1.1 Download + licensing

- [x] Read OEIS usage and license (CC BY-SA 4.0) and note obligations.
- [x] Implement script `scripts/fetch_oeis_data.sh`:
  - [x] Download `https://oeis.org/stripped.gz`.
  - [x] Download `https://oeis.org/names.gz`.
  - [x] Optionally clone `https://github.com/oeis/oeisdata` for full metadata (flag `--clone-oeisdata`).
- [x] Add README note about:
  - [x] How to fetch data.
  - [x] License and attribution requirements.

### 1.2 Parsing stripped/names

- [x] Implement `oeis_data/parse_stripped`:
  - [x] Parse A-number (e.g. `A000045`) and sequence terms.
  - [x] Handle missing or truncated terms gracefully.
  - [x] Decide max number of terms to store per sequence (e.g. 64 or 128).
- [x] Implement `oeis_data/parse_names`:
  - [x] Map A-number → title/name.
  - [ ] Optionally parse keywords (if available separately) — **pending, requires extra source**.

### 1.3 Storage format & indexing

- [x] Define internal data model:
  - [x] `SequenceRecord` with:
    - [x] `id: string` (A-number),
    - [x] `terms: int[]` (first N terms),
    - [x] `length: int` (terms actually present),
    - [x] `name: string`,
    - [x] `metadata` (optional).
- [x] Choose storage backend:
  - [ ] Option A: Memory-mapped binary file (e.g. custom format).
  - [x] Option B: SQLite DB with table `sequences(id, terms_blob, length, name, ...)`.
  - [ ] Option C: Simple binary file + index file (offsets per A-number).
- [x] Implement index structures:
  - [x] Map `id` → `SequenceRecord` (in-memory or DB index).
  - [x] Map `first_k_terms` → list of candidates (hash index via prefix5 text column).
  - [x] Precomputed simple invariants for filtering:
    - [x] gcd of terms,
    - [x] min, max,
    - [x] monotonic flags (nondecreasing/nonincreasing),
    - [x] sign pattern (nonnegative, alternating, mixed, empty).

- [x] Implement `oeis_data/build_index` command:
  - [x] Reads raw files.
  - [x] Builds DB/index (SQLite).
  - [x] Writes summary (insert count printed).

---

## Phase 2 – Core exact matcher (2a)

### 2.1 Query handling

- [x] Implement `SequenceQuery` structure:
  - [x] `terms: int[]`,
  - [x] `min_match_length`,
  - [x] optional flags: exact prefix only, allow subsequence, allow scaling, etc.
- [ ] Implement parser for simple text input:
  - [x] Accept comma- or space- separated integers.
  - [ ] Handle `?` or `*` placeholders (optional feature) — **backlog**.
  - [x] Normalize whitespace and plus/minus signs.

### 2.2 Exact prefix / subsequence matching

- [x] Implement naive matcher (baseline, correct but not optimized):
  - [x] For each OEIS sequence:
    - [x] Check if query is prefix.
    - [x] Check if query appears as contiguous subsequence.
- [ ] Implement optimized matcher:
  - [x] Use hash of first k terms as a key to find candidate sequences quickly (prefix5 index).
  - [x] Optionally use rolling hash/KMP to scan subsequences (implemented KMP).
  - [x] Early exit on mismatch to reduce comparisons (prefix loop).
- [ ] Expose API:
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

- [x] CLI command `oeis-match`:
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

## Phase 3 – Single-sequence transform engine (2b, singular)

### 3.1 Transform DSL design

- [x] Define a small transform vocabulary applied to the **query** (initial set shipped):
  - [x] Affine term transforms: `T(a_n) = α a_n + β` for small integer `α, β` (β optional via CLI flag).
  - [x] Index shifts: forward drop by k.
  - [x] First differences.
  - [x] Partial sums.
  - [x] Negation via scale(-1).
  - [x] Absolute value.
  - [x] Decimation (opt-in).
  - [x] GCD normalization (opt-in).
- [x] Represent transforms as composable operations (chains list).

### 3.2 Implement transform engine

- [x] Implement core transform functions (scale, shift+, diff, partial_sum, abs).
- [x] Implement transform composition (chains with depth limit).
- [x] Implement transform enumerator (all chains up to depth N; dedup basic).

### 3.3 Transform-based search

- [x] For a given input sequence `q`:
  - [x] Generate all transformed queries `T_i(q)` for allowed transforms `T_i`.
  - [x] Discard transforms that are too short.
- [x] For each `T_i(q)`: run matcher, collect matches with transform description.
- [x] Implement simple sorting: chain length, match type, match length (complexity penalty).
- [ ] Add penalties for exotic ops and scoring beyond simple sort.

### 3.4 CLI for transform search

- [x] CLI command `oeis tsearch`:
  - [x] Options: depth, subsequence, limit, scale/shift lists, disable diff/psum/abs, json, show-terms.
  - [x] Output: includes transform chain description.

### 3.5 Scoring

- [x] Basic heuristic score for transform matches (length / (1+complexity)).
- [ ] Tune complexity weights; consider popularity/length bonuses.

### 8.1 Unit tests

- [x] Transform tests:
  - [x] Verify output of `Diff`, `Sum`, `Shift`, etc. on known sequences.
- [x] Matcher edge-case tests for negatives/short queries.

---

## Phase 4 – Candidate ranking & similarity filtering (for combos)

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

### 4.3 Integration with previous phases

- [x] After running:
  - [x] direct matches,
  - [x] transform-based matches,
  - [x] add similarity-ranked candidates:
    - [x] Ensure union of candidates ≤ some K (e.g., 100–200).
- [ ] Expose API to get “candidate bucket” for multi-sequence search:
  - [x] `get_candidate_bucket(q, K) -> list[Candidate]`.
  - [x] Option to skip prefix index and relax nonzero filter for combos (handles mismatched prefixes; `--combo-unfiltered`).

---

## Phase 5 – Multi-sequence linear combination search (2b, plural)

### 5.1 Define search class

- [x] Decide on the class of expressions to search:
  - [x] Number of component sequences `m`:
    - [x] v2: `m ≤ 2` (implemented, forward + optional backward shifts),
    - [ ] maybe optional extension: `m ≤ 3`.
  - [x] Coefficient constraints:
    - [x] small integers, e.g. |c_i| ≤ 5 or 10 (configurable list).
  - [x] Shift constraints:
    - [x] index shifts `s_i` in range, e.g., `-k ≤ s_i ≤ max_shift` (backward shifts supported).
  - [ ] Optional per-component transforms:
    - [x] simple things like `Diff`/`PartialSum` (component-transforms).

### 5.2 Two-sequence combinations

- [x] API design:
  - [x] `search_two_sequence_combinations(q, candidates, options) -> list[CombinationMatch]` (brute-force small integer coefficients).
- [x] For each unordered pair of candidates `(S_i, S_j)` in the candidate bucket:
  - [x] Precompute truncated sequences with possible shifts.
  - [x] For each allowed pair of shifts `(s_i, s_j)`:
    - [x] Build vectors without per-component transforms (scope MVP).
    - [x] Optionally add per-component transforms later.
    - [ ] (Future) Use linear algebra over ℚ for wider coefficient ranges.
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
- [ ] Provide configuration:
  - [x] `max_combinations`,
  - [x] `max_time_per_query` (if implementing time budgets),
  - [x] `max_coeff_abs` (via CLI coeff list),
  - [x] `max_shift_abs` (via CLI `--max-shift`).

### 5.5 Scoring & ranking

- [x] Define complexity measure for a combination:
  - [x] number of component sequences (fixed 2),
  - [x] sum of |coefficients|,
  - [x] sum of |shifts|,
  - [ ] transform chain lengths (still N/A).
- [x] Sort results by:
  - [x] simplest explanation first (lower complexity),
  - [x] then by length of match,
  - [ ] then by sequence popularity/importance (optional heuristic).

---

## Phase 6 – User-facing CLI / API design

### 6.1 Unified CLI interface

- [x] Single entrypoint `oeis analyze`:
  - [x] Runs exact + transform pipeline.
  - [x] Add combos when available.
  - [x] Common options: add max-candidates/combos.

### 6.2 Library API

- [x] Define high-level functions:
  - [x] `analyze_sequence(query_terms, config)` (dict payload).
  - [x] `match_exact` wrapper.
  - [x] `search_transforms`.
  - [x] `search_combinations`.
- [x] Provide data structures:
  - [x] `AnalysisResult` dataclass with diagnostics (dict-compatible).

### 6.3 Output formatting + explanation

- [ ] Human-readable explanation strings, e.g.:
  - [ ] `a(n) = 2 * A013546(n+2) + A132950(n)`
  - [ ] `a(n) = Δ A000045(n)` (first differences of Fibonacci numbers).
- [ ] Optional LaTeX-friendly output for use in papers/notes.

Progress: Combination matches now emit `a(n) = c1*Axxxx(n+s1)+c2*Ayyyy(n+s2)` with LaTeX; transform matches include human + LaTeX-ish chain descriptions.

---

## Phase 7 – Performance, profiling, and optimization

- [ ] Benchmark core operations:
  - [ ] Index build time and memory footprint.
  - [ ] Exact matcher latency vs OEIS size.
  - [ ] Transform search cost per transform.
  - [ ] Combination search cost vs candidate bucket size.
  - [x] Add quick timing harness (`scripts/bench.py`) to measure common cases.
  - [x] Add profiling helper (`scripts/profile_matchers.py`) for stage timing.
  - [x] Add build benchmark script (`scripts/bench_build.py`).
- [x] Expose per-stage timings in CLI (`oeis analyze --timings`) and API (`collect_timings=True`).
- [ ] Profile hotspots:
  - [ ] Identify slow parts (e.g. inner comparison loops, transform application).
- [ ] Optimize:
  - [ ] Use vectorized operations where possible.
  - [ ] Consider compiled extensions (C/Rust) for tight loops.
  - [ ] Cache intermediate results (e.g., transformed sequences).
- [ ] Add configuration presets:
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
- [ ] Combination tests:
  - [ ] Real OEIS-derived pairs to validate expressions beyond synthetic fixtures.

### 8.2 Integration tests

- [ ] Use known OEIS sequences as fixtures:
  - [ ] Feed them to the tool and ensure they map back to their A-numbers.
- [ ] Test transform matches:
  - [ ] Use pairs like `(Fibonacci, first differences)`, `(square numbers, second differences constant)`, etc.
- [ ] Test combination matches:
  - [ ] Construct synthetic sequences as `2*A + B` and verify tool finds that relationship.
  - [ ] Add notebook-driven regression set for whole pipeline.

### 8.3 Regression tests

- [ ] Collect interesting real-world sequences and their OEIS IDs.
- [ ] Run tool periodically and ensure output remains stable or improves.
- [ ] Detect performance regressions (benchmark snapshots).

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
- [ ] Provide example notebooks (if using Python):
  - [x] “Exploring a sequence” (docs/notebook_template.ipynb stub).
  - [x] “Using combination search to explain a sequence” (docs/notebook_combo.ipynb).
- [ ] Add FAQ:
  - [x] Limitations (what the tool can’t realistically find).
  - [x] Performance tips.
  - [x] Licensing clarification.

---

## Phase 10 – Stretch goals / research directions

- [ ] Explore additional transform families:
  - [ ] Binomial/Euler transforms.
  - [ ] Möbius transform and Dirichlet convolutions.
  - [ ] Digit-based transforms (binary, decimal).
- [ ] Integrate with external CAS tools:
  - [ ] Optional hooks to Maple/Mathematica/Pari for advanced transforms/recurrence guessing.
- [ ] Experiment with learning-based candidate selection:
  - [ ] Train a model to suggest promising OEIS candidates for combos.
- [ ] Add small web UI:
  - [ ] Paste sequence → interactive explanation tree.
- [ ] Export found relations in machine-readable format:
  - [ ] JSON schemas compatible with OEIS submission formats or other tools.

---

## Milestones

- [ ] **v0.1** – Offline OEIS index + exact/prefix/subsequence matcher (Phase 1–2).
- [ ] **v0.2** – Single-sequence transform engine and search (Phase 3).
- [ ] **v0.3** – Candidate ranking + 2-sequence linear combo search (Phase 4–5).
- [ ] **v0.4** – CLI polish, config presets, docs (Phase 6–7–9).
- [ ] **v0.5+** – 3-sequence combos, richer transforms, research experiments (Phase 8–10).
