# Changelog

## Unreleased

### Added

- Optional loopback-only browser UI for every CLI workflow, with guided search controls, local job history, health reporting, result cards, and cancellable process-isolated runs.
- Repeatable `--exclude-id` / `--exclude-ids` filtering across `match`, `tsearch`, `combo`, and `analyze`, plus matching Python API parameters.

## 1.0.0

### Added

- Offline status/freshness reporting, startup bootstrap helper, atomic refresh, and stale-data refresh workflow.
- Preset-first `fast`, `deep`, and exhaustive-ceiling `max` search contracts with global and per-stage budgets.
- Advanced transform families, symbolic explanations, optional discovery, mod-class/pointwise/convolution decompositions, expanded DB-wide fallbacks, checkpoint/resume, and diversity-aware reranking.
- Fielded metadata/value queries and a separate b-file fetch/index/search workflow.
- Resumable full-corpus b-file manifests, canonical/auxiliary de-duplication, direct repair for unavailable LFS objects, exact raw-value scans, cached postings, and OEIS-aware result ranking.
- Shared CLI/API analysis orchestration with ordered stage events and versioned JSON schemas.

### Changed from v0.x

- Search commands default to `deep` when no profile is named. Prefer `--fast`, `--deep`, or `--max`; use `--help-advanced` for the full tuning surface.
- `max` is the widest supported preset; there is no `ultra` tier.
- Analyze JSON now always includes diagnostics, all result-family arrays, combined/ranked explanations, and `schema_version: 1`.
- API and CLI analysis now execute the same scheduler and serializer. v1.x JSON changes are additive-only; breaking changes wait for v2.0.
- Failed refresh downloads preserve the prior snapshot, and no-op/skipped syncs no longer reset freshness age.
- B-file indexing no longer materializes every value into a second giant SQLite corpus; `bindex` builds a compact manifest and `bsearch` scans/caches values on demand.

### Migration notes

- Rebuild the main index after refreshing data: `oeis status --refresh-if-stale`, or run `oeis sync` followed by `oeis build-index`.
- Run `oeis optimize-db` for databases created by older versions; add shifted prefixes if using expanded shifted pair search.
- Scripts that consumed pre-v1 JSON should tolerate new fields and may key behavior on `schema_version`.
- Legacy expert flags remain supported but are hidden from normal help rather than removed.
- Re-run `oeis bindex --rebuild` if you created an experimental pre-v1 `bfile_values` database; normal `bindex` also migrates it automatically.
