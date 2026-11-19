#!/usr/bin/env bash
# Real judge on versioned authored controls; not independent human calibration.
# Edit settings for a NEW campaign. budget_cny:null removes only the money ceiling.
set -euo pipefail
SETTINGS=$(cat <<'JSON'
{
  "repeats": 3,
  "requests_per_minute": 60,
  "judge": {
    "base_url": "https://api.moonshot.cn/v1",
    "model": "kimi-k2.6",
    "api_key_env": "MOONSHOT_API_KEY",
    "temperature": 0.6,
    "thinking_mode": "disabled",
    "timeout_seconds": 120.0,
    "max_prompt_bytes": 32768,
    "max_output_tokens": 2048,
    "max_calls": 192,
    "max_total_tokens": 600000
  },
  "budget_cny": null,
  "previous_spend_cny": 46.380943,
  "cost_buffer_cny": 0.1,
  "rates_checked_on": "2026-11-18",
  "rates_cny_per_million": {
    "input": 6.5,
    "output": 27.0
  },
  "pricing_source": "https://platform.kimi.com/docs/pricing/chat",
  "task_pack": "privacy-drafts-v3"
}
JSON
)
SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$(basename -- "${BASH_SOURCE[0]}")"
REPO_DIR=$(cd -- "$(dirname -- "$SCRIPT")/.." && pwd)
PYTHON=${RSI_PYTHON:-"$REPO_DIR/.venv/bin/python"}
ENV_FILE=${RSI_ENV_FILE:-"$REPO_DIR/.env"}
cd "$REPO_DIR"
ACTION=${1:-plan}
if [[ "$ACTION" == resume || "$ACTION" == inspect ]]; then
  if [[ $# -ne 2 ]]; then echo "Usage: bash $0 $ACTION CAMPAIGN" >&2; exit 2; fi
fi
if [[ $# -gt 2 ]]; then echo "Too many arguments" >&2; exit 2; fi
CAMPAIGN=${2:-"$REPO_DIR/runs/current/authorization-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"}
case "$ACTION" in plan|run|resume|inspect) ;; *) echo "Use plan, run, resume or inspect" >&2; exit 2;; esac
if [[ "$ACTION" == plan || ( "$ACTION" == run && ! -d "$CAMPAIGN" ) ]]; then
  printf '%s\n' "$SETTINGS" | "$PYTHON" scripts/authorization_checks.py plan "$CAMPAIGN"
  cp -- "$SCRIPT" "$CAMPAIGN/launch.sh"
  cp -- scripts/authorization_checks.py "$CAMPAIGN/driver.py"
  cp -- scripts/summarize_natural_experiment.py "$CAMPAIGN/cost_reader.py"
fi
if [[ "$ACTION" == plan ]]; then exit 0; fi
if [[ ! -f "$CAMPAIGN/driver.py" ]]; then echo "No frozen authorization plan" >&2; exit 2; fi
"$PYTHON" -u "$CAMPAIGN/driver.py" "$ACTION" "$CAMPAIGN" --env-file "$ENV_FILE" 2>&1 |
  tee "$CAMPAIGN/launch-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S).log"
