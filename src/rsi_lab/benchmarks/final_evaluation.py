"""Final-policy evaluation adapters. No access to optimization or activation."""
from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.errors import BudgetExceeded, OutcomeUnknown
from rsi_lab.serialization import digest
from .metrics import aggregate
from .xstest import XSTest


def preflight(config):
    result = {}
    if config["xstest_ids"] is None or config["xstest_ids"]:
        result["xstest"] = XSTest(config["xstest_ids"]).describe()
    if config["agentharm"] is not None:
        from .agentharm import preflight as check
        result["agentharm"] = check(config["agentharm"])
    return result


def evaluate(program, directory, config, common, *, provider_factory, runtime_factory):
    results = []
    ids = config["evaluation"]["xstest_ids"]
    if ids is None or ids:
        location = directory / "xstest"
        judge = provider_factory(location, "judge") if config["mode"] == "http" else None
        backend = XSTest(ids, judge, control=config["mode"] == "scripted")
        provider = provider_factory(location, "test", backend, backend.cases())
        runtime = runtime_factory(location, provider, "test")
        metrics = []
        for case in backend.cases():
            path = location / "outcomes" / (digest(case) + ".json")
            if path.exists():
                outcome = read_record(path)
            else:
                try:
                    record = runtime.execute(program, case, backend, common["root_id"] + "/xstest/" + digest(case))
                    outcome = record["metrics"]["safety_metrics"]
                except (BudgetExceeded, OutcomeUnknown):
                    values = {"refusal": None}
                    if case["safe"]:
                        values["over_refusal"] = None
                    outcome = {"family": "text_safety", "judge": backend.describe()["judge"], "values": values}
                save_record(path, outcome)
            metrics.append(outcome)
        measured = aggregate(metrics)
        results.append({**common, "benchmark": "xstest", "final_source_sha256": digest(program),
                        "metrics": measured, "estimates": {k: v["mean"] if not v["missing"] else None for k, v in measured.items()},
                        "test_usage": provider.summary(), "judge_usage": judge.summary() if judge else None,
                        "tool_calls": 0})
    if config["evaluation"]["agentharm"] is not None:
        from .agentharm import evaluate as run
        results.extend(run(program, directory / "agentharm", config, common, provider_factory=provider_factory))
    return results
