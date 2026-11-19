#!/usr/bin/env bash
# Preview: bash scripts/archive_experiments.sh
# Archive: bash scripts/archive_experiments.sh archive
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
RUNS_DIR="${REPO_ROOT}/runs"
EXPORTS_DIR="${REPO_ROOT}/exports"
KEEP=(archive current vendor datasets)

exec "$PYTHON" "${REPO_ROOT}/scripts/archive_experiments.py" \
  "${1:-plan}" --runs "$RUNS_DIR" --exports "$EXPORTS_DIR" --keep "${KEEP[@]}"
