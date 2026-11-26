#!/usr/bin/env bash
# Read-only prototype; edit input paths here. No actor, editor or judge is run.
set -euo pipefail
STUDY="runs/current/agentdojo-rsi-20261126-v1/run"
CONFIRMATION="runs/current/agentdojo-confirm-20261126-v1/run"
OUTPUT=${1:-"output/rsi-rating-evidence-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON=${RSI_PYTHON:-"$REPO_DIR/.venv/bin/python"}
if [[ $# -gt 1 ]]; then echo "Usage: bash $0 [NEW_OUTPUT_DIRECTORY]" >&2; exit 2; fi
cd "$REPO_DIR"
export PYTHONDONTWRITEBYTECODE=1
"$PYTHON" "$SCRIPT_DIR/summarize_rating_evidence.py" \
  --study "$STUDY" --confirmation "$CONFIRMATION" --output "$OUTPUT"
