"""Scheduling acceptance through the public runner; local HTTP by default."""
import argparse
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
from threading import Lock, Thread
import time

from rsi_lab.agent_bench import load_config, plan_experiment, run_experiment
from rsi_lab.benchmarks.agentdojo_suite import Catalog
from rsi_lab.engine.continuation import save_record
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import canonical_bytes, decode_json, digest


@contextmanager
def delayed_actor(config, delay):
    """Prescribed native actions over actual HTTP; never a natural-model result."""
    backend = Catalog(config["training"])
    cases = {digest(c["case_id"]): c for c in backend.catalog}
    state, lock = {"active": 0, "peak": 0, "calls": 0, "starts": []}, Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = decode_json(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["active"] += 1
                state["calls"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["starts"].append(time.monotonic())
            try:
                time.sleep(delay)
                messages = body["messages"]
                request = decode_json(messages[1]["content"])
                history = [decode_json(m["content"]) for m in messages[2:] if m["role"] == "user"]
                action = backend.scripted_reply(cases[request["case_id"]], history, messages[0]["content"])
                raw = canonical_bytes({"model": "local-fixture", "choices": [{"finish_reason": "stop",
                    "message": {"content": json.dumps(action)}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            finally:
                with lock:
                    state["active"] -= 1
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def scientific_projection(summary):
    return [{**{k: r[k] for k in ("root_id", "final_source_sha256", "metrics", "primary", "estimates")},
             "curve": [(p["public"]["score"], p.get("policy_changed", False)) for p in r["learning_curve"]]}
            for r in summary["rows"]]


def compare(config, output, *, remote=False, delay=0.2):
    """Freeze both allocations before dispatch; vary only root_workers, never retry."""
    config, output = deepcopy(config), Path(output).resolve()
    if config["methods"] != ["frozen"] or config["evaluation"] != {"xstest_ids": [], "agentharm": None}:
        raise ValidationError("Scheduling acceptance requires frozen AgentDojo roots only")
    if "requests_per_minute" not in config.get("execution", {}):
        raise ValidationError("Declare requests_per_minute explicitly, including null")
    if remote and config["mode"] != "http":
        raise ValidationError("--remote requires explicit HTTP model configuration")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / "validator.py")
    results, projections = {}, []
    with nullcontext(None) if remote else delayed_actor(config, delay) as fixture:
        if fixture:
            model = {"base_url": fixture[0], "model": "local-fixture", "max_output_tokens": 2048,
                     "max_total_tokens": 600000, "timeout_seconds": 10.0}
            config.update(mode="http", models={"actor": model, "editor": model, "judge": None})
            config["study"]["selection_reason"] = "LOCAL HTTP CONTROL; prescribed native actions, no natural model result. " + config["study"]["selection_reason"]
        allocations = []
        for name, workers in (("serial", 1), ("parallel", 2)):
            selected = deepcopy(config)
            selected["execution"]["root_workers"] = workers
            plan = plan_experiment(selected)
            (output / (name + "-config.json")).write_text(json.dumps(selected, indent=2) + "\n")
            save_record(output / (name + "-plan.json"), plan)
            allocations.append((name, selected, plan))
        save_record(output / "comparison-plan.json", {
            "kind": "remote_scheduling_diagnostic" if remote else "local_http_control",
            "local_delay_seconds": None if remote else delay,
            "order": [a[0] for a in allocations], "paired_runs": 1,
            "changed_factor": "execution.root_workers", "method_comparison": False,
            "plans": {name: digest(plan) for name, _, plan in allocations}})
        for name, selected, plan in allocations:
            if fixture:
                fixture[1].update(active=0, peak=0, calls=0, starts=[])
            started = time.monotonic()
            summary = run_experiment(selected, output / name, expected_plan=plan)
            usage = [r[key] for r in summary["rows"] for key in ("train_usage", "test_usage")]
            measured = summary["performance"]
            results[name] = {"wall_seconds": time.monotonic() - started,
                "requests_per_minute": selected["execution"]["requests_per_minute"],
                "calls": sum(u["dispatched_calls"] for u in usage),
                "tokens": sum(u["actual_total_tokens"] for u in usage) if remote else None,
                "unknown_calls": sum(u["unknown_responses"] for u in usage),
                "usage_missing_calls": sum(u["usage_missing_calls"] for u in usage),
                "missing_final_episodes": sum(r["metrics"]["missing_episodes"] for r in summary["rows"]),
                **{k: measured[k] for k in ("observed_peak_in_flight", "http_429", "http_5xx", "timing_missing_calls")}}
            if fixture:
                assert results[name]["calls"] == fixture[1]["calls"]
                assert measured["observed_peak_in_flight"] == fixture[1]["peak"]
            projections.append(scientific_projection(summary))
            save_record(output / (name + "-measurement.json"), results[name])
            print(json.dumps({name: results[name]}), flush=True)
        equivalent = projections[0] == projections[1]
        if not remote:
            assert equivalent, "Local control scientific projections differ"
        results.update(speedup=results["serial"]["wall_seconds"] / results["parallel"]["wall_seconds"],
                       equivalent_scientific_projection=equivalent,
                       caveat="One timing pair; fixed order and remote response variation prevent causal performance claims")
        save_record(output / "comparison.json", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote", action="store_true", help="Explicitly use the configured paid HTTP provider")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.remote and args.env_file:
        from rsi_lab.cli import _credential_names
        from rsi_lab.infra.environment import load_environment
        load_environment(args.env_file, _credential_names(config) | {"SSL_CERT_FILE"})
    compare(config, args.output, remote=args.remote)
