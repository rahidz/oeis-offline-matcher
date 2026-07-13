#!/usr/bin/env bash
set -euo pipefail

# Fetch all OEIS supporting files via oeisdata + Git LFS, then repair
# unavailable canonical b-files from oeis.org.
# Safe to re-run; fetch/checkouts resume.
# Usage: scripts/fetch_all_bfiles.sh [--repo PATH] [--jobs N] [--skip-pull] [--no-direct-fallback] [--progress-every SEC]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="${ROOT_DIR}/data/raw/oeisdata"
JOBS=2
SKIP_PULL=0
PROGRESS_EVERY=120
DIRECT_FALLBACK=1

for arg in "$@"; do
  case "$arg" in
    --repo=*) REPO_DIR="${arg#*=}" ;;
    --jobs=*) JOBS="${arg#*=}" ;;
    --skip-pull) SKIP_PULL=1 ;;
    --no-direct-fallback) DIRECT_FALLBACK=0 ;;
    --progress-every=*) PROGRESS_EVERY="${arg#*=}" ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/fetch_all_bfiles.sh [--repo PATH] [--jobs N] [--skip-pull] [--no-direct-fallback] [--progress-every SEC]

Options:
  --repo=PATH   Path to oeisdata git repo (default: data/raw/oeisdata)
  --jobs=N      Git LFS concurrent transfers (default: 2; be polite)
  --skip-pull   Skip `git pull --ff-only` before LFS fetch
  --no-direct-fallback  Leave unavailable LFS b-files as pointers
  --progress-every=SEC  Print b-file progress every N seconds (default: 120, 0=off)
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "git not found" >&2
  exit 1
fi
if ! git lfs version >/dev/null 2>&1; then
  echo "git-lfs not available; install/fix git-lfs first" >&2
  exit 1
fi

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  echo "[clone] https://github.com/oeis/oeisdata -> ${REPO_DIR}"
  mkdir -p "$(dirname "${REPO_DIR}")"
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/oeis/oeisdata "${REPO_DIR}"
fi

echo "[repo] ${REPO_DIR}"
if [[ ${SKIP_PULL} -eq 0 ]]; then
  echo "[pull] git pull --ff-only"
  git -C "${REPO_DIR}" pull --ff-only
fi

echo "[config] lfs.concurrenttransfers=${JOBS}"
git -C "${REPO_DIR}" config lfs.concurrenttransfers "${JOBS}"

progress_line() {
  git -C "${REPO_DIR}" lfs ls-files --size -I='files/**/b*.txt' -X='' | awk '
    {
      total++
      s=$4; gsub(/[()]/,"",s)
      u=$5; gsub(/[()]/,"",u)
      m=(u=="B"?1:u=="KB"?1024:u=="MB"?1048576:u=="GB"?1073741824:u=="TB"?1099511627776:1)
      t+=s*m
      if($2=="*"){done++; d+=s*m}
    }
    END{
      pct=(total?100*done/total:0)
      bpct=(t?100*d/t:0)
      printf("bfiles=%d/%d (%.2f%%), bytes=%.2f/%.2f GiB (%.2f%%)",
             done,total,pct,d/1073741824,t/1073741824,bpct)
    }'
}

echo "[fetch] git lfs fetch --exclude='' (this can run overnight)"
git -C "${REPO_DIR}" lfs fetch --exclude='' &
FETCH_PID=$!

if [[ "${PROGRESS_EVERY}" =~ ^[0-9]+$ ]] && [[ "${PROGRESS_EVERY}" -gt 0 ]]; then
  NEXT=$((SECONDS + PROGRESS_EVERY))
  while kill -0 "${FETCH_PID}" 2>/dev/null; do
    sleep 1
    if [[ ${SECONDS} -lt ${NEXT} ]]; then
      continue
    fi
    NEXT=$((SECONDS + PROGRESS_EVERY))
    if LINE="$(progress_line 2>/dev/null)"; then
      echo "[progress] ${LINE}"
    fi
  done
fi
if ! wait "${FETCH_PID}"; then
  echo "[warning] Git LFS fetch was incomplete; checking canonical b-files for direct repair" >&2
fi

echo "[checkout] git lfs checkout"
git -C "${REPO_DIR}" lfs checkout || true

if [[ ${DIRECT_FALLBACK} -eq 1 ]]; then
  POINTERS="$(mktemp)"
  trap 'rm -f "${POINTERS}"' EXIT
  git -C "${REPO_DIR}" lfs ls-files -I='files/**/b*.txt' -X='' \
    | awk '$2=="-" && $3 ~ /\/b[0-9]{6}\.txt$/ {print $3}' > "${POINTERS}"
  COUNT="$(wc -l < "${POINTERS}")"
  if [[ ${COUNT} -gt 0 ]]; then
    command -v curl >/dev/null 2>&1 || { echo "curl not found" >&2; exit 1; }
    echo "[fallback] downloading ${COUNT} unavailable canonical b-files from oeis.org"
    export REPO_DIR
    if ! xargs -r -P "${JOBS}" -n 1 bash -c '
      rel=$1
      base=${rel##*/}
      digits=${base#b}; digits=${digits%.txt}
      dest="$REPO_DIR/$rel"; tmp="$dest.tmp"
      curl --fail --location --silent --show-error --retry 2 \
        "https://oeis.org/A${digits}/b${digits}.txt" -o "$tmp" && mv "$tmp" "$dest"
    ' _ < "${POINTERS}"; then
      echo "[warning] some direct b-file repairs failed; rerun to resume" >&2
    fi
  fi
fi

if LINE="$(progress_line 2>/dev/null)"; then
  echo "[progress] ${LINE}"
fi

echo "[done] All available LFS backing content checked out in ${REPO_DIR}/files"
