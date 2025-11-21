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
  - [ ] Optionally clone `https://github.com/oeis/oeisdata` for full metadata.
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
  - [ ] Early exit on mismatch to reduce comparisons (KMP handles subseq; prefix uses slicing).
- [ ] Expose API:
  - [ ] `match_exact_prefix(query) -> list[Match]`.
  - [ ] `match_subsequence(query) -> list[Match]`.
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

---

## Phase 4 – Candidate ranking & similarity filtering (for combos)

### 4.1 Numeric signatures / features

- [x] Define simple numeric features per sequence:
  - [x] Length of usable prefix.
  - [x] `gcd`, `min`, `max`.
  - [x] First-diff sign pattern.
  - [x] Sign pattern of terms.
  - [x] Nonzero count.
  - [ ] Approximate growth rate (future).
- [x] Precompute and store these features during index build (in SQLite).

### 4.2 Similarity scoring

- [ ] Implement a similarity metric between two finite sequences:
  - [ ] E.g. normalized mean squared error after scaling and optional offset.
  - [ ] Or correlation coefficient of `(q_n)` vs `(S_n)` up to k terms.
- [ ] Implement function `rank_candidates_for_query(q)`:
  - [x] Filter sequences quickly by simple invariants (sign pattern, first-diff sign, nonzero band).
  - [ ] Compute similarity scores against the filtered subset.
  - [ ] Return top-K candidate sequences with highest similarity.

### 4.3 Integration with previous phases

- [ ] After running:
  - [ ] direct matches,
  - [ ] transform-based matches,
  - [ ] add similarity-ranked candidates:
    - [ ] Ensure union of candidates ≤ some K (e.g., 100–200).
- [ ] Expose API to get “candidate bucket” for multi-sequence search:
  - [ ] `get_candidate_bucket(q, K) -> list[Candidate]`.

---

## Phase 5 – Multi-sequence linear combination search (2b, plural)

### 5.1 Define search class

- [ ] Decide on the class of expressions to search:
  - [ ] Number of component sequences `m`:
    - [ ] v2: `m ≤ 2`,
    - [ ] maybe optional extension: `m ≤ 3`.
  - [ ] Coefficient constraints:
    - [ ] small integers, e.g. |c_i| ≤ 5 or 10.
  - [ ] Shift constraints:
    - [ ] index shifts `s_i` in range, e.g., `-5 ≤ s_i ≤ 5`.
  - [ ] Optional per-component transforms:
    - [ ] simple things like `Scale`, `Shift`, `Negate`, maybe `Diff`/`Sum`.

### 5.2 Two-sequence combinations

- [ ] API design:
  - [ ] `find_linear_combos(q, candidates, options) -> list[Combination]`.
- [ ] For each unordered pair of candidates `(S_i, S_j)` in the candidate bucket:
  - [ ] Precompute truncated sequences with possible shifts.
  - [ ] For each allowed pair of shifts `(s_i, s_j)`:
    - [ ] Build vectors:
      - [ ] `v_i(n) = T_i(S_i)(n + s_i)`,
      - [ ] `v_j(n) = T_j(S_j)(n + s_j)`,
      - [ ] where `T_i, T_j` are any per-component transforms allowed.
    - [ ] Solve for `a, b` in:
      \[
      a v_i(n) + b v_j(n) = q_n
      \]
      over the first k terms.
      - [ ] Use linear algebra over ℚ to find rational solution.
      - [ ] Check if `(a, b)` are integers within allowed bounds.
    - [ ] Verify equality on all k terms.
    - [ ] If passed, record `Combination`:
      - [ ] A-numbers, coefficients, shifts, component transforms.

### 5.3 Optional: Three-sequence combinations

- [ ] Extend above method:
  - [ ] Use 3 columns in matrix, solve for `(a, b, c)`.
  - [ ] Only run if:
    - [ ] candidate bucket size is small, and/or
    - [ ] user explicitly enables 3-term combinations.
- [ ] Guard with strong limits on:
  - [ ] number of pairs/triples,
  - [ ] coefficient ranges,
  - [ ] transform depth.

### 5.4 Complexity safeguards

- [ ] Hard-limit candidate bucket size (e.g. K ≤ 100).
- [ ] Hard-limit total combinations checked per query.
- [ ] Provide configuration:
  - [ ] `max_combinations`,
  - [ ] `max_time_per_query` (if implementing time budgets),
  - [ ] `max_coeff_abs`,
  - [ ] `max_shift_abs`.

### 5.5 Scoring & ranking

- [ ] Define complexity measure for a combination:
  - [ ] number of component sequences,
  - [ ] sum of |coefficients|,
  - [ ] sum of |shifts|,
  - [ ] transform chain lengths.
- [ ] Sort results by:
  - [ ] simplest explanation first (Occam’s razor),
  - [ ] then by length of match (more terms matched),
  - [ ] then by sequence popularity/importance (optional heuristic).

---

## Phase 6 – User-facing CLI / API design

### 6.1 Unified CLI interface

- [x] Single entrypoint `oeis analyze`:
  - [x] Runs exact + transform pipeline.
  - [ ] Add combos when available.
  - [ ] Common options: add max-candidates/combos later.

### 6.2 Library API

- [ ] Define high-level functions:
  - [ ] `analyze_sequence(query_terms, config) -> AnalysisResult`.
  - [ ] `match_exact(query)`.
  - [ ] `search_transforms(query, config)`.
  - [ ] `search_combinations(query, config)`.
- [ ] Provide data structures:
  - [ ] `AnalysisResult`:
    - [ ] `exact_matches`,
    - [ ] `transform_matches`,
    - [ ] `combination_matches`,
    - [ ] diagnostics (candidate counts, search limits hit, etc.).

### 6.3 Output formatting + explanation

- [ ] Human-readable explanation strings, e.g.:
  - [ ] `a(n) = 2 * A013546(n+2) + A132950(n)`
  - [ ] `a(n) = Δ A000045(n)` (first differences of Fibonacci numbers).
- [ ] Optional LaTeX-friendly output for use in papers/notes.

---

## Phase 7 – Performance, profiling, and optimization

- [ ] Benchmark core operations:
  - [ ] Index build time and memory footprint.
  - [ ] Exact matcher latency vs OEIS size.
  - [ ] Transform search cost per transform.
  - [ ] Combination search cost vs candidate bucket size.
- [ ] Profile hotspots:
  - [ ] Identify slow parts (e.g. inner comparison loops, transform application).
- [ ] Optimize:
  - [ ] Use vectorized operations where possible.
  - [ ] Consider compiled extensions (C/Rust) for tight loops.
  - [ ] Cache intermediate results (e.g., transformed sequences).
- [ ] Add configuration presets:
  - [ ] “Fast” preset (small transform set, few candidates).
  - [ ] “Deep” preset (more transforms, combos, but bounded).

---

## Phase 8 – Testing & validation

### 8.1 Unit tests

- [x] Parser tests:
  - [x] `parse_stripped` on sample lines.
  - [x] `parse_names` on sample lines.
- [ ] Transform tests:
  - [ ] Verify output of `Diff`, `Sum`, `Shift`, etc. on known sequences.
- [x] Matcher tests:
  - [x] Exact prefix/subsequence cases.
  - [ ] Edge cases: too short, mismatched lengths, negative numbers.

### 8.2 Integration tests

- [ ] Use known OEIS sequences as fixtures:
  - [ ] Feed them to the tool and ensure they map back to their A-numbers.
- [ ] Test transform matches:
  - [ ] Use pairs like `(Fibonacci, first differences)`, `(square numbers, second differences constant)`, etc.
- [ ] Test combination matches:
  - [ ] Construct synthetic sequences as `2*A + B` and verify tool finds that relationship.

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
- [ ] Write `docs/architecture.md`:
  - [ ] Data flow diagram (query → transforms → matchers → combos).
  - [ ] Description of internal data structures.
- [ ] Provide example notebooks (if using Python):
  - [ ] “Exploring a sequence”.
  - [ ] “Using combination search to explain a sequence”.
- [ ] Add FAQ:
  - [ ] Limitations (what the tool can’t realistically find).
  - [ ] Performance tips.
  - [ ] Licensing clarification.

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
