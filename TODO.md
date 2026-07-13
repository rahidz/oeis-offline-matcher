# TODO: OEIS Offline Matcher v1.0 Roadmap

This roadmap replaces the v0.5-era backlog and targets a practical, release-grade `v1.0`.

Archived roadmap: `TODO_v0.5.md`

## Product Direction (Locked In)

- Primary priority: broaden feature coverage while keeping quality and performance strong.
- Primary user: power-user CLI workflow (single-user local research tool).
- Interface direction: CLI/API first (no web UI required for v1.0).
- Preset direction: `max` is the exhaustive ceiling (no `ultra` tier for v1.0).
- Output direction: prioritize diverse plausible explanations and deep/exhaustive search modes.
- Dependencies direction: allow heavier optional stacks (`numpy`, `scipy`, `numba`, Rust extension, external math tools) when they provide clear wins.
- v1.0 done criteria: strong regression/perf gates, stable UX/docs, and clearly improved match quality.

---

## v1.0 Acceptance Criteria

- [ ] Quality: materially better hit quality on curated real-world cases (exact, transform, combo, pointwise, convolution, mod-class).
- [ ] Diversity: top results contain multiple non-redundant explanation families when they exist.
- [ ] Exhaustive mode: `--preset max` reliably explores deeper search space within explicit global time/check budgets.
- [ ] Reproducibility: deterministic outputs under fixed seed/options and pinned DB snapshot.
- [ ] Reliability: selfcheck + regression suite + random trials are stable and expanded.
- [ ] Performance: benchmarked and tracked; no unbounded regressions in common workflows.
- [ ] UX: startup workflow removes repeated manual venv/data freshness setup.
- [ ] Docs: v1.0 docs describe guarantees, limits, tuning knobs, and expected runtime tradeoffs.

---

## Consolidation Gate (Ordered)

Complete this gate before declaring the feature-complete phases or milestones done.

- [x] Preserve the current v1 feature tranche on a dedicated consolidation branch and baseline commit.
- [x] Make data refresh atomic: failed downloads must preserve the last known-good snapshot, and skipped downloads must not reset freshness age.
- [ ] Keep the default search CLI preset-first and concise while restoring expert access through `--help-advanced` and hidden-but-supported advanced flags.
- [ ] Ensure `--max` actually enables every intended exhaustive transform/search family, including newly added advanced transforms.
- [ ] Restore a fully green test suite after the CLI contract migration.
- [ ] Establish one shared analysis orchestration path for CLI and API, including streaming/stage events, budgets, ranking, and result serialization.
- [ ] Break up the monolithic CLI command dispatcher and combination-search hotspots only where extraction removes duplication or materially reduces complexity.
- [ ] Remove dead/shadowed code and generated repository artifacts (`$DB`, tracked `*.egg-info`).
- [ ] Repair CLI/API/JSON schema parity and add explicit additive `schema_version` contracts.
- [ ] Refresh README, FAQ, architecture, preset guidance, reproducibility guidance, changelog, and benchmark results against the consolidated implementation.
- [ ] Expand real-snapshot regressions, diversity assertions, transform inverse/property tests, fuzz replay seeds, and machine-readable command contract tests.
- [ ] Profile current workloads, optimize measured Python/SQLite bottlenecks, and add repeatable performance envelopes before introducing native complexity.
- [ ] Add deterministic local parallelism and optional acceleration only where benchmarks demonstrate a material end-to-end win.
- [ ] Audit full-corpus b-file indexing/search for duplicate auxiliary files, resumability, storage cost, and useful result ranking; then build and smoke-test the local b-file index.
- [ ] Complete an end-to-end v1.0 release audit with the full suite, selfcheck, representative preset runs, schemas, docs, and packaging verified.

---

## Phase 0 - Workflow UX (Power User CLI)

### 0.1 Startup helper script

- [x] Add `scripts/oeis-start` (or `scripts/dev-start.sh`) that:
  - [x] Ensures `.venv` exists (create if missing).
  - [x] Installs project in editable mode if not installed.
  - [x] Prints a concise environment status summary.
  - [x] Launches a shell with the project env active (or runs a passed command directly).

### 0.2 Data freshness guardrail

- [x] Persist last-sync metadata (UTC timestamp + source snapshot markers).
- [x] Add `oeis status` command to report freshness and local data/index health.
- [x] Warn if local data is older than configured threshold (default: 30 days).
- [x] Add optional non-interactive refresh flow (`--refresh-if-stale`) for power workflows.
- [x] Document expected behavior when offline or rate-limited.

### 0.3 Config ergonomics

- [x] Add config keys for freshness threshold and startup defaults.
- [x] Add one-liner setup path in README for first-time bootstrap.

---

## Phase 1 - Quality and Coverage Expansion

### 1.1 Transform/operator coverage

- [x] Add more vetted transform families (guarded by complexity and domain checks).
  - [x] Add alternating-sign transform (`alt_sign`: `(-1)^n * a(n)`).
  - [x] Add inverse binomial transform (pair with existing `binomial`).
  - [x] Add canonical Euler transform + inverse Euler transform with explicit naming/semantics.
  - [x] Add Stirling transforms (first/second kind) and their inverses.
  - [x] Generalize p-adic valuation transform family (`v_p` for configurable primes, not only `v2`).
  - [x] Add factorization-profile transforms (`lpf`, `gpf`, `rad`, squarefree indicator, Liouville lambda).
  - [x] Add index-family subsequence transforms (`index_triangular`, `index_fibonacci`, generic `index_kth_power`).
  - [x] Add ratio/quotient transforms with exactness guards (integral ratio path + safe fallback behavior).
- [x] Add richer composition constraints for deeper chains without explosion.
  - [x] Add pairwise chain guards for idempotent/index-selector/stacked-`vp` combinations.
- [x] Add structured operator metadata (invertibility/domain/risk/noise profile).
  - [x] Extend `Transform` schema with explicit metadata fields (`invertible`, `domain`, `risk`, `noise`, `complexity`).
- [x] Add opt-in advanced transforms that depend on heavier numeric backends.
  - [x] Add OGF inverse transform (`1 / A(x)`) with strict domain guards (`a0 != 0`, bounded truncation).
  - [x] Add compositional inverse / series reversion transform (advanced, strongly bounded, opt-in).

### 1.2 Combination/explanation breadth

- [x] Improve multi-family explanation search so linear/pointwise/convolution/mod-class results compete fairly.
- [x] Add better de-duplication across equivalent expressions (symbolic canonicalization).
- [x] Improve shifted/self-reference discovery under exhaustive mode.
- [x] Add guardrails for pathological rational-solver outputs.

### 1.3 Ranking improvements (diversity + depth)

- [x] Implement diversity-aware ranking (avoid near-duplicate top-N).
- [x] Add explanation-family quotas for top results (`transform`, `combo`, `pointwise`, etc.).
- [x] Add optional reranker pass for `--preset deep|max`.
- [x] Expose ranking diagnostics in JSON output for tuning.

### 1.4 Query/retrieval coverage expansion

- [x] Generalize `oeis match` into a fielded query surface (beyond raw term lists), including `name:`, `formula:`, and `id:` forms.
- [x] Add user-facing invariant/tag filters in CLI (e.g., monotonic/sign-pattern/has-formula/keyword combinations) with deterministic semantics.
- [x] Add positional/value constraints for search (`term@index`, contains-all terms, excludes-term) to improve non-prefix discovery workflows.

---

## Phase 2 - Search Depth and Exhaustive Modes

### 2.1 Exhaustive mode hardening

- [x] Finalize preset contracts and document them clearly:
  - [x] `fast`: exact-first + a small extra search budget; aim to stay within ~10s total.
  - [x] `deep`: broader search with combos/expansions; target typical runs around 1-2 minutes.
  - [x] `max`: exhaustive ceiling with all available search families and long budgets (hour-scale or longer via explicit caps).
- [x] Translate preset contracts into concrete `PRESETS` defaults in `src/oeis_matcher/cli.py` (time caps, candidate caps, transform/combination breadth).
- [x] Add preset contract tests/bench checks to keep real runtime behavior aligned with the documented intent.
- [x] Ensure every stage is bounded by both per-stage and global budgets.
- [x] Add checkpoint/resume support for long exhaustive runs (optional persisted state).
- [x] Improve stage scheduling for better time-to-first-meaningful-hit.

### 2.2 Candidate generation expansion

- [x] Add optional wider prefilters for difficult sequences.
- [x] Add pluggable candidate providers (exact/similarity/index-join/expanded).
- [x] Track candidate provenance through scoring for explainability.
- [x] Add an optional symbolic/numeric-discovery candidate provider (SymPy/Sage/GP-backed recurrence/OGF/closed-form guessers) and feed discovered candidates into ranking with provenance.

### 2.3 Parallel/distributed local execution

- [ ] Add safe local parallelism for expensive independent search branches.
- [ ] Add deterministic merge ordering for parallel result streams.
- [ ] Add CPU pinning / worker caps in CLI for reproducible benchmarking.

---

## Phase 3 - Performance Engineering (Including Heavy Tooling)

### 3.1 Python-side acceleration

- [ ] Profile hot loops and move bottlenecks to vectorized/natively compiled paths.
- [ ] Add optional `numpy`/`numba` accelerated kernels for transform and combo primitives (first acceleration path).
- [ ] Add cache strategy for repeated transformed/candidate vectors.

### 3.2 Native extension path

- [ ] Prototype optional Rust extension for high-cost matching kernels.
- [ ] Keep pure-Python fallback parity with golden tests.
- [ ] Gate optional native path with clear feature flags and CI matrix.

### 3.3 Tool-assisted workflows

- [ ] Add optional benchmark harness using `hyperfine` for repeatable local perf checks.
- [ ] Add scripts to compare perf across presets and DB sizes.
- [ ] Keep results versioned under `docs/benchmarks.md` updates.

---

## Phase 4 - Determinism, Testing, and Validation

### 4.1 Regression suite expansion

- [ ] Expand `docs/regressions.json` to include harder real-world examples and edge families.
- [ ] Add expected diversity checks (not just one target id).
- [ ] Add regression cases for stale-index and missing-index behavior.

### 4.2 Randomized/property testing

- [ ] Add property tests for transform invertibility and composition invariants where applicable.
- [ ] Expand combo fuzzing to stress rational/shifted/component-transform paths.
- [ ] Add long-run seed corpus for flaky-case replay.

### 4.3 Performance regression gates

- [ ] Define baseline timing envelopes for representative workloads.
- [ ] Add CI/per-commit smoke thresholds and local "strict perf" mode.
- [ ] Flag worst-case explosion scenarios explicitly in tests/docs.

---

## Phase 5 - CLI/API Stability and Docs for v1.0

### 5.1 CLI/API stabilization

- [x] Review/normalize option names and defaults across `match/tsearch/combo/analyze`.
- [ ] Finalize additive-only JSON/schema compatibility policy for `v1.x` and add explicit `schema_version`.
- [ ] Add command-level contract tests for machine-readable output.

### 5.2 Docs pass

- [ ] Rewrite README for v1.0 workflows (bootstrap, refresh, exhaustive tuning, troubleshooting).
- [x] Align README status/preset language with v1.0 direction and `fast/deep/max` runtime intent.
- [ ] Add "how to choose presets" and "why this result ranked first" docs.
- [ ] Add reproducibility guide (seeds, DB pinning, benchmark protocol).

### 5.3 Release readiness

- [ ] Add changelog and migration notes from v0.x to v1.0.
- [ ] Tag release checklist (quality, perf, docs, schemas, selfcheck green).
- [ ] Prepare packaging/release process (including optional extras).

---

## Stretch Track (Post-v1.0 or Time-Permitting)

- [ ] Plugin system for third-party transforms and candidate providers.
- [ ] Symbolic simplification/canonicalization engine for expression equivalence classes.
- [ ] Deeper arithmetic tooling integration (PARI/GP/Sage/GAP) behind optional adapters.
- [ ] Alternative storage backends for very large snapshots or lower-memory machines.
- [ ] Lightweight notebook helpers for comparative exploration (still CLI/API-centric).

---

## Milestones

- [x] **v0.6** - Startup UX + freshness/status + config ergonomics.
- [ ] **v0.7** - Ranking diversity + broader explanation families.
- [ ] **v0.8** - Exhaustive mode hardening + parallel search foundations.
- [ ] **v0.9** - Acceleration path (numpy/numba and/or optional Rust kernels) + perf gates.
- [ ] **v1.0-rc1** - API/CLI freeze, docs freeze, expanded regression/perf suite.
- [ ] **v1.0** - Release with acceptance criteria satisfied.

---

## Decisions Locked

- `oeis status` will be a dedicated read-only command; `oeis sync` remains update/fetch focused.
- Acceleration order: `numpy`/`numba` first for low-friction wins, then optional Rust for stable hot kernels.
- Compatibility policy: additive-only JSON/schema changes in `v1.x`; breaking schema changes deferred to `v2.0`.
