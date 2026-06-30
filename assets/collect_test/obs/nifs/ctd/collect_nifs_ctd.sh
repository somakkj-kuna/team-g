#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERGE_PY_SCRIPT="${SCRIPT_DIR}/libs/nifs_tools.py"
CRAWL_PY_SCRIPT="${SCRIPT_DIR}/../libs/kodc_web_crawl/line_data_client.py"
DEFAULT_CONFIG_FILE="${SCRIPT_DIR}/config/config.toml"
CONDA_BIN="/home/collect/appl/miniconda3/bin/conda"

usage() {
  cat <<'USAGE'
Usage:
  collect_nifs_ctd.sh [START_YYYY] [END_YYYY] [--config PATH] [--output-dir DIR]
  collect_nifs_ctd.sh [YYYY] [--crawl-only | --merge-only]

Examples:
  collect_nifs_ctd.sh
  collect_nifs_ctd.sh 2025
  collect_nifs_ctd.sh 2017 2025
  collect_nifs_ctd.sh 2025 --output-dir "/data/DATA/OBS/nifs/merge/ctd"
  collect_nifs_ctd.sh 2025 --crawl-only
  collect_nifs_ctd.sh 2025 --merge-only
  collect_nifs_ctd.sh 2025 --output /tmp/ctd_2025.csv --output-dir /tmp/nifs_ctd_merge

Notes:
  - no year -> previous calendar year
  - default run = crawl source CSV from KODC first, then merge it
  - --output is only allowed for a single year
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

previous_calendar_year() {
  local value=""

  if value="$(date +%Y 2>/dev/null)"; then
    printf "%04d\n" "$((10#${value} - 1))"
    return 0
  fi

  value="$(date -j +%Y)"
  printf "%04d\n" "$((10#${value} - 1))"
}

config_file="${DEFAULT_CONFIG_FILE}"
merge_output_dir=""
crawl_output=""
merge_source_glob=""
page_size=""
request_interval_sec=""
timeout=""
log_level=""
crawl_only=0
merge_only=0
positional_years=()

while [[ $# -gt 0 ]]; do
  case "${1}" in
    -h|--help)
      usage
      exit 0
      ;;
    --config)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --config requires a value." >&2
        exit 1
      fi
      config_file="${2}"
      shift 2
      ;;
    --output-dir)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --output-dir requires a value." >&2
        exit 1
      fi
      merge_output_dir="${2}"
      shift 2
      ;;
    --output|--source-output)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] ${1} requires a value." >&2
        exit 1
      fi
      crawl_output="${2}"
      shift 2
      ;;
    --source-glob)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --source-glob requires a value." >&2
        exit 1
      fi
      merge_source_glob="${2}"
      shift 2
      ;;
    --page-size)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --page-size requires a value." >&2
        exit 1
      fi
      page_size="${2}"
      shift 2
      ;;
    --request-interval-sec)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --request-interval-sec requires a value." >&2
        exit 1
      fi
      request_interval_sec="${2}"
      shift 2
      ;;
    --timeout)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --timeout requires a value." >&2
        exit 1
      fi
      timeout="${2}"
      shift 2
      ;;
    --log-level)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --log-level requires a value." >&2
        exit 1
      fi
      log_level="${2}"
      shift 2
      ;;
    --crawl-only)
      crawl_only=1
      shift
      ;;
    --merge-only)
      merge_only=1
      shift
      ;;
    --*)
      echo "[ERROR] Unknown option: ${1}" >&2
      usage
      exit 1
      ;;
    *)
      positional_years+=("${1}")
      shift
      ;;
  esac
done

if (( crawl_only == 1 && merge_only == 1 )); then
  echo "[ERROR] --crawl-only and --merge-only cannot be used together." >&2
  exit 1
fi

if (( ${#positional_years[@]} == 0 )); then
  start_year="$(previous_calendar_year)"
  end_year="${start_year}"
elif (( ${#positional_years[@]} == 1 )); then
  start_year="${positional_years[0]}"
  end_year="${start_year}"
elif (( ${#positional_years[@]} == 2 )); then
  start_year="${positional_years[0]}"
  end_year="${positional_years[1]}"
else
  echo "[ERROR] Too many positional arguments. Use at most START_YYYY END_YYYY." >&2
  usage
  exit 1
fi

if [[ ! "${start_year}" =~ ^[0-9]{4}$ ]]; then
  echo "[ERROR] Invalid start year: ${start_year}" >&2
  exit 1
fi
if [[ ! "${end_year}" =~ ^[0-9]{4}$ ]]; then
  echo "[ERROR] Invalid end year: ${end_year}" >&2
  exit 1
fi
if (( 10#${start_year} > 10#${end_year} )); then
  echo "[ERROR] start year must be <= end year: ${start_year} > ${end_year}" >&2
  exit 1
fi
if [[ -n "${crawl_output}" ]] && (( 10#${start_year} < 10#${end_year} )); then
  echo "[ERROR] --output is only allowed with a single year." >&2
  exit 1
fi

run_python_script() {
  local script_path="$1"
  shift
  python "${script_path}" "$@"
}

set +u
eval "$("${CONDA_BIN}" shell.bash hook)"
if [[ -n "${CONDA_PREFIX:-}" ]]; then
  conda deactivate || true
fi
conda activate dataenv
set -u

current_year="${start_year}"
while (( 10#${current_year} <= 10#${end_year} )); do
  echo "=============================================================================="
  echo "   ∴ Processing year :: ${current_year}"
  echo "=============================================================================="

  if (( merge_only == 0 )); then
    crawl_cmd=("${current_year}" "--config" "${config_file}")
    if [[ -n "${crawl_output}" ]]; then
      crawl_cmd+=("--output" "${crawl_output}")
    fi
    if [[ -n "${page_size}" ]]; then
      crawl_cmd+=("--page-size" "${page_size}")
    fi
    if [[ -n "${request_interval_sec}" ]]; then
      crawl_cmd+=("--request-interval-sec" "${request_interval_sec}")
    fi
    if [[ -n "${timeout}" ]]; then
      crawl_cmd+=("--timeout" "${timeout}")
    fi
    if [[ -n "${log_level}" ]]; then
      crawl_cmd+=("--log-level" "${log_level}")
    fi

    echo "   ∴ Step 1 :: crawl source CSV"
    run_python_script "${CRAWL_PY_SCRIPT}" "${crawl_cmd[@]}"
  fi

  if (( crawl_only == 0 )); then
    merge_cmd=("--config" "${config_file}" "--year" "${current_year}")
    if [[ -n "${merge_output_dir}" ]]; then
      merge_cmd+=("--output-dir" "${merge_output_dir}")
    fi
    if [[ -n "${crawl_output}" ]]; then
      merge_cmd+=("--source-glob" "${crawl_output}")
    elif [[ -n "${merge_source_glob}" ]]; then
      merge_cmd+=("--source-glob" "${merge_source_glob}")
    fi

    echo "   ∴ Step 2 :: merge yearly CSV"
    run_python_script "${MERGE_PY_SCRIPT}" "${merge_cmd[@]}"
  fi

  current_year="$(printf '%04d' "$((10#${current_year} + 1))")"
done

set +u
conda deactivate || true
set -u
