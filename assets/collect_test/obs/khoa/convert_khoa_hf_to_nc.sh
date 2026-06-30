#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NC_PY="${SCRIPT_DIR}/libs/khoa_hf_to_nc.py"
NC_CFG="${SCRIPT_DIR}/config/khoa_hf_nc_config.toml"

resolve_conda_bin() {
  local candidates=(
    "${CONDA_EXE:-}"
    "/home/collect/appl/miniconda3/bin/conda"
    "/home/smsim/miniconda3/bin/conda"
  )
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

usage() {
  cat <<'USAGE'
Usage:
  convert_khoa_hf_to_nc.sh [YYYY] [--obs-codes HF_0039,HF_0040]

Options:
  YYYY            Target year (default: current year)
  --obs-codes     Comma-separated station codes (default: all in khoa_config.toml)

Examples:
  convert_khoa_hf_to_nc.sh 2024
  convert_khoa_hf_to_nc.sh 2024 --obs-codes HF_0039,HF_0040
  convert_khoa_hf_to_nc.sh
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

year="${1:-}"
if [[ -z "${year}" || "${year}" == --* ]]; then
  year="$(date +%Y)"
else
  shift
fi

if ! [[ "${year}" =~ ^[0-9]{4}$ ]]; then
  echo "[ERROR] Invalid year: ${year}" >&2
  exit 1
fi

if ! CONDA_BIN="$(resolve_conda_bin)"; then
  echo "[ERROR] conda not found. Set CONDA_EXE or install conda." >&2
  exit 1
fi

set +u
eval "$("${CONDA_BIN}" shell.bash hook)"
[[ -n "${CONDA_PREFIX:-}" ]] && conda deactivate || true
conda activate dataenv
set -u

echo "[INFO] Converting KHOA HF CSV -> NetCDF  year=${year}"
python "${NC_PY}" --year "${year}" --config "${NC_CFG}" "$@"

set +u
conda deactivate || true
set -u
