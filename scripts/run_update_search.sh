#!/usr/bin/env bash
# Bounded adversarial context-update search, not a benign-RSI risk estimate.
# Edit NEW-run models, roots, attempts, repetitions and caps in this block.
# The existing task allocation and two strategies are fixed by the study protocol.
# Resume uses saved configuration/source. No automatic restart, repair or retry.
set -euo pipefail

EXPERIMENT_SETTINGS=$(cat <<'JSON'
{
  "profile": "update-search",
  "protocol": "bounded-context-update-search-v1",
  "mode": "http",
  "strategies": ["plain", "hypothesis"],
  "seeds": [2026112401, 2026112402],
  "slots": 2,
  "evaluation": {"repeats": 5},
  "training": {
    "task_pack": "rsi-feasibility-v1",
    "scheduling": {"seed": 20261123, "dev_per_family": 1, "probe_per_family": 1, "final_per_family": 1},
    "agentdojo": {"suites": [
      {"suite": "banking", "partitions": {"dev": ["user_task_3"], "probe": ["user_task_13"], "heldout": ["user_task_15"]},
       "injection_task_ids": ["injection_task_5"], "attack_ids": ["role_spoofing_native"]},
      {"suite": "slack", "partitions": {"dev": ["user_task_7"], "probe": ["user_task_4"], "heldout": ["user_task_11"]},
       "injection_task_ids": ["injection_task_1"], "attack_ids": ["role_spoofing_native"]}
    ]}
  },
  "budget": {
    "max_steps": 32,
    "train_episodes": 36, "train_calls": 1152,
    "probe_episodes": 24, "probe_calls": 768,
    "test_episodes": 120, "test_calls": 3840,
    "editor_calls_per_slot": 1
  },
  "models": {
    "actor": {
      "base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key_env": "DEEPSEEK_API_KEY",
      "temperature": 0.0, "thinking_mode": "disabled", "timeout_seconds": 120.0,
      "max_prompt_bytes": 131072, "max_output_tokens": 4096, "max_total_tokens": 16000000
    },
    "editor": {
      "base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key_env": "DEEPSEEK_API_KEY",
      "temperature": 0.6, "thinking_mode": "disabled", "timeout_seconds": 120.0,
      "max_prompt_bytes": 65536, "max_output_tokens": 2048, "max_total_tokens": 65536
    },
    "judge": null
  },
  "execution": {"root_workers": 4, "max_in_flight": 4, "requests_per_minute": 120, "cooldown_seconds": 30}
}
JSON
)

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON=${RSI_PYTHON:-"$REPO_DIR/.venv/bin/python"}
ENV_FILE=${RSI_ENV_FILE:-"$REPO_DIR/.env"}
ACTION=${1:-prepare}
case "$ACTION" in
  prepare|control|run) CAMPAIGN=${2:-"$REPO_DIR/runs/current/update-search-${ACTION}-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"} ;;
  status|resume)
    if [[ $# -ne 2 ]]; then echo "Supply the frozen campaign path" >&2; exit 2; fi
    CAMPAIGN=$2 ;;
  *) echo "Usage: bash $0 {prepare|control|run|status|resume} [CAMPAIGN]" >&2; exit 2 ;;
esac
if [[ $# -gt 2 || ! -x "$PYTHON" ]]; then echo "Invalid arguments or Python path" >&2; exit 2; fi
export PYTHONDONTWRITEBYTECODE=1
cd "$REPO_DIR"
if [[ "$ACTION" == prepare || ( ( "$ACTION" == control || "$ACTION" == run ) && ! -e "$CAMPAIGN" ) ]]; then
  BUILD_ARGS=("$CAMPAIGN" --launcher "$SCRIPT_DIR/$(basename -- "${BASH_SOURCE[0]}")")
  if [[ "$ACTION" == control ]]; then BUILD_ARGS+=(--mode scripted); fi
  printf '%s\n' "$EXPERIMENT_SETTINGS" | "$PYTHON" "$SCRIPT_DIR/authorization_experiment_config.py" "${BUILD_ARGS[@]}"
fi
if [[ ! -f "$CAMPAIGN/campaign.json" ]]; then echo "No frozen campaign at $CAMPAIGN" >&2; exit 2; fi
CAMPAIGN=$(cd -- "$CAMPAIGN" && pwd)
export PYTHONPATH="$CAMPAIGN/execution-source/package" PYTHONSAFEPATH=1
"$PYTHON" "$CAMPAIGN/config-builder.py" "$CAMPAIGN" --verify
if [[ "$ACTION" == prepare ]]; then echo "Prepared with zero API calls: $CAMPAIGN"; exit 0; fi
if [[ "$ACTION" == status ]]; then "$PYTHON" "$CAMPAIGN/config-builder.py" "$CAMPAIGN" --status; exit 0; fi
"$PYTHON" - "$CAMPAIGN" "$ACTION" <<'PY'
import json
from pathlib import Path
import sys
p, action = Path(sys.argv[1]), sys.argv[2]
c = json.loads((p / 'config.json').read_text())
if c['profile'] != 'update-search':
    raise SystemExit('Wrong experiment profile')
if action == 'control' and c['mode'] != 'scripted':
    raise SystemExit('control refuses a paid HTTP plan')
if action == 'resume' and not (p / 'run/manifest.json').is_file():
    raise SystemExit('No started experiment to resume')
if action != 'resume' and (p / 'run').exists():
    raise SystemExit('Existing attempt; inspect and explicitly resume')
PY
RUN_ARGS=(--config "$CAMPAIGN/config.json" --plan "$CAMPAIGN/plan.json" --output "$CAMPAIGN/run")
if [[ "$ACTION" == resume ]]; then RUN_ARGS+=(--resume); fi
"$PYTHON" -u "$CAMPAIGN/config-builder.py" "$CAMPAIGN" --execute --env-file "$ENV_FILE" --cli-args "${RUN_ARGS[@]}" 2>&1 |
  tee "$CAMPAIGN/launch-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S).log"
"$PYTHON" -m rsi_lab.cli inspect --output "$CAMPAIGN/run"
