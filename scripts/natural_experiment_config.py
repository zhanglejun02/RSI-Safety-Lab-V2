"""Render the Bash launcher's settings into the existing public experiment API.

This helper only plans; it creates no model providers and makes no API calls.
"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


def validate_kimi_recipe(model):
    """Guard the tested direct-provider recipe, not every Kimi deployment."""
    if (model.get("model") == "kimi-k2.6"
            and urlsplit(model.get("base_url", "")).hostname in {"api.moonshot.cn", "api.moonshot.ai"}):
        mode = model.get("thinking_mode")
        if mode not in ("disabled", "enabled") or model.get("temperature") != (1.0 if mode == "enabled" else 0.6):
            raise ValueError("Use the validated Kimi recipe: explicit thinking_mode=disabled with temperature=0.6, or enabled with temperature=1.0")


def provider_cost(tokens, calls, output_cap, rates):
    """Worst allocation cost at the declared uncached input/output rates."""
    incoming, outgoing = (Decimal(str(rates[k])) for k in ("input", "output"))
    if not incoming.is_finite() or not outgoing.is_finite() or min(incoming, outgoing) < 0:
        raise ValueError("Rates must be finite nonnegative CNY per million tokens")
    # If output is cheaper than input, treating every token as input is safer.
    extra = max(Decimal(0), outgoing - incoming)
    return (tokens * incoming + min(tokens, calls * output_cap) * extra) / 1000000


def build(settings, *, enforce_budget=True):
    """Expand episode counts and bound every distinct phase/root provider."""
    from importlib.resources import files

    s = deepcopy(settings)
    for model in s["models"].values():
        validate_kimi_recipe(model)
    from rsi_lab.benchmarks.privacy_drafts import PACKS
    if s["task_pack"] not in PACKS:
        raise ValueError("Declare a supported task pack before deriving episode budgets")
    pack = json.loads(files("rsi_lab.data").joinpath(PACKS[s["task_pack"]]).read_text())
    tasks = pack["tasks"]
    dev_count = sum(t["evaluation_phase"] == "dev" for t in tasks)
    final_count = sum(t["evaluation_phase"] == "final" for t in tasks)
    train_episodes = dev_count * (s["slots"] + 1)
    test_episodes = final_count * s["final_repeats"]
    steps = s["max_steps"]
    budget = {"max_steps": steps, "train_episodes": train_episodes,
              "train_calls": train_episodes * steps, "test_episodes": test_episodes,
              "test_calls": test_episodes * steps, "editor_calls_per_slot": s["editor_calls_per_slot"],
              "judge_calls": max(train_episodes, 2 * test_episodes)}
    config = {
        "profile": "seabench-controller", "protocol": "seabench-controller-study-v1", "mode": "http",
        "source": str(Path(s["source"]).resolve()), "sequence": "controller_update/personal_admin/privacy",
        "task_pack": s["task_pack"], "methods": s["methods"], "arms": s["arms"], "seeds": s["seeds"],
        "slots": s["slots"], "budget": budget, "models": s["models"],
        "public_rollout_cache": True, "record_events": True,
        "actor_context": s["actor_context"], "final_text_steps": s["final_text_steps"],
        "final_repeats": s["final_repeats"],
        "risk_report": {"protocol": "rsi-risk-report-v1", "calibration": {"confirmed": False, "evidence_ref": None},
                        "min_matched_roots": 5, "risk_margin": 0.0},
        "execution": {"root_workers": s["root_workers"], "max_in_flight": s["max_in_flight"],
                      "requests_per_minute": s["requests_per_minute"], "cooldown_seconds": 30},
    }
    if "hyperagents" in s["methods"]:
        config["hyperagents_meta_modes"] = s["hyperagents_meta_modes"]
    if s["harness_directory"]:
        from rsi_lab import adapt
        config["harness"] = {"source": adapt(s["harness_directory"]).dumps()}
    review_arms = {"review", "behavior_review", "observe_only"}
    if review_arms.intersection(s["arms"]):
        if s["review_scope"] != "deployed_policy":
            raise ValueError("This launcher bounds deployed_policy review; broader scopes need explicit policy-count budgets")
        # Each slot reviews a baseline and candidate on every public probe.
        episodes = 2 * len(s["probe_task_ids"]) * s["slots"]
        config["review"] = {
            "protocol": "rsi-review-v1", "module": "public-behavior-regression-v1", "module_version": 1,
            "scope": s["review_scope"], "rollback": "candidate_snapshot_not_committed",
            "parameters": {"max_risk_increase": s["max_risk_increase"], "max_utility_drop": s["max_utility_drop"]},
            "probe_task_ids": s["probe_task_ids"],
            "budget": {"episodes": episodes, "calls": episodes * steps, "judge_calls": 2 * episodes,
                       "max_total_tokens": s["review_actor_tokens"], "judge_max_total_tokens": s["review_judge_tokens"]},
        }
    if "random_reject" in s["arms"]:
        config["random_reject"] = {"protocol": "rsi-random-reject-v1", "probability": s["random_reject_probability"],
                                   "seed": s["seeds"][0]}
    # A common upper cap covers all declared search providers, including review.
    # The first pilot matches available search opportunities; review costs extra.
    search_calls = budget["train_calls"] + budget["judge_calls"] + s["slots"] * s["editor_calls_per_slot"]
    search_tokens = sum(s["models"][r]["max_total_tokens"] for r in ("actor", "editor", "judge"))
    if "review" in config:
        rb = config["review"]["budget"]
        search_calls += rb["calls"] + rb["judge_calls"]
        search_tokens += rb["max_total_tokens"] + rb["judge_max_total_tokens"]
    config["optimization_budget"] = {"max_calls": search_calls, "max_total_tokens": search_tokens}
    if s["enable_audit"]:
        episodes = len(s["audit_task_ids"]) * len(s["audit_fractions"]) * s["audit_repeats"]
        audit_resource = s.get("audit_resource", "calls")
        if audit_resource not in ("calls", "updates"):
            raise ValueError("Audit resource must be calls or updates")
        config["observations"] = {
            "protocol": "rsi-process-audit-v2" if audit_resource == "updates" else "rsi-process-audit-v1",
            "scope": "deployed_policy", "fractions": s["audit_fractions"],
            "resource": audit_resource, "resource_limit": s["slots"] if audit_resource == "updates" else search_calls,
            "task_ids": s["audit_task_ids"],
            "repeats": s["audit_repeats"], "max_policies": 1, "risk_tolerance": 0.1,
            "budget": {"episodes": episodes, "calls": episodes * steps, "judge_calls": 2 * episodes,
                       "max_total_tokens": s["audit_actor_tokens"], "judge_max_total_tokens": s["audit_judge_tokens"]},
        }
    allocations = []

    def add(root, phase, role, calls, tokens):
        cap = s["models"][role]["max_output_tokens"]
        cost = provider_cost(tokens, calls, cap, s["rates_cny_per_million"][role])
        allocations.append({"root": root, "phase": phase, "role": role, "max_calls": calls,
                            "max_total_tokens": tokens, "max_output_tokens": cap, "cost_bound_cny": float(cost)})

    for method in s["methods"]:
        modes = s["hyperagents_meta_modes"] if method == "hyperagents" else [None]
        for mode in modes:
            for arm in (["native_only"] if method == "frozen" else s["arms"]):
                for seed in s["seeds"]:
                    root = f"{method}{'_' + mode + '_meta' if mode else ''}-{arm}-{seed}"
                    for phase, role, calls in (("train", "actor", budget["train_calls"]),
                            ("test", "actor", budget["test_calls"]), ("train-judge", "judge", budget["judge_calls"]),
                            ("test-judge", "judge", budget["judge_calls"])):
                        add(root, phase, role, calls, s["models"][role]["max_total_tokens"])
                    if method != "frozen":
                        add(root, "editor", "editor", s["slots"] * s["editor_calls_per_slot"], s["models"]["editor"]["max_total_tokens"])
                    for phase, enabled in (("review", arm in review_arms), ("observations", s["enable_audit"])):
                        if enabled:
                            caps = config[phase]["budget"]
                            add(root, phase + "-actor", "actor", caps["calls"], caps["max_total_tokens"])
                            add(root, phase + "-judge", "judge", caps["judge_calls"], caps["judge_max_total_tokens"])
    bound = sum(Decimal(str(a["cost_bound_cny"])) for a in allocations)
    previous, buffer = (Decimal(str(s[k])) for k in ("previous_spend_cny", "cost_buffer_cny"))
    limit = None if s["budget_cny"] is None else Decimal(str(s["budget_cny"]))
    if (any(not v.is_finite() or v < 0 for v in (previous, buffer))
            or limit is not None and (not limit.is_finite() or limit < 0)):
        raise ValueError("Budget, previous spend and buffer must be finite nonnegative amounts")
    within_budget = limit is None or bound + previous + buffer <= limit
    if enforce_budget and not within_budget:
        raise ValueError(f"Allocation cost {bound} + previous {previous} + buffer {buffer} exceeds CNY {limit}; reduce the settings before starting")
    config["execution"].update(max_total_calls=sum(a["max_calls"] for a in allocations),
                               max_total_tokens=sum(a["max_total_tokens"] for a in allocations))
    costs = {"protocol": "natural-pilot-budget-v1", "cost_bound_cny": float(bound),
             "previous_spend_cny": float(previous), "budget_cny": None if limit is None else float(limit), "cost_buffer_cny": float(buffer),
             "within_budget": within_budget, "required_total_cny": float(bound + previous + buffer),
             "additional_budget_cny": 0.0 if limit is None else float(max(Decimal(0), bound + previous + buffer - limit)),
             "rates_cny_per_million": s["rates_cny_per_million"], "rates_checked_on": s["rates_checked_on"],
             "pricing_sources": s["pricing_sources"], "allocations": allocations,
             "assumptions": "Uncached peak input rates; every provider may spend its token cap; output bounded by calls times output cap. Server token overruns and pricing changes are not a verified invoice guarantee. Unknown calls retain reservations. No automatic retries."}
    return config, costs


def main():
    from rsi_lab.agent_bench import plan_experiment
    from rsi_lab.infra.records import save_record
    from rsi_lab.serialization import digest

    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--estimate", action="store_true", help="Plan only; permit an over-budget allocation without authorizing dispatch")
    parser.add_argument("--check-budget", action="store_true", help="Check frozen settings before dispatch")
    args = parser.parse_args()
    directory = args.directory
    settings = json.loads((directory / "settings.json").read_text()) if args.check_budget else json.load(sys.stdin)
    config, costs = build(settings, enforce_budget=not args.estimate)
    costs["settings_sha256"] = digest(settings)
    if args.check_budget:
        saved_costs = json.loads((directory / "budget.json").read_text())
        if any(costs.get(key) != value for key, value in saved_costs.items()):
            raise ValueError("Frozen budget or settings changed; create a new plan")
        if config != json.loads((directory / "config.json").read_text()):
            raise ValueError("Frozen configuration differs from the budgeted settings")
        return
    plan = plan_experiment(config)
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()  # Never overwrite a previous plan or completed experiment.
    for name, value in (("settings.json", settings), ("config.json", config), ("budget.json", costs)):
        with (directory / name).open("x") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    save_record(directory / "plan.json", plan)
    print(json.dumps({"roots": plan["root_count"], "slots": config["slots"], "final_episodes": plan["final_episodes_total"],
                      "cost_bound_cny": costs["cost_bound_cny"], "previous_spend_cny": costs["previous_spend_cny"],
                      "within_budget": costs["within_budget"], "required_total_cny": costs["required_total_cny"],
                      "additional_budget_cny": costs["additional_budget_cny"],
                      "implementation": plan["implementation"], "api_calls": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    from rsi_lab.errors import LabError
    try:
        main()
    except (ValueError, LabError) as exc:
        print(f"ConfigurationError: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
