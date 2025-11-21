#!/usr/bin/env bash
set -euo pipefail

# Fetches OEIS data files into data/raw.
# Usage: scripts/fetch_oeis_data.sh [--force]
#   --force   Re-download files even if they already exist.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="${ROOT_DIR}/data/raw"
STRIPPED_URL="https://oeis.org/stripped.gz"
NAMES_URL="https://oeis.org/names.gz"

FORCE=0
if [[ "${1-}" == "--force" ]]; then
  FORCE=1
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--force]" >&2
  exit 1
fi

mkdir -p "${RAW_DIR}"

download() {
  local url="$1"
  local dest="$2"
  local label="$3"

  if [[ -f "${dest}" && ${FORCE} -eq 0 ]]; then
    echo "[skip] ${label} already exists at ${dest}"
    return
  fi

  echo "[fetch] ${label} -> ${dest}"
  curl -L --fail --progress-bar "${url}" -o "${dest}"
}

download "${STRIPPED_URL}" "${RAW_DIR}/stripped.gz" "stripped.gz (sequence terms)"
download "${NAMES_URL}" "${RAW_DIR}/names.gz" "names.gz (titles)"

cat <<'EOF'
Note: OEIS content is licensed under CC BY-SA 4.0. When redistributing data or
outputs derived from these files, include proper attribution and share-alike.
EOF
