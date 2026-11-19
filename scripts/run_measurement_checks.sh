#!/usr/bin/env bash
# Measurement diagnostics, not the multi-method safety comparison.
# Edit this block for a NEW campaign. Resume uses the saved settings.
# budget_cny: null disables only the monetary ceiling, not call/token budgets.
set -euo pipefail
SETTINGS=$(cat <<'JSON'
{
  "source": "runs/vendor/SEABench",
  "seed": 20261118,
  "execution_repeats": 3,
  "judgment_repeats": 3,
  "check_openevolve": true,
  "max_steps": 6,
  "actor_context": {"max_bytes": 16384, "tool_page_chars": 6000, "keep_recent_messages": 3, "final_response_steps": 2},
  "final_text_steps": 2,
  "models": {
    "actor": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key_env": "DEEPSEEK_API_KEY", "temperature": 0.0, "thinking_mode": "disabled", "timeout_seconds": 120.0, "max_prompt_bytes": 24576, "max_output_tokens": 768, "max_total_tokens": 120000},
    "editor": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key_env": "DEEPSEEK_API_KEY", "temperature": 0.6, "thinking_mode": "disabled", "timeout_seconds": 120.0, "max_prompt_bytes": 65536, "max_output_tokens": 8192, "max_total_tokens": 120000},
    "judge": {"base_url": "https://api.moonshot.cn/v1", "model": "kimi-k2.6", "api_key_env": "MOONSHOT_API_KEY", "temperature": 0.6, "thinking_mode": "disabled", "timeout_seconds": 120.0, "max_prompt_bytes": 16384, "max_output_tokens": 512, "max_total_tokens": 30000}
  },
  "rejudge_token_cap": 90000,
  "root_workers": 2,
  "requests_per_minute": 30,
  "budget_cny": null,
  "previous_spend_cny": 4.269024,
  "cost_buffer_cny": 0.1,
  "rates_checked_on": "2026-11-18",
  "rates_cny_per_million": {"actor": {"input": 2, "output": 8}, "editor": {"input": 2, "output": 8}, "judge": {"input": 6.5, "output": 27}},
  "pricing_sources": ["https://api-docs.deepseek.com/zh-cn/quick_start/pricing/", "https://platform.kimi.com/docs/pricing/chat"]
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
CAMPAIGN=${2:-"$REPO_DIR/runs/current/measurement-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"}
case "$ACTION" in plan|run|resume|inspect) ;; *) echo "Use plan, run, resume or inspect" >&2; exit 2;; esac
if [[ "$ACTION" == plan || ( "$ACTION" == run && ! -d "$CAMPAIGN" ) ]]; then
  printf '%s\n' "$SETTINGS" | "$PYTHON" scripts/measurement_checks.py plan "$CAMPAIGN"
  cp -- "$SCRIPT" "$CAMPAIGN/launch.sh"
  cp -- scripts/measurement_checks.py "$CAMPAIGN/driver.py"
  cp -- scripts/summarize_natural_experiment.py "$CAMPAIGN/cost_reader.py"
fi
if [[ "$ACTION" == plan ]]; then exit 0; fi
if [[ ! -f "$CAMPAIGN/driver.py" ]]; then echo "No frozen measurement plan" >&2; exit 2; fi
"$PYTHON" -u "$CAMPAIGN/driver.py" "$ACTION" "$CAMPAIGN" --env-file "$ENV_FILE" 2>&1 |
  tee "$CAMPAIGN/launch-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S).log"
