#!/usr/bin/env bash
# Saved answers only: never launch an actor or an optimizer.
# Edit this block for a NEW campaign. Resume always uses frozen settings/source.
set -euo pipefail
SETTINGS=$(cat <<'JSON'
{
  "profile": "scoring-calibration",
  "protocol": "frozen-answer-scoring-study-v1",
  "mode": "http",
  "action": "rescore",
  "source_run": "runs/current/scale-20261119-v3/run",
  "extraction_protocol": "privacy-recipient-event-observations-v6-r3",
  "control_repeats": 3,
  "workers": 8,
  "requests_per_minute": 60,
  "split_seed": 1729,
  "heldout_fraction": 0.25,
  "judge": {
    "base_url": "https://api.moonshot.cn/v1",
    "model": "kimi-k2.6",
    "api_key_env": "MOONSHOT_API_KEY",
    "temperature": 0.6,
    "thinking_mode": "disabled",
    "timeout_seconds": 90.0,
    "max_prompt_bytes": 49152,
    "max_output_tokens": 4096,
    "max_calls": 2000,
    "max_total_tokens": 120000000
  }
}
JSON
)

REPO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${RSI_PYTHON:-"$REPO_DIR/.venv/bin/python"}
ENV_FILE=${RSI_ENV_FILE:-"$REPO_DIR/.env"}
ACTION=${1:-plan}
CAMPAIGN=${2:-"$REPO_DIR/runs/current/scoring-$(TZ=Asia/Shanghai date +%Y%m%d-%H%M%S)"}
cd "$REPO_DIR"
if [[ $# -gt 2 ]]; then echo "Usage: bash $0 ACTION [CAMPAIGN]" >&2; exit 2; fi
case "$ACTION" in
  plan|export|controls|rescore|start|resume|resume-start|status|inspect) ;;
  *) echo "Use plan, export, controls, rescore, start, resume, resume-start, status or inspect" >&2; exit 2;;
esac
case "$ACTION" in
  resume|resume-start|status|inspect)
    if [[ $# -ne 2 ]]; then echo "An existing CAMPAIGN is required" >&2; exit 2; fi;;
esac
CAMPAIGN=$("$PYTHON" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$CAMPAIGN")
if [[ -f "$CAMPAIGN/config.json" && ( "$ACTION" == export || "$ACTION" == controls || "$ACTION" == rescore ) ]]; then
  "$PYTHON" - "$CAMPAIGN/config.json" "$ACTION" <<'PY'
import json,sys
from pathlib import Path
saved=json.loads(Path(sys.argv[1]).read_text())["action"]
if saved != sys.argv[2]:
    raise SystemExit(f"Requested action {sys.argv[2]} differs from frozen action {saved}; use a new campaign")
PY
fi
if [[ "$ACTION" == status ]]; then
  "$PYTHON" scripts/background_experiment.py status "$CAMPAIGN"
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - "$CAMPAIGN" <<'PY'
import json,sys
from pathlib import Path
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import digest
p=Path(sys.argv[1])
if not (p/"plan.json").is_file():
    print(json.dumps({"scoring_progress":{"status":"no_frozen_plan"}},indent=2))
    raise SystemExit(0)
plan=read_record(p/"plan.json")
config=json.loads((p/"config.json").read_text())
if plan["protocol"] != "frozen-answer-scoring-study-v1" or digest(config) != plan["config_sha256"]:
    raise SystemExit("Scoring plan and configuration do not match")
samples=[] if config["action"]=="export" else plan["samples"]
completed=known=missing=unknown=0
for sample in samples:
    path=p/"run/judgments"/(digest(sample["scoring_id"])+".json")
    if not path.is_file():
        continue
    result=read_record(path)
    if result["scoring_id"] != sample["scoring_id"] or result["sample_sha256"] != digest(sample):
        raise SystemExit("Saved judgment does not match its frozen input")
    risk=result["risk"]
    if risk is not None and type(risk) is not bool:
        raise SystemExit("Saved risk label must be true, false or null")
    completed+=1
    known+=risk is not None
    missing+=risk is None
    unknown+=result.get("error")=="OutcomeUnknown"
print(json.dumps({"scoring_progress":{
    "action":config["action"],"completed_inputs":completed,"planned_inputs":len(samples),
    "pending_inputs":len(samples)-completed,"known_inputs":known,"missing_inputs":missing,
    "new_scoring_unknown_inputs":unknown,
    "unknown_scope":"Saved judgments in this study only; excludes source-run unknowns and pending provider reservations",
    "api_calls_for_status":0}},indent=2))
PY
  exit 0
fi
if [[ "$ACTION" == resume-start ]]; then
  exec "$PYTHON" scripts/background_experiment.py "$ACTION" "$CAMPAIGN"
fi
if [[ "$ACTION" != resume && "$ACTION" != inspect && ! -d "$CAMPAIGN" ]]; then
  mkdir -p -- "$CAMPAIGN"
  printf '%s\n' "$SETTINGS" | "$PYTHON" -c '
import json,sys
from pathlib import Path
config=json.load(sys.stdin); action=sys.argv[2]
if action in ("export","controls","rescore"): config["action"]=action
if config["action"]=="export": config.update(mode="scripted",judge=None)
config["source_run"]=str(Path(config["source_run"]).resolve())
Path(sys.argv[1]).write_text(json.dumps(config,indent=2)+"\n")
' "$CAMPAIGN/config.json" "$ACTION"
  cp -- "${BASH_SOURCE[0]}" "$CAMPAIGN/launch.sh"
  "$PYTHON" -m rsi_lab.cli plan --config "$CAMPAIGN/config.json" --output "$CAMPAIGN/plan.json" > "$CAMPAIGN/plan-output.json"
  "$PYTHON" scripts/background_experiment.py freeze-source "$CAMPAIGN"
  "$PYTHON" - "$CAMPAIGN" "$PYTHON" "$ENV_FILE" <<'PY'
from pathlib import Path
import shlex,sys
p=Path(sys.argv[1]); python=sys.argv[2]; env=sys.argv[3]
arguments=["run","--config",str(p/"config.json"),"--output",str(p/"run"),"--plan",str(p/"plan.json"),"--resume"]
command=[python,"-m","rsi_lab.cli",*arguments]
if __import__('json').loads((p/'config.json').read_text())["mode"]=="http":
    wrapper="import sys\nfrom pathlib import Path\nfrom rsi_lab.infra.environment import load_environment\nfrom rsi_lab.cli import main\nif not Path(sys.argv[2]).is_file():\n    load_environment(sys.argv[1], ('DEEPSEEK_API_KEY','MOONSHOT_API_KEY','SSL_CERT_FILE'))\nraise SystemExit(main(sys.argv[3:]))"
    command=[python,"-c",wrapper,env,str(p/"run/summary.json"),*arguments]
header="#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1\nexport PYTHONPATH="+shlex.quote(str(p/"execution-source/package"))+"\n"
(p/"background-driver.sh").write_text(header+"exec "+shlex.join(command)+"\n")
(p/"background-run.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\nexec bash "+shlex.quote(str(p/"background-driver.sh"))+"\n")
PY
fi
if [[ ! -f "$CAMPAIGN/execution-source.json" ]]; then echo "Campaign has no frozen source" >&2; exit 2; fi
if [[ "$ACTION" == plan ]]; then
  "$PYTHON" - "$CAMPAIGN/plan.json" <<'PY'
from rsi_lab.infra.records import read_record
import json,sys
p=read_record(sys.argv[1]);print(json.dumps({"cases":len(p["source"]["cases"]),"unique_scoring_inputs":len(p["samples"]),"maximum_judge_calls":p["maximum_judge_calls"],"actor_calls":0},indent=2))
PY
  exit 0
fi
if [[ "$ACTION" == start ]]; then
  exec "$PYTHON" scripts/background_experiment.py start "$CAMPAIGN" "$REPO_DIR" true
fi
"$PYTHON" - "$CAMPAIGN" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,"scripts")
from background_experiment import verify_source,prepare_resume
p=Path(sys.argv[1]);verify_source(p)
if (p/"background.json").exists(): prepare_resume(p)
PY
if [[ "$ACTION" == inspect ]]; then
  export PYTHONPATH="$CAMPAIGN/execution-source/package" PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1
  exec "$PYTHON" -m rsi_lab.cli inspect --output "$CAMPAIGN/run"
fi
if [[ -f "$CAMPAIGN/run/summary.json" ]]; then
  # Verify completed work without loading credentials, including older drivers.
  export PYTHONPATH="$CAMPAIGN/execution-source/package" PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1
  exec "$PYTHON" -m rsi_lab.cli run --config "$CAMPAIGN/config.json" --output "$CAMPAIGN/run" --plan "$CAMPAIGN/plan.json" --resume
fi
exec bash "$CAMPAIGN/background-driver.sh"
