#!/usr/bin/env bash
# Re-evaluate all versions from a completed confirmation on another risk package.
# Edit NEW-run settings here; resume uses the frozen settings and package.
# No new optimization, task selection, review decisions, or automatic retries.
set -euo pipefail

EXPERIMENT_SETTINGS=$(cat <<'JSON'
{
  "profile": "update-confirmation",
  "protocol": "saved-update-confirmation-v1",
  "source_run": "runs/current/agentdojo-confirm-20261126-v1/run",
  "replication_tasks": [],
  "blocks": 5,
  "order_seed": 2026112702,
  "training": {
    "task_pack": "agentharm-native-v1",
    "data_dir": "runs/datasets/agentharm",
    "partitions": {
      "dev": [],
      "probe": [],
      "heldout": ["9-1", "28-1", "50-1"]
    }
  },
  "review": null,
  "criteria": {"bootstrap_samples": 5000, "family_alpha": 0.05},
  "budget": {
    "max_steps": 24,
    "probe_episodes": 0,
    "probe_calls": 0,
    "test_episodes": 42,
    "test_calls": 1008
  },
  "models": {
    "actor": {
      "base_url": "https://api.deepseek.com",
      "model": "deepseek-flash",
      "api_key_env": "DEEPSEEK_API_KEY",
      "temperature": 0.0,
      "thinking_mode": "disabled",
      "timeout_seconds": 120.0,
      "max_prompt_bytes": 131072,
      "max_output_tokens": 2048,
      "max_total_tokens": 8000000
    },
    "editor": null,
    "judge": null
  },
  "execution": {
    "root_workers": 2,
    "max_in_flight": 2,
    "requests_per_minute": 120,
    "cooldown_seconds": 30
  }
}
JSON
)

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPERIMENT_PREFIX=frozen-risk-suite
EXPERIMENT_LAUNCHER="$SCRIPT_DIR/$(basename -- "${BASH_SOURCE[0]}")"
source "$SCRIPT_DIR/experiment_campaign.sh"
experiment_campaign "$@"
