#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/libs/kma_aws_collect.py"
CONFIG_FILE="${SCRIPT_DIR}/config/aws_config.toml"
CONDA_BIN="/home/collect/appl/miniconda3/bin/conda"

usage() {
  cat <<'USAGE'
Usage:
  collect_kma_aws.sh [START_YYYYMMDD] [END_YYYYMMDD] [options]

Options:
  --stn-ids STN1,STN2   특정 지점만 수집
  --limit N             처음 N개 지점만 수집
  --show-sample         수집 후 샘플 출력

Examples:
  collect_kma_aws.sh                        # 어제 전체
  collect_kma_aws.sh 20260619               # 특정일
  collect_kma_aws.sh 20260601 20260619      # 기간
  collect_kma_aws.sh 20260619 --limit 5 --show-sample
USAGE
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

yesterday_ymd() { date -d 'yesterday' +%Y%m%d 2>/dev/null || date -v-1d +%Y%m%d; }
normalize_ymd()  { date -d "$1" +%Y%m%d 2>/dev/null || date -j -f "%Y%m%d" "$1" +%Y%m%d; }
add_days_ymd()   { date -d "$1 +$2 day" +%Y%m%d 2>/dev/null || date -j -f "%Y%m%d" -v+"$2"d "$1" +%Y%m%d; }

start_date="${1:-}"
if [[ -z "${start_date}" || "${start_date}" == --* ]]; then
  start_date="$(yesterday_ymd)"
else
  shift
fi

end_date="${1:-}"
if [[ -z "${end_date}" || "${end_date}" == --* ]]; then
  end_date="${start_date}"
else
  shift
fi

start_date="$(normalize_ymd "${start_date}")"
end_date="$(normalize_ymd "${end_date}")"

set +u
eval "$("${CONDA_BIN}" shell.bash hook)"
[[ -n "${CONDA_PREFIX:-}" ]] && conda deactivate || true
conda activate dataenv
set -u

cur="${start_date}"
while [[ "${cur}" < "${end_date}" || "${cur}" == "${end_date}" ]]; do
  python "${PY_SCRIPT}" --date "${cur}" --config "${CONFIG_FILE}" "$@"
  cur="$(add_days_ymd "${cur}" 1)"
done

set +u
conda deactivate || true
set -u
