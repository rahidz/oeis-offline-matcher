# AGENTS

## Vision
Build a local tool that downloads a snapshot of the OEIS once, then helps a user input a numeric sequence and:
- Find direct matches to OEIS entries.
- Discover composite transformations (e.g., `2 * A013546` starting at `n=3` plus `A132950`).

## First Milestone
1) Script to fetch and cache the full OEIS data set locally (one-time download with an easy refresh flag).  
2) CLI that accepts a sequence (comma or space separated) and returns:
   - Exact entry matches.
   - Top-ranked transformation matches with human-readable formulas and offsets.
3) Deterministic, testable matching logic: pure functions for parsing, normalization, and scoring.

## Workstyle Principles
- Keep everything reproducible and documented; prefer small, composable modules.
- Optimize for fast local iteration (no network calls at query time after initial download).
- Log decisions and assumptions in code comments or small docs near the code they affect.
- Add tests alongside new logic; value correctness over micro-optimizations early on.

## Open Questions To Resolve Soon
- Which OEIS export format to store locally (full `stripped.gz` vs. JSON mirror vs. custom SQLite import)?
- Minimum required metadata for transformations (offsets, formulae, cross-references).
- Scoring rubric for transformation matches (exact prefix vs. best partial, penalty for complexity).
- Limits on search depth for composed transformations to keep runtime acceptable.

## Immediate Next Steps
- Decide the local data shape (likely SQLite with precomputed indexes for speed).
- Draft the downloader/bootstrap script interface (e.g., `oeis sync --force`).
- Define sequence input normalization rules (whitespace, +/- signs, leading zeros).
- Sketch the transformation operators to support first (scale, shift, add, concatenate?).
