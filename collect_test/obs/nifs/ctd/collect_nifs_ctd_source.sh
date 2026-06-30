#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SCRIPT="${SCRIPT_DIR}/collect_nifs_ctd.sh"

exec bash "${MAIN_SCRIPT}" --crawl-only "$@"
