#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIDAL_PY="${SCRIPT_DIR}/libs/khoa_tidal_collect.py"
BUOY_PY="${SCRIPT_DIR}/libs/khoa_buoy_collect.py"
HF_PY="${SCRIPT_DIR}/libs/khoa_hf_collect.py"
COMMON_CFG="${SCRIPT_DIR}/config/khoa_config.toml"

resolve_conda_bin() {
  local candidates=(
    "${CONDA_EXE:-}"
    "/home/collect/appl/miniconda3/bin/conda"
    "/home/smsim/miniconda3/bin/conda"
  )
  local candidate=""
  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      printf "%s\n" "${candidate}"
      return 0
    fi
  done
  if command -v conda >/dev/null 2>&1; then
    command -v conda
    return 0
  fi
  return 1
}

if ! CONDA_BIN="$(resolve_conda_bin)"; then
  echo "[ERROR] conda executable not found. Set CONDA_EXE or install conda in a known path." >&2
  exit 1
fi

usage() {
  cat <<'USAGE'
Usage:
  collect_khoa_obs.sh [tidal|buoy|hf] [START_YYYYMMDD] [END_YYYYMMDD] [--show-sample] [--limit N] [--obs-codes CODE1,CODE2]

Notes:
  - fetches data and appends to monthly CSV in one run
  - default mode is tidal
  - default date is yesterday if START_YYYYMMDD is omitted
  - if END_YYYYMMDD is omitted, only START_YYYYMMDD is collected

Examples:
  collect_khoa_obs.sh
  collect_khoa_obs.sh tidal 20240809 --show-sample --limit 3
  collect_khoa_obs.sh tidal 20240809 20240811
  collect_khoa_obs.sh buoy 20240809 --obs-codes TW_0089,KG_0021
  collect_khoa_obs.sh hf 20240809 --obs-codes HF_0039,HF_0040
  collect_khoa_obs.sh 20240809 --show-sample
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

mode="tidal"
if [[ "${1:-}" == "tidal" || "${1:-}" == "buoy" || "${1:-}" == "hf" || "${1:-}" == "HF" ]]; then
  mode="${1}"
  shift
fi
mode="$(printf "%s" "${mode}" | tr '[:upper:]' '[:lower:]')"

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
  if [[ "${mode}" == "buoy" ]]; then
    python "${BUOY_PY}" --date "${current_date}" --config "${COMMON_CFG}" "$@"
  elif [[ "${mode}" == "hf" ]]; then
    python "${HF_PY}" --date "${current_date}" --config "${COMMON_CFG}" "$@"
  else
    python "${TIDAL_PY}" --date "${current_date}" --config "${COMMON_CFG}" "$@"
  fi
  current_date="$(add_days_ymd "${current_date}" 1)"
done

set +u
conda deactivate || true
set -u
