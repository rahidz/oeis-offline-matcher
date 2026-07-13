# B-file corpus and exact-value search

The raw b-file corpus is intentionally retained. It extends far beyond the short prefixes in `stripped.gz` and is valuable for asking “which OEIS sequences contain this integer anywhere in their published b-file?”

## Local corpus audit (2026-07-13)

| class | files | size |
| --- | ---: | ---: |
| canonical `bNNNNNN.txt` | 214,983 | 28.05 GiB |
| auxiliary `bNNNNNN_*.txt` | 25,611 | 3.05 GiB |

The complete `oeisdata/files` tree, including PDFs, archives, videos, and other supporting files, is about 50.58 GB. Auxiliary b-files are excluded from exact-value search because several can map to the same A-number and otherwise create duplicate or ambiguous results.

The July refresh encountered 1,310 unavailable/corrupt Git LFS b-file objects. Their canonical text was fetched directly from `oeis.org`; the local manifest therefore reports zero remaining LFS pointers. Those substitutions intentionally leave the nested `oeisdata` working tree dirty.

## Why the index is a manifest

Materializing every `(value, sequence, n)` row in SQLite duplicates 28 GiB of source text and adds a large B-tree before accounting for auxiliary files. The v1 design instead uses:

- a resumable 20 MiB SQLite manifest with one row per canonical b-file;
- raw, multithreaded `ripgrep` for the first search of an integer;
- a generation-keyed SQLite posting cache for subsequent searches;
- the main OEIS database for names and `core`/`nice`/`easy` ranking signals.

Any changed, added, or removed canonical file increments the manifest generation and invalidates cached value searches. An unchanged rebuild skips all 214,983 manifest rows.

## Build and search

```bash
# Fetch/repair the complete oeisdata supporting-file corpus. Safe to resume.
scripts/fetch_all_bfiles.sh --jobs=2

# Build or update the compact manifest (default paths shown explicitly).
oeis bindex \
  --files-root data/raw/oeisdata/files \
  --db data/processed/bfiles.db

# Exact integer search. The first lookup scans raw canonical files; repeats use cache.
oeis bsearch 514229 --db data/processed/bfiles.db

# Force one value to be rescanned, or bound an unattended cold scan.
oeis bsearch 514229 --refresh-cache --max-time 120
```

On this machine the full manifest build took about 8 seconds and an unchanged pass about 7.5 seconds (the filesystem still has to be audited). Searching `514229` found 740 canonical b-files: observed raw-scan times ranged from 2.7 seconds with a hot filesystem cache to 57 seconds cold; the SQLite cache returned in about 0.08 seconds.

Each result represents the best (smallest absolute) index for one canonical b-file. Ranking prefers OEIS `core`, then `nice`/`easy`, then small `|n|`; the JSON includes the title, keywords, source-relative path, and line number. This put Fibonacci A000045 second for `514229` rather than burying it among hundreds of incidental occurrences.

`--threads 0` (the default) lets ripgrep choose its worker count. Use `--threads N` for a reproducible cap. A timed-out scan writes no partial cache.
