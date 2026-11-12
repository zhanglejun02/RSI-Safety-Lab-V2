"""Sequential, preplanned jobs through the public runner; no retry supervisor."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from rsi_lab.agent_bench import load_config, plan_experiment, run_experiment
from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.errors import ConflictError, ValidationError
from rsi_lab.infra.runlock import run_lock
from rsi_lab.serialization import digest


def run(path, output, *, resume=False, env_file=None):
    jobs = json.loads(Path(path).read_text())
    if (type(jobs) is not list or not jobs or any(type(j) is not dict or set(j) != {"name", "config", "plan", "output"}
            or any(type(v) is not str or not v for v in j.values()) for j in jobs)
            or len({j["name"] for j in jobs}) != len(jobs)
            or len({str(Path(j["output"]).resolve()) for j in jobs}) != len(jobs)):
        raise ValidationError("Batch requires unique named jobs with config, frozen plan and output paths")
    output = Path(output).resolve()
    if output.exists() and not resume:
        raise ConflictError("Batch output exists; use explicit resume")
    output.mkdir(parents=True, exist_ok=True)
    with run_lock(output):
        prepared = [(j, load_config(j["config"]), read_record(Path(j["plan"]))) for j in jobs]
        binding = [{**j, "config_sha256": digest(c), "plan_sha256": digest(p)} for j, c, p in prepared]
        save_record(output / "manifest.json", {"protocol": "planned-batch-v1", "jobs": binding})
        if env_file:
            from rsi_lab.cli import _credential_names
            from rsi_lab.infra.environment import load_environment
            names = set().union(*(_credential_names(c) for _, c, _ in prepared))
            load_environment(env_file, tuple(names | {"SSL_CERT_FILE"}))
        # Validate the whole static allocation before the first paid dispatch.
        for job, config, planned in prepared:
            if (Path(job["output"]) / "summary.json").exists() and resume:
                continue  # Completed resume is verified by its original frozen inputs.
            if plan_experiment(config) != planned:
                raise ConflictError("Batch job differs from its frozen plan: " + job["name"])
        completed = []
        def status(state, current=None, error=None):
            value = {"state": state, "current_job": current, "completed_jobs": completed,
                     "pid": os.getpid(), "updated_at": datetime.now(timezone.utc).isoformat(), "error": error}
            temporary = output / "status.tmp"
            temporary.write_text(json.dumps(value, indent=2) + "\n")
            temporary.replace(output / "status.json")
        try:
            for job, config, planned in prepared:
                status("running", job["name"])
                summary = run_experiment(config, job["output"], resume=resume and Path(job["output"]).exists(), expected_plan=planned)
                usages = [v for row in summary.get("rows", []) for k, v in row.items() if k.endswith("_usage") and v]
                tokens = [v["actual_total_tokens"] for v in usages if v["actual_total_tokens"] is not None]
                completed.append({"name": job["name"], "output": str(Path(job["output"]).resolve()),
                    "summary_sha256": digest(summary), "origin": summary.get("origin"),
                    "calls": sum(v["dispatched_calls"] for v in usages),
                    "tokens": sum(tokens) if tokens else None,
                    "usage_missing_calls": sum(v.get("usage_missing_calls", 0) for v in usages),
                    "unknown": sum(v["unknown_responses"] for v in usages),
                    "contrasts": summary.get("statistics", {}).get("contrasts", [])})
            save_record(output / "summary.json", {"protocol": "planned-batch-v1", "jobs": completed,
                "scope": "Studies remain separate; repeated continuations are not new independent roots."})
            lines = ["# Planned batch", "", "No automatic retries or outcome-dependent extra jobs.", "",
                     "| Job | Calls | Reported tokens | Usage missing | Unknown | Report |", "|---|---:|---:|---:|---:|---|"]
            for row in completed:
                lines.append(f"| {row['name']} | {row['calls']} | {row['tokens']} | {row['usage_missing_calls']} | {row['unknown']} | [report]({row['output']}/report.md) |")
            lines += ["", "Per-job paired contrasts are in summary.json. Repetition diagnostics stay within each original source root."]
            (output / "report.md").write_text("\n".join(lines) + "\n")
            status("complete")
        except BaseException as exc:
            status("failed", job["name"], type(exc).__name__)
            raise
    return {"output": str(output), "state": "complete", "jobs": len(completed)}
