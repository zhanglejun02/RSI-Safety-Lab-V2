#!/usr/bin/env bash
# Shared immutable launch/resume mechanics; editable allocations live in callers.
set -euo pipefail

experiment_execute() {
  local repo=$1 action=$2 campaign=$3 python=$4 env_file=$5
  cd "$repo"
  export PYTHONPATH="$campaign/execution-source/package" PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1
  "$python" "$campaign/config-builder.py" "$campaign" --verify
  if [[ "$action" == prepare ]]; then
    echo "Prepared with zero API calls: $campaign"
    return
  fi
  if [[ "$action" == status ]]; then
    "$python" "$campaign/config-builder.py" "$campaign" --status
    return
  fi
  "$python" - "$campaign" "$action" <<'PY'
import json
from pathlib import Path
import sys
p, action = Path(sys.argv[1]), sys.argv[2]
c = json.loads((p / 'config.json').read_text())
if action == 'control' and c['mode'] != 'scripted':
    raise SystemExit('control refuses an HTTP plan; use a new control campaign')
if action == 'resume' and not (p / 'run/manifest.json').is_file():
    raise SystemExit('No started experiment to resume')
if action != 'resume' and (p / 'run').exists():
    raise SystemExit('Existing attempt; inspect it and explicitly resume, never automatically retry')
PY
  local run_args=(--config "$campaign/config.json" --plan "$campaign/plan.json" --output "$campaign/run")
  if [[ "$action" == resume ]]; then run_args+=(--resume); fi
  "$python" -u "$campaign/config-builder.py" "$campaign" --execute --env-file "$env_file" --cli-args "${run_args[@]}" 2>&1 |
    tee "$campaign/launch-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S).log"
  "$python" -m rsi_lab.cli inspect --output "$campaign/run"
}

experiment_campaign() {
  local action=${1:-prepare} repo python env_file campaign
  repo=$(cd -- "$SCRIPT_DIR/.." && pwd)
  python=${RSI_PYTHON:-"$repo/.venv/bin/python"}
  env_file=${RSI_ENV_FILE:-"$repo/.env"}
  case "$action" in
    prepare|control|run)
      campaign=${2:-"$repo/runs/current/${EXPERIMENT_PREFIX}-${action}-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"} ;;
    status|resume)
      if [[ $# -ne 2 ]]; then echo "Usage: bash $0 $action CAMPAIGN" >&2; return 2; fi
      campaign=$2 ;;
    *) echo "Usage: bash $0 {prepare|control|run|status|resume} [CAMPAIGN]" >&2; return 2 ;;
  esac
  if [[ $# -gt 2 ]]; then echo "Too many arguments" >&2; return 2; fi
  if [[ ! -x "$python" ]]; then echo "Python not found: $python" >&2; return 2; fi
  export PYTHONDONTWRITEBYTECODE=1
  cd "$repo"
  if [[ "$action" == prepare || ( ( "$action" == control || "$action" == run ) && ! -e "$campaign" ) ]]; then
    local build_args=("$campaign" --launcher "$EXPERIMENT_LAUNCHER" --runtime "$SCRIPT_DIR/experiment_campaign.sh")
    if [[ "$action" == control ]]; then build_args+=(--mode scripted); fi
    printf '%s\n' "$EXPERIMENT_SETTINGS" | "$python" "$SCRIPT_DIR/authorization_experiment_config.py" "${build_args[@]}"
  fi
  if [[ ! -f "$campaign/campaign.json" ]]; then echo "No frozen authorization campaign in $campaign; prepare a new campaign." >&2; return 2; fi
  campaign=$(cd -- "$campaign" && pwd)
  echo "Campaign: $campaign"
  export PYTHONPATH="$campaign/execution-source/package" PYTHONSAFEPATH=1
  "$python" "$campaign/config-builder.py" "$campaign" --verify
  if [[ -f "$campaign/screen-runtime.sh" ]]; then
    # The historical artifact name is retained by the shared campaign builder.
    # Newly prepared campaigns freeze this helper, too; resume never uses edits.
    bash "$campaign/screen-runtime.sh" "$repo" "$action" "$campaign" "$python" "$env_file"
  else
    # Pre-helper campaigns still execute their original builder/config/package.
    experiment_execute "$repo" "$action" "$campaign" "$python" "$env_file"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then experiment_execute "$@"; fi
