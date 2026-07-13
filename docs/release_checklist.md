# v1.0 Release Audit

Audit date: July 13, 2026. Branch: `codex/v1-consolidation`.

## Snapshot and storage

- [x] `oeis status --json` reports `ready: true`, a fresh snapshot, 397,352 sequences, and no missing recommended indexes.
- [x] The main SQLite database and the b-file manifest both pass `PRAGMA quick_check`.
- [x] The OEIS exports and `oeisdata` supporting tree were refreshed; the latter is pinned at `7e846541fdca87dc2be0b6324ea96e3057310a24`.
- [x] The compact b-file manifest contains 214,983 canonical files. A search for `514229` finds 740 sequences and ranks A001519 first and Fibonacci A000045 second.
- [x] The 1,310 canonical b-files unavailable through upstream Git LFS were repaired directly from OEIS. These intentional substitutions are why the nested `oeisdata` checkout is dirty.

## Correctness and contracts

- [x] `python -m pytest -q`: 246 passed.
- [x] `ruff check src/oeis_matcher tests --select F`: clean.
- [x] Full-snapshot selfcheck: 9/9 curated regressions and 80/80 seeded pair, triple, pointwise, and convolution trials passed.
- [x] `fast`, `deep`, and capped `max` smoke runs all returned `schema_version: 1`; the pronic fixture produced 5, 58, and 80 ranked explanations respectively.
- [x] Two independent `deep` JSON runs for the same query were byte-identical (`sha256: 4e3a8abd276cb387d7eeae59ede3414f048dc126415f504475299b3f3609bd73`).
- [x] Normal help stays preset-first and concise; `--help-advanced` exposes the supported expert controls.
- [x] `scripts/oeis-start` preserves child stdout for machine-readable pipelines while sending its own status to stderr.

## Performance

- [x] `python scripts/bench.py --repeats 5 --strict` passes every maintained envelope.

| Workload | Median | Envelope |
| --- | ---: | ---: |
| Exact Fibonacci | 1.43 ms | 25 ms |
| Short transform search | 25.53 ms | 250 ms |
| Subsequence search | 0.45 ms | 25 ms |
| Deep transform search | 27.17 ms | 250 ms |
| Small pair combination | 9.64 ms | 500 ms |
| Mod-class decomposition | 6.37 ms | 250 ms |

- [x] Local thread/process probes did not reach the documented 20% material-win threshold, so v1.0 keeps the simpler deterministic serial implementation. Optional native/vectorized paths remain deferred until a measured workload justifies them.

## Distribution and documentation

- [x] `uv build` produces the 1.0.0 wheel and source distribution.
- [x] `twine check dist/*` passes.
- [x] The wheel installs in a fresh virtual environment, reports `oeis 1.0.0`, imports the public API, and returns schema-versioned results.
- [x] The source distribution excludes the raw OEIS corpus and generated local databases.
- [x] README, FAQ, architecture, presets, reproducibility, b-file behavior, benchmarks, changelog, and migration guidance reflect the consolidated v1 implementation.

This checklist verifies release readiness; creating a public tag or release remains an explicit publishing action.
