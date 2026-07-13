#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
db=${OEIS_DB_PATH:-data/processed/oeis.db}
out=${1:-/tmp/oeis-hyperfine.json}
pin=
[[ -z ${OEIS_BENCH_CPU:-} ]] || pin="taskset -c ${OEIS_BENCH_CPU} "

hyperfine --warmup 2 --runs "${OEIS_BENCH_RUNS:-8}" --export-json "$out" \
  "${pin}.venv/bin/oeis match '0,1,1,2,3,5,8' --db '$db' --json" \
  "${pin}.venv/bin/oeis analyze '0,2,6,12,20,30,42,56' --db '$db' --fast --json" \
  "${pin}.venv/bin/oeis analyze '0,2,6,12,20,30,42,56' --db '$db' --deep --time-cap 10 --json"

echo "Wrote $out"
