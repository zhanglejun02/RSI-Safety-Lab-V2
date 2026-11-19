"""Two predeclared measurements through the public runner; never retry failures.

Phase one freezes an unchanged founder and executes every final task repeatedly.
An optional OpenEvolve root checks the candidate transport separately. Phase two
rejudges ALL founder answers, including failures, without any actor or optimizer.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from rsi_lab.agent_bench import inspect_run, plan_experiment, run_experiment
from rsi_lab.frozen import implementation_fingerprint
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.infra.runlock import run_lock
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies.repetitions import diagnostics


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def render_config(settings):
    s = settings
    for key in ("execution_repeats", "judgment_repeats"):
        if type(s[key]) is not int or not 2 <= s[key] <= 20:
            raise ValueError(key + " must be an integer in [2,20]")
    if type(s["check_openevolve"]) is not bool:
        raise ValueError("check_openevolve must be boolean")
    train = 8 if s["check_openevolve"] else 4
    final = 2 * s["execution_repeats"]
    return {"profile": "seabench-controller", "protocol": "seabench-controller-study-v1", "mode": "http",
            "source": str(Path(s["source"]).resolve()), "sequence": "controller_update/personal_admin/privacy",
            "task_pack": "privacy-drafts-v1", "methods": ["frozen", "openevolve"] if s["check_openevolve"] else ["frozen"],
            "arms": ["native_only"], "seeds": [s["seed"]], "slots": 1,
            "models": deepcopy(s["models"]), "actor_context": s["actor_context"],
            "final_text_steps": s["final_text_steps"], "final_repeats": s["execution_repeats"],
            "public_rollout_cache": True, "record_events": True,
            "budget": {"max_steps": s["max_steps"], "train_episodes": train, "train_calls": train * s["max_steps"],
                       "test_episodes": final, "test_calls": final * s["max_steps"],
                       "editor_calls_per_slot": 3, "judge_calls": max(train, 2 * final)},
            "execution": {"root_workers": s["root_workers"], "max_in_flight": s["root_workers"],
                          "requests_per_minute": s["requests_per_minute"], "cooldown_seconds": 30}}


def allocation(settings, config):
    """Bound both phases before the first dispatch, even though answers come later."""
    amounts = []
    def add(role, phase, calls, tokens):
        prices = settings["rates_cny_per_million"][role]
        incoming, outgoing = (Decimal(str(prices[k])) for k in ("input", "output"))
        if not all(v.is_finite() and v >= 0 for v in (incoming, outgoing)):
            raise ValueError("Invalid price declaration")
        out = min(tokens, calls * config["models"][role]["max_output_tokens"])
        cost = (tokens * incoming + out * max(Decimal(0), outgoing - incoming)) / 1000000
        amounts.append({"phase": phase, "role": role, "max_calls": calls, "max_total_tokens": tokens,
                        "cost_bound_cny": float(cost)})
    b = config["budget"]
    for method in config["methods"]:
        for phase, role, calls in (("train", "actor", b["train_calls"]), ("test", "actor", b["test_calls"]),
                                  ("train-judge", "judge", b["judge_calls"]), ("test-judge", "judge", b["judge_calls"])):
            add(role, method + "/" + phase, calls, config["models"][role]["max_total_tokens"])
        if method != "frozen":
            add("editor", method + "/editor", 3, config["models"]["editor"]["max_total_tokens"])
    calls = 4 * settings["execution_repeats"] * settings["judgment_repeats"]
    add("judge", "rejudge", calls, settings["rejudge_token_cap"])
    bound = sum(Decimal(str(row["cost_bound_cny"])) for row in amounts)
    previous, buffer = (Decimal(str(settings[k])) for k in ("previous_spend_cny", "cost_buffer_cny"))
    cap = None if settings["budget_cny"] is None else Decimal(str(settings["budget_cny"]))
    if (any(not v.is_finite() or v < 0 for v in (previous, buffer))
            or cap is not None and (not cap.is_finite() or cap < 0)):
        raise ValueError("Invalid monetary limit")
    if cap is not None and bound + previous + buffer > cap:
        raise ValueError(f"Measurement allocation {bound} + previous {previous} + buffer {buffer} exceeds CNY {cap}")
    return {"protocol": "measurement-allocation-v1", "allocations": amounts, "cost_bound_cny": float(bound),
            "previous_spend_cny": float(previous), "budget_cny": None if cap is None else float(cap), "cost_buffer_cny": float(buffer),
            "rates_cny_per_million": settings["rates_cny_per_million"], "pricing_sources": settings["pricing_sources"],
            "rates_checked_on": settings["rates_checked_on"],
            "assumptions": "Frozen uncached peak prices and provider token/output limits; not a verified invoice guarantee."}


def prepare(path, settings):
    config = render_config(settings)
    money = allocation(settings, config)
    phases = [row for row in money["allocations"] if row["phase"] != "rejudge"]
    config["execution"].update(max_total_calls=sum(row["max_calls"] for row in phases),
                               max_total_tokens=sum(row["max_total_tokens"] for row in phases))
    planned = plan_experiment(config)
    if planned["downstream_tasks"] != 2:
        raise ValueError("Measurement allocation expects the declared two-task final partition")
    path.mkdir(parents=True)
    write(path / "settings.json", settings)
    write(path / "budget.json", money)
    write(path / "execution-config.json", config)
    save_record(path / "execution-plan.json", planned)
    save_record(path / "measurement-plan.json", {
        "protocol": "measurement-checks-v1", "implementation": implementation_fingerprint(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "settings_sha256": digest(settings), "budget_sha256": digest(money), "execution_plan_sha256": digest(planned),
        "rejudge": {"source": "all founder final records, including missing answers; no outcome selection",
                    "root_id": f"frozen-native_only-{settings['seed']}", "repeats": settings["judgment_repeats"],
                    "expected_source_answers": 2 * settings["execution_repeats"],
                    "expected_judge_calls": 4 * settings["execution_repeats"] * settings["judgment_repeats"]}})
    return {"campaign": str(path), "api_calls": 0, "cost_bound_cny": money["cost_bound_cny"],
            "scope": "measurement reliability and optional candidate-format check; not a method safety comparison"}


def rejudge_config(path, settings, original):
    config = deepcopy(original)
    config.update(methods=["frozen"], final_repeats=settings["judgment_repeats"],
                  frozen_evaluation={"run": str(path / "execution"), "root_ids": [f"frozen-native_only-{settings['seed']}"],
                                     "kind": "rejudge", "order_seed": settings["seed"]})
    records = 2 * settings["execution_repeats"] * settings["judgment_repeats"]
    config["budget"].update(test_episodes=records, test_calls=records * settings["max_steps"], judge_calls=2 * records)
    config["models"]["judge"]["max_total_tokens"] = settings["rejudge_token_cap"]
    config["execution"].update(max_total_calls=2 * records, max_total_tokens=settings["rejudge_token_cap"])
    return config


def summarize(path, settings, execution, judged):
    from cost_reader import provider_costs
    founder = next(row for row in execution["rows"] if row["method"] == "frozen")
    if founder["final_source_sha256"] != execution["allocation"]["initial_policy_sha256"]:
        raise ValueError("Execution measurement changed the founder")
    execution_stats = diagnostics([founder])
    by_task = defaultdict(list)
    for case in founder["cases"]:
        record = read_record(path / "execution" / case["record"])
        by_task[case["task_id"]].append(digest(record["answer"]) if record.get("answer") else None)
    answers = {key: {"allocated": len(values), "present": sum(v is not None for v in values),
                     "unique_answers": len(set(values) - {None})} for key, values in by_task.items()}
    costs = {name: provider_costs(path / name, settings["rates_cny_per_million"])["total"]
             for name in ("execution", "rejudge")}
    candidate = []
    for row in execution["rows"]:
        if row["method"] == "frozen":
            continue
        root = read_record(path / "execution/roots" / row["root_id"] / "root.json")
        candidate.append({"method": row["method"], "slots": len(root["slots"]),
                          "committed": sum(s["committed"] for s in root["slots"]),
                          "slot_errors": [s.get("error") for s in root["slots"] if s.get("error")],
                          "deployed_changed": row["final_source_sha256"] != execution["allocation"]["initial_policy_sha256"]})
    result = {"protocol": "measurement-checks-report-v1", "implementation": execution["allocation"]["implementation"],
              "api_calls_for_analysis": 0, "execution_summary_sha256": digest(execution), "rejudge_summary_sha256": digest(judged),
              "execution": execution_stats, "answers": answers, "rejudge": judged["repetition_diagnostics"],
              "candidate_transport_check": candidate, "costs": costs,
              "scope": "One source root; repeats are not independent roots. Label consistency is not human-validated accuracy."}
    output = path / "analysis"
    output.mkdir(exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 测量重复校验", "", "本批测执行与评分波动，不是三种 RSI 或 safety 模块效果比较。", "",
             "| 固定 Harness 任务 | 执行次数 | 不同答案数 |", "|---|---:|---:|"]
    for task, value in answers.items():
        lines.append(f"| {task} | {value['present']}/{value['allocated']} | {value['unique_answers']} |")
    for title, data in (("重复执行后的评分（包含执行与评分变化）", execution_stats),
                        ("固定答案重复评分", judged["repetition_diagnostics"])):
        lines += ["", "## " + title, "", "| 任务 / 来源答案 | 指标 | 阳性/有效标签 | 缺失 | 配对不一致率 |", "|---|---|---:|---:|---:|"]
        for row in data["rows"]:
            sample = Path(row["source_case"]).stem[:10] if row["source_case"] else "重复执行"
            for key, value in row["metrics"].items():
                rate = value["pairwise_disagreement"]
                lines.append(f"| {row['task_id']} / {sample} | {key} | {value['positive']}/{value['known']} | {value['missing']} | "
                             + ("缺失" if rate is None else f"{rate:.1%}") + " |")
    lines += ["", "一项任务对应一个固定部署，重复不是新增独立搜索根。评分一致不代表评分准确；人工标签仍未取得。",
              "", "OpenEvolve 仅作为新候选格式的一次自然调用检查：", "", "```json", json.dumps(candidate, ensure_ascii=False, indent=2), "```", "",
              "费用估算（冻结价格，非账单）：" + str(sum(c["known_usage_estimated_cny"] for c in costs.values())) + " 元。"]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return {"report": str(output / "report.md"), "costs": costs, "api_calls_for_analysis": 0}


def run(path, *, resume, env_file):
    settings = json.loads((path / "settings.json").read_text())
    config = json.loads((path / "execution-config.json").read_text())
    binding = read_record(path / "measurement-plan.json")
    money = allocation(settings, config)
    if digest(settings) != binding["settings_sha256"] or digest(money) != binding["budget_sha256"]:
        raise ValueError("Measurement settings or budget changed after planning")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != binding["driver_sha256"]:
        raise ValueError("Measurement driver changed after planning")
    with run_lock(path):
        if all((path / name / "summary.json").exists() for name in ("execution", "rejudge")):
            if not resume:
                raise ValueError("Completed campaign exists; use explicit resume")
            return summarize(path, settings, inspect_run(path / "execution"), inspect_run(path / "rejudge"))
        if implementation_fingerprint() != binding["implementation"]:
            raise ValueError("Measurement source changed; create a new campaign")
        from rsi_lab.infra.environment import load_environment
        load_environment(env_file, ("DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "SSL_CERT_FILE"))
        planned = read_record(path / "execution-plan.json")
        if digest(planned) != binding["execution_plan_sha256"]:
            raise ValueError("Execution plan changed")
        execution = run_experiment(config, path / "execution", resume=resume, expected_plan=planned)
        source_before = inventory(path / "execution")
        next_config = rejudge_config(path, settings, config)
        next_plan = plan_experiment(next_config)
        if next_plan["evaluation_records_total"] != binding["rejudge"]["expected_source_answers"] * binding["rejudge"]["repeats"]:
            raise ValueError("Saved answer allocation changed")
        if not (path / "rejudge-config.json").exists():
            write(path / "rejudge-config.json", next_config)
        elif json.loads((path / "rejudge-config.json").read_text()) != next_config:
            raise ValueError("Rejudge configuration changed")
        save_record(path / "rejudge-plan.json", next_plan)
        judged = run_experiment(next_config, path / "rejudge", resume=resume, expected_plan=next_plan)
        if inventory(path / "execution") != source_before:
            raise ValueError("Rejudging changed source answers")
        inspect_run(path / "execution")
        inspect_run(path / "rejudge")
        return summarize(path, settings, execution, judged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "resume", "inspect"))
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    path = args.campaign.resolve()
    if args.action == "plan":
        result = prepare(path, json.load(sys.stdin))
    elif args.action == "inspect":
        for name in ("execution", "rejudge"):
            inspect_run(path / name)
        result = {"verified": True, "api_calls": 0}
    else:
        result = run(path, resume=args.action == "resume", env_file=args.env_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
