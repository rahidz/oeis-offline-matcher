#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-${ROOT}/runs/five-max-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
cd "$ROOT"
exec >> "$OUT/batch.log" 2>&1
export PYTHONUNBUFFERED=1

sequences=(
  '2,3,5,5,9,10,9,8,7,8,14,7,15,14,13,30,29,28,27,53'
  '1,2,3,4,6,7,8,9,9,10,11,13,14,14,18,19,19,19,19,20'
  '0,1,2,2,3,4,4,4,4,4,5,5,6,6,6,8,8,8,8,9'
  '1,1,4,3,24,12,3,140,56,504,48,1540,9240,180180,10010,131040,2880,342720,64260,8139600'
  '1,1,5,4,35,19,5,327,201,1895,193,6541,37831,825299,25481,503729,11851,1484003,300479,39553121'
)

echo "$(date -Is) START batch: five sequential --max searches, 3600s each"
echo "Output: $OUT"
failed=0
for i in "${!sequences[@]}"; do
  name="sequence-$((i + 1))"
  echo "$(date -Is) START $name: ${sequences[$i]}"
  status=0
  # Enforce a hard wall limit even if a search stage overruns its own budget.
  # Streaming text and completed-stage checkpoints survive a forced stop.
  timeout --signal=KILL 3600s \
    "$ROOT/scripts/oeis-start" --no-status --no-refresh-if-stale -- \
    oeis analyze "${sequences[$i]}" --max --time-cap 3600 \
    --checkpoint "$OUT/$name.checkpoint.json" \
    > "$OUT/$name.txt" 2>&1 || status=$?
  case "$status" in
    0) echo "$(date -Is) DONE $name" ;;
    124|137) echo "$(date -Is) TIME LIMIT $name (exit $status; partial results saved)" ;;
    *) echo "$(date -Is) FAILED $name (exit $status); continuing"; failed=1 ;;
  esac
done
echo "$(date -Is) COMPLETE batch (failures=$failed)"
exit "$failed"
