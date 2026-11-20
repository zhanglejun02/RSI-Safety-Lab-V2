#!/usr/bin/env bash
# Shared launcher mechanics. Each public Bash script owns its editable settings.
set -euo pipefail

screen_execute() {
  local repo=$1 action=$2 campaign=$3 profile=$4 python=$5 env_file=$6 method=${7:-frozen}
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
  "$python" - "$campaign" "$action" "$profile" "$method" <<'PY'
import json
from pathlib import Path
import sys
p, action, profile, method = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
c = json.loads((p / 'config.json').read_text())
if c['profile'] != profile or c['methods'] != [method] or c['arms'] != ['native_only']:
    raise SystemExit('This launcher only executes its declared method and native_only profile')
if action == 'control' and c['mode'] != 'scripted':
    raise SystemExit('control refuses an HTTP plan')
if action == 'screen' and (c['mode'] != 'http' or method != 'frozen'):
    raise SystemExit('screen requires a Frozen HTTP plan')
if action == 'resume' and not (p / 'run/manifest.json').is_file():
    raise SystemExit('No started experiment to resume')
if action != 'resume' and (p / 'run').exists():
    raise SystemExit('Existing attempt; inspect and explicitly resume, never automatically retry')
PY
  local run_args=(--config "$campaign/config.json" --plan "$campaign/plan.json" --output "$campaign/run")
  if [[ "$action" == resume ]]; then run_args+=(--resume); fi
  "$python" -u "$campaign/config-builder.py" "$campaign" --execute --env-file "$env_file" --cli-args "${run_args[@]}" 2>&1 |
    tee "$campaign/launch-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S).log"
  "$python" -m rsi_lab.cli inspect --output "$campaign/run"
}

screen_campaign() {
  local action=${1:-prepare} actor=${3:-deepseek} strategy=${4:-baseline}
  local repo python env_file campaign
  local method=${SCREEN_METHOD:-frozen}
  if [[ "${SCREEN_FIXED_SETTINGS:-0}" == 1 && ( $# -gt 2 || "$action" == screen ) ]]; then
    echo "Usage: bash $0 {prepare|control|run|status|resume} [CAMPAIGN]; edit parameters in the script" >&2
    return 2
  fi
  repo=$(cd -- "$SCRIPT_DIR/.." && pwd)
  python=${RSI_PYTHON:-"$repo/.venv/bin/python"}
  env_file=${RSI_ENV_FILE:-"$repo/.env"}
  case "$action" in
    prepare|control|run|screen)
      campaign=${2:-"$repo/runs/current/${SCREEN_PREFIX}-${actor}-${strategy}-${action}-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"} ;;
    status|resume)
      if [[ $# -ne 2 ]]; then echo "Usage: bash $0 $action CAMPAIGN (frozen actor)" >&2; return 2; fi
      campaign=$2 ;;
    *) echo "Usage: bash $0 {prepare|control|run|screen|status|resume} [CAMPAIGN] [deepseek|kimi] [baseline|structured]" >&2; return 2 ;;
  esac
  if [[ $# -gt 4 || ! "$actor" =~ ^(deepseek|kimi)$ || ! "$strategy" =~ ^(baseline|structured)$ ]]; then
    echo "Invalid actor, strategy or argument count" >&2; return 2
  fi
  if [[ $# -ge 3 && -e "$campaign" ]]; then echo "Existing campaign uses its frozen actor and strategy; omit overrides" >&2; return 2; fi
  if [[ ! -x "$python" ]]; then echo "Python not found: $python" >&2; return 2; fi
  export PYTHONDONTWRITEBYTECODE=1
  cd "$repo"
  if [[ "$action" == prepare || ( ( "$action" == control || "$action" == run || "$action" == screen ) && ! -e "$campaign" ) ]]; then
    local build_args=("$campaign" --launcher "$SCREEN_LAUNCHER" --runtime "$SCRIPT_DIR/screen_campaign.sh" --actor "$actor" --strategy "$strategy")
    if [[ "$action" == control ]]; then build_args+=(--mode scripted); fi
    printf '%s\n' "$EXPERIMENT_SETTINGS" | "$python" "$SCRIPT_DIR/$SCREEN_BUILDER" "${build_args[@]}"
  fi
  if [[ ! -f "$campaign/campaign.json" ]]; then echo "No frozen screen campaign in $campaign" >&2; return 2; fi
  campaign=$(cd -- "$campaign" && pwd)
  echo "Campaign: $campaign"
  export PYTHONPATH="$campaign/execution-source/package" PYTHONSAFEPATH=1
  "$python" "$campaign/config-builder.py" "$campaign" --verify
  # Older archived runtimes only know Frozen; validate before handing them control.
  "$python" - "$campaign/config.json" "$SCREEN_PROFILE" "$method" <<'PY'
import json
from pathlib import Path
import sys
c = json.loads(Path(sys.argv[1]).read_text())
if (c['profile'], c['methods'], c['arms']) != (sys.argv[2], [sys.argv[3]], ['native_only']):
    raise SystemExit('Campaign does not match this launcher method/profile')
PY
  if [[ -f "$campaign/screen-runtime.sh" ]]; then
    # The archived runtime was just checked with the archived verifier.
    bash "$campaign/screen-runtime.sh" "$repo" "$action" "$campaign" "$SCREEN_PROFILE" "$python" "$env_file" "$method"
  else
    # Old campaigns predate the shared shell helper; their config/source stay frozen.
    screen_execute "$repo" "$action" "$campaign" "$SCREEN_PROFILE" "$python" "$env_file" "$method"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then screen_execute "$@"; fi
