#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="${1:-${ROOT_DIR}/idea6_candidates.md}"
DB="${DB:-${ROOT_DIR}/data/processed/oeis.db}"
FAST_CAP="${FAST_CAP:-10}"
DEEP_CAP="${DEEP_CAP:-120}"
MAX_CAP="${MAX_CAP:-3600}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/runs/idea6_$(date +%Y%m%d_%H%M%S)}"

if [[ ! -f "${INPUT}" ]]; then
  echo "Input file not found: ${INPUT}" >&2
  exit 1
fi
if [[ ! -f "${DB}" ]]; then
  echo "DB file not found: ${DB}" >&2
  exit 1
fi

if [[ ! -x "${ROOT_DIR}/.venv/bin/oeis" ]]; then
  echo "[idea6-run] bootstrapping venv/package via scripts/oeis-start"
  "${ROOT_DIR}/scripts/oeis-start" --no-status -- true
fi
OEIS_BIN="${ROOT_DIR}/.venv/bin/oeis"
if ! command -v jq >/dev/null 2>&1; then
  echo "Missing required tool: jq" >&2
  exit 1
fi

has_exact_hit() {
  local json_file="$1"
  [[ -s "${json_file}" ]] || return 1
  jq -e '((.exact_matches // []) | length) > 0' "${json_file}" >/dev/null 2>&1
}

mkdir -p "${OUT_DIR}"/{fast,deep,max,logs}
awk -F'`' '
function norm_seq(s, out) {
  out = s
  gsub(/`/, "", out)
  gsub(/#.*/, "", out)
  gsub(/^[[:space:]]+|[[:space:]]+$/, "", out)
  gsub(/, +/, ",", out)
  gsub(/[[:space:]]+/, "", out)
  return out
}
function mark_id(id, n) {
  used[id] = 1
  n = substr(id, 2) + 0
  if (n > max_id) max_id = n
}
/^- `S[0-9]+`/ {
  id = $2
  seq = norm_seq($8)
  if (id != "" && seq != "") {
    print id "\t" seq
    mark_id(id)
  }
  next
}
tolower($0) ~ /^[[:space:]]*-[[:space:]]*first terms[[:space:]]*\(/ {
  line = $0
  sub(/^.*:[[:space:]]*/, "", line)
  seq = norm_seq(line)
  if (seq != "") {
    do {
      max_id += 1
      id = sprintf("S%03d", max_id)
    } while (id in used)
    used[id] = 1
    print id "\t" seq
  }
}
' "${INPUT}" > "${OUT_DIR}/sequences.tsv"
total="$(wc -l < "${OUT_DIR}/sequences.tsv")"
if [[ "${total}" -eq 0 ]]; then
  echo "No sequences parsed from: ${INPUT}" >&2
  echo "Expected either legacy lines like '- \`S001\` ... : \`1,2,3\`'" >&2
  echo "or lines like '- First terms (n=...): 1,2,3'." >&2
  exit 1
fi

{
  echo "start=$(date -Is)"
  echo "input=${INPUT}"
  echo "db=${DB}"
  echo "fast_cap=${FAST_CAP}"
  echo "deep_cap=${DEEP_CAP}"
  echo "max_cap=${MAX_CAP}"
  echo "sequence_count=${total}"
} > "${OUT_DIR}/run.meta"

for preset in fast deep max; do
  case "${preset}" in
    fast) cap="${FAST_CAP}" ;;
    deep) cap="${DEEP_CAP}" ;;
    max) cap="${MAX_CAP}" ;;
  esac
  echo "[$(date -Is)] PHASE --${preset} (time-cap ${cap}s)" | tee -a "${OUT_DIR}/logs/run.log"
  i=0
  while IFS=$'\t' read -r id seq; do
    [[ -z "${id}" || -z "${seq}" ]] && continue
    i=$((i + 1))
    fast_json="${OUT_DIR}/fast/${id}.json"
    deep_json="${OUT_DIR}/deep/${id}.json"

    if [[ "${preset}" == "deep" ]] && has_exact_hit "${fast_json}"; then
      echo "[$(date -Is)] SKIP (${i}/${total}) ${id} --deep (exact hit in --fast)" | tee -a "${OUT_DIR}/logs/run.log"
      continue
    fi
    if [[ "${preset}" == "max" ]] && has_exact_hit "${fast_json}"; then
      echo "[$(date -Is)] SKIP (${i}/${total}) ${id} --max (exact hit in --fast)" | tee -a "${OUT_DIR}/logs/run.log"
      continue
    fi
    if [[ "${preset}" == "max" ]] && has_exact_hit "${deep_json}"; then
      echo "[$(date -Is)] SKIP (${i}/${total}) ${id} --max (exact hit in --deep)" | tee -a "${OUT_DIR}/logs/run.log"
      continue
    fi

    json="${OUT_DIR}/${preset}/${id}.json"
    err="${OUT_DIR}/logs/${id}.${preset}.stderr"
    if [[ -s "${json}" ]]; then
      echo "[$(date -Is)] SKIP (${i}/${total}) ${id} --${preset} (existing json)" | tee -a "${OUT_DIR}/logs/run.log"
      continue
    fi
    echo "[$(date -Is)] RUN  (${i}/${total}) ${id} --${preset} --time-cap ${cap}" | tee -a "${OUT_DIR}/logs/run.log"
    if ! "${OEIS_BIN}" analyze "${seq}" --"${preset}" --time-cap "${cap}" --json --db "${DB}" > "${json}" 2> "${err}"; then
      echo "[$(date -Is)] ERROR (${i}/${total}) ${id} --${preset}" | tee -a "${OUT_DIR}/logs/run.log"
    fi
  done < "${OUT_DIR}/sequences.tsv"
done

echo "[$(date -Is)] DONE out=${OUT_DIR}" | tee -a "${OUT_DIR}/logs/run.log"
