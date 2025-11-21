#!/usr/bin/env bash
set -euo pipefail

# Fetches OEIS data files into data/raw.
# Usage: scripts/fetch_oeis_data.sh [--force] [--clone-oeisdata]
#   --force            Re-download files even if they already exist.
#   --clone-oeisdata   Also clone https://github.com/oeis/oeisdata (shallow).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="${ROOT_DIR}/data/raw"
STRIPPED_URL="https://oeis.org/stripped.gz"
NAMES_URL="https://oeis.org/names.gz"
OEISDATA_DIR="${RAW_DIR}/oeisdata"

FORCE=0
CLONE_OEISDATA=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --clone-oeisdata) CLONE_OEISDATA=1 ;;
    *) echo "Usage: $0 [--force] [--clone-oeisdata]" >&2; exit 1 ;;
  esac
done

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

if [[ ${CLONE_OEISDATA} -eq 1 ]]; then
  if [[ -d "${OEISDATA_DIR}/.git" && ${FORCE} -eq 0 ]]; then
    echo "[skip] oeisdata repo already exists at ${OEISDATA_DIR}"
  else
    if [[ -d "${OEISDATA_DIR}" ]]; then
      echo "[remove] existing ${OEISDATA_DIR}"
      rm -rf "${OEISDATA_DIR}"
    fi
    echo "[clone] https://github.com/oeis/oeisdata -> ${OEISDATA_DIR}"
    git clone --depth 1 https://github.com/oeis/oeisdata "${OEISDATA_DIR}"
  fi
fi

cat <<'EOF'
Note: OEIS content is licensed under CC BY-SA 4.0. When redistributing data or
outputs derived from these files, include proper attribution and share-alike.
EOF
