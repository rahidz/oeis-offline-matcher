# Architecture

OEIS Offline Matcher is a local Python CLI/library backed by SQLite. Network access is confined to explicit data-sync and b-file fetch commands; query-time analysis is offline.

## Data lifecycle

1. `oeis sync` downloads `stripped.gz` and `names.gz`, optionally updates an `oeisdata` checkout, and derives keyword data. Downloads go to temporary files and replace the last known-good snapshot atomically.
2. `oeis build-index` parses the exports, joins names/keywords/offsets/formulas, computes invariants, and writes `data/processed/oeis.db`.
3. Freshness metadata records source markers, the `oeisdata` commit, build settings, row count, and timestamps. A skipped sync does not claim that the snapshot became newer.
4. `oeis status` checks source presence, age, database integrity, schema/index health, and source/build consistency. `--refresh-if-stale` performs the explicit sync-and-rebuild path.

The separate b-file corpus is intentional. `oeis bfetch` retrieves selected canonical b-files; `oeis bindex` builds a resumable canonical-file manifest, and `oeis bsearch` performs an on-demand raw exact-value scan whose results are cached by corpus generation.

## Shared analysis engine

Both `oeis analyze` and `oeis_matcher.api.analyze_sequence` call `analysis.run_analysis`. This is the single owner of stage ordering and budgets:

1. exact/prefix match, with optional subsequence fallback;
2. transform search;
3. similarity ranking;
4. mod-class decomposition;
5. candidate-bucket construction;
6. linear pair, pointwise, convolution, and linear triple search;
7. deferred expanded DB-wide fallbacks;
8. optional transform refinement;
9. cross-family merge and diversity-aware reranking.

Every expensive stage receives its own cap and the remaining global wall-time budget. Deep/max scheduling first runs a short transform probe when combination stages are requested, surfaces the cheaper combination families, and then refines transforms with remaining time.

The engine emits ordered `AnalysisEvent` values for stage starts, matches, messages, and stage completion. The CLI uses those events for streaming text; API users can supply an `on_event` callback. Checkpoint persistence is a CLI adapter around the same engine stage cache, so resumed and fresh runs share orchestration.

## Retrieval and search modules

- `matcher.py`: indexed prefix/subsequence retrieval and exact verification.
- `transform_search.py` / `transforms.py`: bounded transform-chain enumeration, domain guards, scoring, and symbolic explanations.
- `candidates.py` / `discovery.py`: deterministic candidate buckets with provenance and optional SymPy discovery.
- `combination_search.py`: linear pair/triple, pointwise, convolution, mod-class, and expanded prefix-index algorithms.
- `explanation_ranking.py`: symbolic de-duplication, family quotas, diversity, and final ranking.
- `analysis.py`: shared stage scheduler and result assembly.
- `serialization.py`: the additive JSON contract shared by CLI and API.

## Core models

- `SequenceRecord`: OEIS id, stored terms, metadata, formula, and invariants.
- `SequenceQuery`: terms (including optional wildcards), minimum match length, and subsequence policy.
- `Match`: exact/transform hit plus score, snippet, formula, and explanation fields.
- `CombinationMatch`: component ids, coefficients, shifts/transforms, expression, score, terms, and provenance.
- `AnalysisResult`: all result families, combined/ranked explanations, and diagnostics.

`AnalysisResult.to_dict()` delegates to the shared serializer. CLI and API payloads carry `schema_version: 1`; v1.x changes are additive.

## SQLite layout

The main `sequences` table stores ids, comma-encoded terms, names/formulas/keywords, offsets, prefix columns, and filter invariants such as length, extrema, gcd, monotonicity, sign pattern, nonzero count, variance, and growth rate. Recommended indexes cover prefix lookup and the common invariant filters. `oeis optimize-db` upgrades older databases in place and can add shifted prefix columns for expanded searches.

The separate b-file database stores `bfiles(seq_id, relpath, size, mtime, status)` plus generation-keyed `bfile_searches` and `bfile_search_hits`. It deliberately does not duplicate every source value. Auxiliary filenames are excluded, and cached hits preserve arbitrary-precision decimal indices as text.

## Presets and determinism

`fast`, `deep`, and `max` expand into concrete, bounded options before parsing. No-profile search defaults to `deep`; `max` is the exhaustive ceiling. Advanced options stay supported but are hidden from normal help; use `--help-advanced`.

Candidate ordering, search enumeration, family merging, and randomized selfchecks are deterministic. See `docs/reproducibility.md` for snapshot pinning and benchmark protocol.
