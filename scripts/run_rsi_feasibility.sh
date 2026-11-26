#!/usr/bin/env bash
# Fixed GEPA + full-public-validation feasibility experiment; not a method ranking.
# Edit all NEW-run settings here. Resume always uses archived settings/source.
# 4 development / 8 probe / 8 final cases; two roots per arm, two update slots.
# Three independent final executions per case and distinct candidate source.
# No LLM judge: risk is a declared environment effect, not answer interpretation.
# No manual candidate repair, adaptive task replacement, or automatic retries.
set -euo pipefail

EXPERIMENT_SETTINGS=$(cat <<'JSON'
{
  "methods": [
    "gepa"
  ],
  "arms": [
    "native_only",
    "behavior_review"
  ],
  "seeds": [
    2026112301,
    2026112302
  ],
  "slots": 2,
  "evaluation": {
    "audit_candidates": true,
    "repeats": 3
  },
  "training": {
    "task_pack": "rsi-feasibility-v1",
    "scheduling": {
      "seed": 20261123,
      "dev_per_family": 1,
      "probe_per_family": 1,
      "final_per_family": 1
    },
    "agentdojo": {
      "suites": [
        {
          "suite": "banking",
          "partitions": {
            "dev": [
              "user_task_3"
            ],
            "probe": [
              "user_task_13"
            ],
            "heldout": [
              "user_task_15"
            ]
          },
          "injection_task_ids": [
            "injection_task_5"
          ],
          "attack_ids": [
            "role_spoofing_native"
          ]
        },
        {
          "suite": "slack",
          "partitions": {
            "dev": [
              "user_task_7"
            ],
            "probe": [
              "user_task_4"
            ],
            "heldout": [
              "user_task_11"
            ]
          },
          "injection_task_ids": [
            "injection_task_1"
          ],
          "attack_ids": [
            "role_spoofing_native"
          ]
        }
      ]
    }
  },
  "review": {
    "protocol": "rsi-review-v1",
    "module": "public-full-validation-v1",
    "module_version": 1,
    "scope": "deployed_policy",
    "rollback": "candidate_snapshot_not_committed",
    "parameters": {}
  },
  "budget": {
    "max_steps": 32,
    "train_episodes": 256,
    "train_calls": 8192,
    "probe_episodes": 64,
    "probe_calls": 2048,
    "test_episodes": 144,
    "test_calls": 4608,
    "editor_calls_per_slot": 6,
    "judge_calls": 1
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
      "max_output_tokens": 4096,
      "max_total_tokens": 16000000
    },
    "editor": {
      "base_url": "https://api.deepseek.com",
      "model": "deepseek-flash",
      "api_key_env": "DEEPSEEK_API_KEY",
      "temperature": 0.6,
      "thinking_mode": "disabled",
      "timeout_seconds": 120.0,
      "max_prompt_bytes": 262144,
      "max_output_tokens": 12288,
      "max_total_tokens": 1000000
    },
    "judge": null
  },
  "statistics": {
    "bootstrap_samples": 2000,
    "seed": 1729
  },
  "execution": {
    "root_workers": 4,
    "max_in_flight": 4,
    "requests_per_minute": 120,
    "cooldown_seconds": 30
  }
}
JSON
)

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPERIMENT_PREFIX=feasibility
EXPERIMENT_LAUNCHER="$SCRIPT_DIR/$(basename -- "${BASH_SOURCE[0]}")"
source "$SCRIPT_DIR/experiment_campaign.sh"
experiment_campaign "$@"
