#!/bin/bash
set -u
ROOT=/home/collect/collect_test
LOG=$ROOT/out/full_test.log
S=20260620; E=20260629
{
echo "START $(date '+%F %T')  window=$S..$E"
for spec in \
  "khoa/collect_khoa_obs.sh tidal" \
  "khoa/collect_khoa_obs.sh buoy" \
  "kma/collect_kma_obs.sh" \
  "nifs/collect_nifs_obs.sh"; do
  echo "==================== $spec  $(date '+%T') ===================="
  /bin/bash $ROOT/obs/$spec $S $E
  echo "-------------------- rc=$? --------------------"
done
echo "DONE $(date '+%F %T')"
} >> "$LOG" 2>&1
