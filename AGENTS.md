# AGENTS

## Vision
Build a local, offline-first OEIS analysis tool for power-user sequence research.
Given a numeric sequence, the tool should surface:
- Direct OEIS matches (exact/prefix/subsequence).
- Transform-based explanations.
- Multi-sequence decompositions (linear, pointwise, convolution, and related structured matches).

## Current State
- The v1.0 release audit is complete; see `docs/release_checklist.md`.
- Post-v1.0 work lives in `TODO.md`. Parallel and native acceleration are deferred pending a measured end-to-end win.
- The v0.5 roadmap is archived in `TODO_v0.5.md`.

## Workstyle Principles
- Keep everything reproducible and documented; prefer small, composable modules.
- Optimize for fast local iteration (no network calls at query time after initial download).
- Log decisions and assumptions in code comments or small docs near the code they affect.
- Add tests alongside new logic; value correctness over micro-optimizations early on.
- Please work autonomously unless you encounter any issues, and mark items off your `TODO.md` as you go through.

## v1.0 Direction (Locked)
- Priority: broaden feature coverage while preserving quality, reproducibility, and performance.
- User profile: single-user, power-user CLI/API workflow.
- Presets: `max` is the exhaustive ceiling; no `ultra` tier for v1.0.
- Output preference: prioritize diverse plausible explanations and deep/exhaustive search modes.
- Dependencies: heavier optional stacks are acceptable when they produce clear wins (`numpy`/`numba` first, optional Rust/native later).
- Compatibility: additive-only JSON/schema changes in `v1.x`; breaking schema changes defer to `v2.0`.
- UX: preserve the dedicated `oeis status` command and data freshness guardrails.

## Execution Rules
- Treat `TODO.md` as the source of truth for roadmap tasks.
- When implementing roadmap items, update `TODO.md` checkboxes in the same change set.
- Keep deterministic behavior as default (seeded/randomized modes must be reproducible).
- Prefer bounded search with explicit time/check limits; avoid unbounded exhaustive loops.
- Keep CLI/API behavior and JSON schemas stable unless a roadmap item explicitly changes them.
