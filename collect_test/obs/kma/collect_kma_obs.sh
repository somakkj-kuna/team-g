#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/libs/kma_collect.py"
CONFIG_FILE="${SCRIPT_DIR}/config/kma_config.toml"
CONDA_BIN="/home/collect/appl/miniconda3/bin/conda"

usage() {
  cat <<'USAGE'
Usage:
  collect_kma_obs.sh [START_YYYYMMDD] [END_YYYYMMDD] [--show-sample] [--limit N] [--obs-codes CODE1,CODE2]

Examples:
  collect_kma_obs.sh
  collect_kma_obs.sh 20260315 --show-sample --limit 5
  collect_kma_obs.sh 20260315 20260321
  collect_kma_obs.sh 20260315 --obs-codes 22101,22102
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

normalize_ymd() {
  local value="$1"
  local normalized=""

  if normalized="$(date -d "${value}" +%Y%m%d 2>/dev/null)"; then
    printf "%s\n" "${normalized}"
    return 0
  fi
  if normalized="$(date -j -f "%Y%m%d" "${value}" +%Y%m%d 2>/dev/null)"; then
    printf "%s\n" "${normalized}"
    return 0
  fi
  if normalized="$(date -j -f "%Y-%m-%d" "${value}" +%Y%m%d 2>/dev/null)"; then
    printf "%s\n" "${normalized}"
    return 0
  fi

  return 1
}

yesterday_ymd() {
  local value=""

  if value="$(date -d 'yesterday' +%Y%m%d 2>/dev/null)"; then
    printf "%s\n" "${value}"
    return 0
  fi
  date -v-1d +%Y%m%d
}

add_days_ymd() {
  local value="$1"
  local days="$2"
  local adjusted=""

  if adjusted="$(date -d "${value} +${days} day" +%Y%m%d 2>/dev/null)"; then
    printf "%s\n" "${adjusted}"
    return 0
  fi
  date -j -f "%Y%m%d" -v+"${days}"d "${value}" +%Y%m%d
}

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

raw_start_date="${start_date}"
if ! start_date="$(normalize_ymd "${raw_start_date}")"; then
  echo "[ERROR] Invalid start date: ${raw_start_date}" >&2
  exit 1
fi
raw_end_date="${end_date}"
if ! end_date="$(normalize_ymd "${raw_end_date}")"; then
  echo "[ERROR] Invalid end date: ${raw_end_date}" >&2
  exit 1
fi
if [[ "${start_date}" > "${end_date}" ]]; then
  echo "[ERROR] start date must be earlier than or equal to end date: ${start_date} > ${end_date}" >&2
  exit 1
fi

set +u
eval "$("${CONDA_BIN}" shell.bash hook)"
if [[ -n "${CONDA_PREFIX:-}" ]]; then
  conda deactivate || true
fi
conda activate dataenv
set -u

current_date="${start_date}"
while [[ "${current_date}" < "${end_date}" || "${current_date}" == "${end_date}" ]]; do
  python "${PY_SCRIPT}" --date "${current_date}" --config "${CONFIG_FILE}" "$@"
  current_date="$(add_days_ymd "${current_date}" 1)"
done

set +u
conda deactivate || true
set -u
