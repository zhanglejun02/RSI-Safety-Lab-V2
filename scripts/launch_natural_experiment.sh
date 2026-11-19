# Shared implementation sourced by the parameter-only natural experiment entrypoints.
# Paths can also be overridden from the calling shell. Credentials stay in .env.
REPO_DIR=$(cd -- "$(dirname -- "$LAUNCH_SCRIPT")/.." && pwd)
PYTHON=${RSI_PYTHON:-"$REPO_DIR/.venv/bin/python"}
ENV_FILE=${RSI_ENV_FILE:-"$REPO_DIR/.env"}
cd "$REPO_DIR"
ACTION=${1:-plan}
case "$ACTION" in
  plan|run|start) CAMPAIGN=${2:-"$REPO_DIR/runs/current/${CAMPAIGN_PREFIX:-natural}-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"} ;;
  resume|resume-start|inspect|status)
    if [[ $# -ne 2 ]]; then echo "Usage: bash $0 $ACTION CAMPAIGN" >&2; exit 2; fi
    CAMPAIGN=$2 ;;
  *) echo "Usage: bash $0 {plan|run|start|resume|resume-start|inspect|status} [CAMPAIGN]" >&2; exit 2 ;;
esac
if [[ $# -gt 2 ]]; then echo "Too many arguments" >&2; exit 2; fi
if [[ ! -x "$PYTHON" ]]; then echo "Python not found: $PYTHON" >&2; exit 2; fi

if [[ "$ACTION" == plan || ( ( "$ACTION" == run || "$ACTION" == start ) && ! -d "$CAMPAIGN" ) ]]; then
  # A plan may expose a funding gap; a run must fit the authorized ceiling.
  BUILD_ARGS=("$CAMPAIGN")
  if [[ "$ACTION" == plan ]]; then BUILD_ARGS+=(--estimate); fi
  printf '%s\n' "$EXPERIMENT_SETTINGS" | "$PYTHON" scripts/natural_experiment_config.py "${BUILD_ARGS[@]}"
  cp -- "$LAUNCH_SCRIPT" "$CAMPAIGN/launch.sh"
  cp -- scripts/natural_experiment_config.py "$CAMPAIGN/config-builder.py"
  cp -- scripts/launch_natural_experiment.sh "$CAMPAIGN/launch-driver.sh"
fi
if [[ ! -f "$CAMPAIGN/plan.json" ]]; then
  echo "No frozen plan in $CAMPAIGN; create a new campaign with plan." >&2; exit 2
fi
CAMPAIGN=$(cd -- "$CAMPAIGN" && pwd)
echo "Campaign: $CAMPAIGN"
if [[ "$ACTION" == status ]]; then
  "$PYTHON" scripts/background_experiment.py status "$CAMPAIGN"
  exit 0
fi
if [[ "$ACTION" == resume-start ]]; then
  "$PYTHON" scripts/background_experiment.py resume-start "$CAMPAIGN"
  exit 0
fi
if [[ "$ACTION" == resume ]]; then
  "$PYTHON" scripts/background_experiment.py prepare-resume "$CAMPAIGN"
  if [[ -f "$CAMPAIGN/execution-source.json" ]]; then
    export PYTHONPATH="$CAMPAIGN/execution-source/package"
    export PYTHONSAFEPATH=1
    export PYTHONDONTWRITEBYTECODE=1
  fi
fi
if [[ "$ACTION" == start && ( -f "$CAMPAIGN/background.json" || -f "$CAMPAIGN/run/summary.json" ) ]]; then
  # Existing jobs never silently restart. Completed start is read-only.
  "$PYTHON" scripts/background_experiment.py start "$CAMPAIGN" "$REPO_DIR" "${KEEP_AWAKE:-false}"
  exit 0
fi
if [[ "$ACTION" != inspect ]]; then
  # Freeze secondary reports before execution. Existing runs never acquire a new
  # postprocessor on resume, and v1 campaigns keep their original reporting path.
  "$PYTHON" - "$CAMPAIGN" "$REPO_DIR/scripts" <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import sys

campaign, scripts = map(Path, sys.argv[1:])
if json.loads((campaign / 'config.json').read_text()).get('task_pack') in ('privacy-drafts-v2', 'privacy-drafts-v3'):
    binding = campaign / 'reports.json'
    if not binding.exists() and not (campaign / 'run').exists():
        files = {}
        for name in ('summarize_search.py', 'summarize_comparison.py'):
            shutil.copyfile(scripts / name, campaign / name)
            files[name] = hashlib.sha256((campaign / name).read_bytes()).hexdigest()
        # A saved plan may predate reporting support. Record the actual execution
        # driver separately without replacing its originally archived plan driver.
        shutil.copyfile(scripts / 'launch_natural_experiment.sh', campaign / 'execution-driver.sh')
        files['execution-driver.sh'] = hashlib.sha256((campaign / 'execution-driver.sh').read_bytes()).hexdigest()
        binding.write_text(json.dumps({'protocol': 'campaign-reports-v1', 'files': files}, indent=2) + '\n')
    if binding.exists():
        for name, expected in json.loads(binding.read_text())['files'].items():
            if name not in ('summarize_search.py', 'summarize_comparison.py', 'execution-driver.sh'):
                raise ValueError('Unknown frozen report artifact')
            if hashlib.sha256((campaign / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Frozen report artifact changed: ' + name)
PY
fi
if [[ "$ACTION" == plan ]]; then
  echo "Zero API calls. Paid execution rechecks the frozen budget. Start this plan: bash $0 run '$CAMPAIGN'"
  exit 0
fi
if [[ "$ACTION" == inspect ]]; then
  "$PYTHON" -m rsi_lab.cli inspect --output "$CAMPAIGN/run"
  exit 0
fi

CONFIG_BUILDER="$CAMPAIGN/config-builder.py"
if [[ ! -f "$CONFIG_BUILDER" ]]; then CONFIG_BUILDER="$REPO_DIR/scripts/natural_experiment_config.py"; fi
"$PYTHON" "$CONFIG_BUILDER" "$CAMPAIGN" --check-budget

if [[ ! -f "$CAMPAIGN/summarize.py" ]]; then
  cp -- scripts/summarize_natural_experiment.py "$CAMPAIGN/summarize.py"
fi

if [[ "$ACTION" == start ]]; then
  # Check source and allocation before detaching. The public CLI checks again
  # before any model request; later parameter edits cannot affect this job.
  "$PYTHON" scripts/background_experiment.py freeze-source "$CAMPAIGN"
  "$PYTHON" - "$CAMPAIGN" "$REPO_DIR" "$PYTHON" "$ENV_FILE" "$LAUNCH_SCRIPT" <<'PY'
from pathlib import Path
import shlex
import sys
campaign, repo, python, env_file, launcher = sys.argv[1:]
p = Path(campaign)
with (p / 'background-driver.sh').open('xb') as out:
    out.write((Path(repo) / 'scripts/launch_natural_experiment.sh').read_bytes())
q = shlex.quote
with (p / 'background-run.sh').open('x') as out:
    out.write(
        '#!/usr/bin/env bash\nset -euo pipefail\n'
        + 'export RSI_PYTHON=' + q(python) + '\n'
        + 'export RSI_ENV_FILE=' + q(env_file) + '\n'
        + 'export PYTHONPATH=' + q(str(p / 'execution-source/package')) + '\n'
        + 'export PYTHONSAFEPATH=1\nexport PYTHONDONTWRITEBYTECODE=1\n'
        + 'LAUNCH_SCRIPT=' + q(launcher) + '\n'
        + 'source ' + q(str(p / 'background-driver.sh')) + ' run ' + q(campaign) + '\n')
PY
  "$PYTHON" scripts/background_experiment.py start "$CAMPAIGN" "$REPO_DIR" "${KEEP_AWAKE:-false}"
  exit 0
fi

RUN_ARGS=(--config "$CAMPAIGN/config.json" --plan "$CAMPAIGN/plan.json"
          --output "$CAMPAIGN/run")
# A completed resume does not load credentials or require an existing .env.
if [[ ! -f "$CAMPAIGN/run/summary.json" ]]; then RUN_ARGS+=(--env-file "$ENV_FILE"); fi
if [[ "$ACTION" == resume ]]; then RUN_ARGS+=(--resume); fi
# pipefail preserves errors. No retry or automatic replacement run is performed.
"$PYTHON" -u -m rsi_lab.cli run "${RUN_ARGS[@]}" 2>&1 |
  tee "$CAMPAIGN/launch-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S).log"
"$PYTHON" -m rsi_lab.cli inspect --output "$CAMPAIGN/run"
"$PYTHON" "$CAMPAIGN/summarize.py" --campaign "$CAMPAIGN"
if [[ -f "$CAMPAIGN/reports.json" ]]; then
  "$PYTHON" "$CAMPAIGN/summarize_search.py" --campaign "$CAMPAIGN"
  "$PYTHON" "$CAMPAIGN/summarize_comparison.py" --campaign "$CAMPAIGN"
fi
if [[ "$ACTION" == resume ]]; then
  "$PYTHON" "$REPO_DIR/scripts/background_experiment.py" resume-complete "$CAMPAIGN"
fi
