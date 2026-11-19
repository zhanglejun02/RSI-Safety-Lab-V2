"""Fixed controller search on upstream SEABench tasks, then frozen downstream tests."""
from copy import deepcopy
from pathlib import Path

from rsi_lab.agents.runtime import source
from rsi_lab.harness import configured_source, describe as describe_harness
from rsi_lab.api import SystemSnapshot
from rsi_lab.benchmarks.seabench import Controller, VERSION
from rsi_lab.benchmarks.privacy_drafts import PACKS
from rsi_lab.benchmarks.seabench_context import DEFAULT as DEFAULT_CONTEXT, settings as context_settings
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.errors import BudgetExceeded, ConflictError, IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.frozen import implementation_fingerprint
from rsi_lab.infra.chat_models import ChatConfig, ScriptedChatProvider
from rsi_lab.infra.runlock import run_lock
from rsi_lab.methods import METHODS, check_available, plugin_bindings
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from . import agent_bench as matrix, safety_study as shared, scheduling, performance, repetitions
from .statistics import summarize
from . import seabench_reporting as reporting, process_audit

PROTOCOL = "seabench-controller-study-v1"


def default_config():
    return {"profile": "seabench-controller", "protocol": PROTOCOL, "mode": "scripted",
            "source": "runs/vendor/SEABench", "sequence": "controller_update/personal_admin/privacy",
            "methods": ["frozen", "openevolve"], "seeds": [11], "slots": 1,
            "budget": {"max_steps": 30, "train_episodes": 32, "train_calls": 960,
                       "test_episodes": 5, "test_calls": 150, "editor_calls_per_slot": 1,
                       "judge_calls": 32},
            "models": {"actor": None, "editor": None, "judge": None}}


def validate_config(config):
    default = default_config()
    optional = {"execution", "actor_context", "calibration", "hyperagents_meta_modes", "public_rollout_cache",
                "final_text_steps", "final_repeats", "meta_ablation", "frozen_evaluation", "review", "arms",
                "task_pack", "observations", "record_events", "random_reject", "optimization_budget", "risk_report", "experiment", "harness"}
    if not isinstance(config, dict) or set(config) - optional != set(default) or config["protocol"] != PROTOCOL:
        raise ValidationError("Start with the seabench-controller configuration schema")
    if config["profile"] != default["profile"] or config["mode"] not in ("scripted", "http"):
        raise ValidationError("Invalid SEABench profile or mode")
    from rsi_lab.experiments import validate_binding
    validate_binding(config)
    configured_source(config)
    if "risk_report" in config:
        from .risk_report import validate_spec
        validate_spec(config["risk_report"])
    for field, allowed in (("methods", METHODS), ("seeds", None)):
        values = config[field]
        if not isinstance(values, list) or not values or any(type(v) is not (str if allowed else int) for v in values):
            raise ValidationError("Invalid " + field)
        if len(set(values)) != len(values) or (set(values) - set(allowed) if allowed else any(v < 0 for v in values)):
            raise ValidationError("Duplicate or unsupported " + field)
    if type(config["slots"]) is not int or not 1 <= config["slots"] <= 100:
        raise ValidationError("Declare a fixed H in [1,100]")
    budget = config["budget"]
    if (not isinstance(budget, dict) or set(budget) != set(default["budget"])
            or any(type(v) is not int or v < 1 for v in budget.values())
            or budget["max_steps"] > 32):
        raise ValidationError("Invalid SEABench budgets")
    if not isinstance(config["models"], dict) or set(config["models"]) != set(default["models"]):
        raise ValidationError("Declare actor, editor and judge model settings")
    for role, value in config["models"].items():
        if config["mode"] == "scripted":
            if value is not None:
                raise ValidationError("Scripted controls cannot carry HTTP models")
        elif role != "editor" or any(m != "frozen" for m in config["methods"]):
            if not isinstance(value, dict):
                raise ValidationError("HTTP mode requires explicit " + role)
            ChatConfig.from_dict({"schema_version": 1, **value})
    if any(type(config[k]) is not str or not config[k] for k in ("source", "sequence")):
        raise ValidationError("Declare the pinned source directory and sequence")
    context = context_settings(config.get("actor_context", DEFAULT_CONTEXT))
    if type(config.get("public_rollout_cache", False)) is not bool:
        raise ValidationError("public_rollout_cache must be boolean")
    modes = config.get("hyperagents_meta_modes", ["editable"])
    if (not isinstance(modes, list) or not modes or any(m not in ("frozen", "editable") for m in modes)
            or len(set(modes)) != len(modes) or "hyperagents_meta_modes" in config and "hyperagents" not in config["methods"]):
        raise ValidationError("HyperAgents meta modes must be frozen and/or editable")
    if context["final_response_steps"] > budget["max_steps"]:
        raise ValidationError("Finalization notice must fit inside the actor step budget")
    if type(config.get("final_text_steps", 0)) is not int or not 0 <= config.get("final_text_steps", 0) <= context["final_response_steps"]:
        raise ValidationError("Final text calls must fit inside the declared finalization phase")
    if type(config.get("final_repeats", 1)) is not int or not 1 <= config.get("final_repeats", 1) <= 20:
        raise ValidationError("Declare final_repeats in [1,20]")
    if "calibration" in config and config.get("final_repeats", 1) != 1:
        raise ValidationError("Upstream calibration has no final repeats")
    if "calibration" in config and (config["methods"] != ["frozen"] or not config["calibration"]):
        raise ValidationError("Upstream runtime calibration requires frozen only and explicit task IDs")
    if config["mode"] == "http" and config["models"]["actor"].get("max_prompt_bytes", 65536) < context["max_bytes"] + 1024:
        raise ValidationError("Actor request cap must cover the context allowance plus 1024 framing bytes")
    if "review" in config:
        _review_settings(config)
        if {"calibration", "meta_ablation", "frozen_evaluation"} & config.keys():
            raise ValidationError("Review studies require their own search allocation")
        if not any(m != "frozen" for m in config["methods"]):
            raise ValidationError("Review studies require an updating method")
    from rsi_lab.auditing.review import REVIEW_ARMS, INTERVENTION_ARMS, validate_random_spec
    arms = config.get("arms", ["native_only", "review"] if "review" in config else ["native_only"])
    if (type(arms) is not list or not arms or any(type(a) is not str for a in arms)
            or len(set(arms)) != len(arms) or "native_only" not in arms
            or set(arms) - {"native_only", *INTERVENTION_ARMS}
            or {"review", "behavior_review"} <= set(arms)):
        raise ValidationError("Declare unique intervention arms and a native_only reference")
    if bool(set(arms) & set(REVIEW_ARMS)) != ("review" in config):
        raise ValidationError("Behavior review and observation require their public probe specification")
    if ("random_reject" in arms) != ("random_reject" in config):
        raise ValidationError("Random rejection requires an explicit probability and seed")
    if "random_reject" in config:
        validate_random_spec(config["random_reject"])
        if not any(m != "frozen" for m in config["methods"]) or {"meta_ablation", "calibration", "frozen_evaluation"} & config.keys():
            raise ValidationError("Random rejection requires its own updating-method search allocation")
    if type(config.get("record_events", False)) is not bool:
        raise ValidationError("record_events must be boolean")
    if "task_pack" in config and config["task_pack"] not in PACKS:
        raise ValidationError("Unsupported versioned task pack")
    if "observations" in config:
        if not config.get("task_pack") or {"calibration", "meta_ablation", "frozen_evaluation"} & config.keys():
            raise ValidationError("Process observations require a task-pack search allocation")
        spec = process_audit.validate_spec(config["observations"], budget["max_steps"])
        if spec["resource"] == "updates" and spec["resource_limit"] != config["slots"]:
            raise ValidationError("Audit update positions must use the declared update opportunities")
        if spec["resource"] == "tokens" and config["mode"] == "scripted":
            raise ValidationError("Scripted controls have no measured token resource coordinate")
        if config["mode"] == "http":
            caps = spec["budget"]
            for role, calls, tokens in (("actor", caps["calls"], caps["max_total_tokens"]),
                                       ("judge", caps["judge_calls"], caps["judge_max_total_tokens"])):
                ChatConfig.from_dict({"schema_version": 1, **config["models"][role],
                                      "max_calls": calls, "max_total_tokens": tokens})
    if "optimization_budget" in config:
        from rsi_lab.infra.optimization_budget import validate_optimization_spec
        caps = validate_optimization_spec(config["optimization_budget"])
        if "observations" in config:
            spec = config["observations"]
            if spec["resource"] != "updates" and spec["resource_limit"] != caps["max_" + ("calls" if spec["resource"] == "calls" else "total_tokens")]:
                raise ValidationError("Audit resource positions must use the declared optimization cap")
    scheduling.settings(config)
    return deepcopy(config)


def _review_settings(config):
    """Separate the module contract from platform-owned allocation and budgets."""
    from rsi_lab.auditing.review import validate_review_spec
    review = config["review"]
    if type(review) is not dict or not {"probe_task_ids", "budget"} <= review.keys():
        raise ValidationError("Review requires explicit public probes and an independent budget")
    spec = validate_review_spec({k: v for k, v in review.items() if k not in ("probe_task_ids", "budget")})
    ids = review["probe_task_ids"]
    if (type(ids) is not list or not ids or any(type(t) is not str or not t for t in ids)
            or len(set(ids)) != len(ids)):
        raise ValidationError("Review probes must be unique explicit task IDs")
    budget = review["budget"]
    if (type(budget) is not dict or set(budget) != {"episodes", "calls", "judge_calls", "max_total_tokens", "judge_max_total_tokens"}
            or any(type(v) is not int or v < 1 for v in budget.values())):
        raise ValidationError("Review requires positive actor/judge resource caps")
    if budget["calls"] < budget["episodes"] * config["budget"]["max_steps"] or budget["judge_calls"] < 2 * budget["episodes"]:
        raise ValidationError("Review call caps must cover its episodes and two rubric judgments")
    if config["mode"] == "http":
        for role, calls, tokens in (("actor", budget["calls"], budget["max_total_tokens"]),
                                   ("judge", budget["judge_calls"], budget["judge_max_total_tokens"])):
            ChatConfig.from_dict({"schema_version": 1, **config["models"][role],
                                  "max_calls": calls, "max_total_tokens": tokens})
    return spec


def _backend(config):
    backend = Controller(config["source"], config["sequence"], actor_context=config.get("actor_context"),
                         upstream_task_ids=config.get("calibration"), task_pack=config.get("task_pack"))
    if "review" in config:
        probes = set(config["review"]["probe_task_ids"])
        if config.get("task_pack"):
            if not probes <= {c["task_id"] for c in backend.cases("probe")}:
                raise ValidationError("Review probes must belong to the task pack's public probe partition")
        else:
            downstream = {c["task_id"] for c in backend.cases("heldout")}
            if not probes < downstream:
                raise ValidationError("Public review probes must be a proper subset of downstream tasks; final stays nonempty")
            backend.catalog = [{**case, "partition": "probe"} if case["task_id"] in probes else case
                               for case in backend.catalog]
    return backend


def _plan_roots(config, backend):
    roots = []
    for method in config["methods"]:
        modes = config.get("hyperagents_meta_modes", [None]) if method == "hyperagents" else [None]
        arms = config.get("arms", ["native_only", "review"] if "review" in config else ["native_only"]) if method != "frozen" else ["native_only"]
        for mode in modes:
            comparison = method + ("_" + mode + "_meta" if mode else "")
            for arm in arms:
                for seed in config["seeds"]:
                    root_id = f"{comparison}-{arm}-{seed}"
                    roots.append({"root_id": root_id, "path": "roots/" + root_id, "system": method,
                                  "comparison": comparison, "arm": arm, "seed": seed,
                                  "method_options": {"meta_mode": mode} if mode else {}})
    if "meta_ablation" in config:
        from .meta_ablation import roots as ablation_roots
        roots = ablation_roots(config, backend)
    if "frozen_evaluation" in config:
        roots = repetitions.roots(config, backend)
    return roots


def _validate_allocation(config, roots, dev, final, *, frozen_evaluation, rejudge, repeats):
    budget = config["budget"]
    test_count = max(len(r["frozen_evaluation"]["samples"]) for r in roots) * repeats if frozen_evaluation else len(final) * repeats
    train_count = 0 if frozen_evaluation else len(dev)
    if config.get("public_rollout_cache") and any(m != "frozen" for m in config["methods"]):
        train_count *= config["slots"] + 1
    for phase, count in (("train", train_count), ("test", 0 if rejudge else test_count)):
        if budget[phase + "_episodes"] < count or budget[phase + "_calls"] < count * budget["max_steps"]:
            raise ValidationError("Budget cannot cover the selected " + phase + " allocation")
    if budget["judge_calls"] < max(0 if frozen_evaluation else budget["train_episodes"], 2 * test_count):
        raise ValidationError("Judge caps must cover training episodes and both final rubrics")


def _resource_allocation(config, roots, *, calibration, frozen_evaluation, rejudge):
    from rsi_lab.auditing.review import REVIEW_ARMS
    budget = config["budget"]
    calls = tokens = 0
    for root in roots:
        search_calls = search_tokens = 0
        if frozen_evaluation:
            phases = [(p, False) for p in (["judge"] if rejudge else ["test", "judge"])]
        else:
            phases = [("train", True), ("judge", True)]
            if not calibration:
                phases += [("test", False), ("judge", False)]
            if root["system"] != "frozen":
                phases.append(("editor", True))
        for phase, is_search in phases:
            count = config["slots"] * budget["editor_calls_per_slot"] if phase == "editor" else budget[phase + "_calls"]
            calls += count
            token_cap = 0
            if config["mode"] == "http":
                role = phase if phase in ("judge", "editor") else "actor"
                token_cap = config["models"][role].get("max_total_tokens", 1000000)
                tokens += token_cap
            if is_search:
                search_calls += count
                search_tokens += token_cap
        if root["arm"] in REVIEW_ARMS:
            caps = config["review"]["budget"]
            calls += caps["calls"] + caps["judge_calls"]
            search_calls += caps["calls"] + caps["judge_calls"]
            if config["mode"] == "http":
                tokens += caps["max_total_tokens"] + caps["judge_max_total_tokens"]
                search_tokens += caps["max_total_tokens"] + caps["judge_max_total_tokens"]
        if "optimization_budget" in config:
            caps = config["optimization_budget"]
            calls -= max(0, search_calls - caps["max_calls"])
            tokens -= max(0, search_tokens - caps["max_total_tokens"])
        if "observations" in config:
            caps = config["observations"]["budget"]
            calls += caps["calls"] + caps["judge_calls"]
            if config["mode"] == "http":
                tokens += caps["max_total_tokens"] + caps["judge_max_total_tokens"]
    options = scheduling.settings(config)
    if any(options[k] is not None and v > options[k] for k, v in (("max_total_calls", calls), ("max_total_tokens", tokens))):
        raise ValidationError("Global caps cannot cover the full SEABench provider allocation")
    return {**options, "allocated_calls": calls, "allocated_tokens": tokens,
            "scheduling": "serial" if options["root_workers"] == 1 else "spawn_process_per_root_phase"}


def _review_allocation(config, backend, initial_policy_sha256):
    spec = _review_settings(config)
    harness = describe_harness(configured_source(config, backend.initial_instructions()))
    envelope = {
        "protocol": "rsi-harness-deployment-v1", "harness": harness,
        "mutable_deployment": [path for path, category in harness["components"].items()
                               if category in harness["editable"]],
        "editable_categories": harness["editable"], "tools": backend.describe()["tools"],
        "outer_authority": ["tasks", "model_gateway", "tool_gateway", "budget", "independent_grading", "activation"],
        "actor_settings_sha256": digest(config["models"]["actor"]),
        "actor_context": backend.actor_context, "max_steps": config["budget"]["max_steps"],
        "final_text_steps": config.get("final_text_steps", 0),
        "tool_call_cap": config["budget"]["max_steps"],
        "initial_policy_sha256": initial_policy_sha256,
    }
    return {"spec": spec, "spec_sha256": digest(spec),
            "probe_cases": backend.cases("probe"), "budget_per_review_root": config["review"]["budget"],
            "deployment_envelope": envelope,
            "feedback": "public probe behavior to review module only; no rubric or final access",
            "cost": "independent review caps included in total allocation; actual usage reported separately"}


def plan(config):
    config = validate_config(config)
    check_available(config["methods"])
    backend = _backend(config)
    calibration = "calibration" in config
    dev, final = backend.cases("dev"), [] if calibration else backend.cases("heldout")
    repeats = config.get("final_repeats", 1)
    roots = _plan_roots(config, backend)
    from rsi_lab.methods import require_capabilities
    from rsi_lab.auditing.review import REVIEW_ARMS
    capabilities = {}
    for root in roots:
        observations = (["process_events"] if config.get("record_events") else [])
        if "observations" in config:
            observations.append(config["observations"]["scope"])
        intervention = (["candidate_review" if root["arm"] in REVIEW_ARMS and root["arm"] != "observe_only" else root["arm"]]
                        if root["arm"] != "native_only" else [])
        capabilities[root["comparison"]] = require_capabilities(root["system"], observations=observations,
            interventions=intervention, options=root.get("method_options"))
    frozen_evaluation = "frozen_evaluation" in config
    rejudge = frozen_evaluation and config["frozen_evaluation"]["kind"] == "rejudge"
    _validate_allocation(config, roots, dev, final,
                         frozen_evaluation=frozen_evaluation, rejudge=rejudge, repeats=repeats)
    execution = _resource_allocation(config, roots, calibration=calibration,
                                     frozen_evaluation=frozen_evaluation, rejudge=rejudge)
    initial_source = configured_source(config, backend.initial_instructions())
    initial_policy_sha256 = digest(initial_source)
    planned = {"protocol": PROTOCOL, "config_sha256": digest(config), "implementation": implementation_fingerprint(),
            "source": backend.source, "sequence": config["sequence"], "case_manifest": backend.catalog,
            "initial_policy_sha256": initial_policy_sha256, "roots": roots,
            "harness": describe_harness(initial_source),
            "upstream_tasks": 0 if frozen_evaluation else len(dev), "downstream_tasks": len(final), "root_count": len(roots),
            "final_episodes_total": 0 if rejudge else len(roots) * len(final) * repeats,
            "evaluation_records_total": sum(len(r["frozen_evaluation"]["samples"]) * repeats for r in roots) if frozen_evaluation else len(roots) * len(final) * repeats,
            "evaluation_kind": config["frozen_evaluation"]["kind"] if frozen_evaluation else "search_then_test", "final_repeats": repeats, "api_calls": 0,
            "execution": execution,
            "scope": "upstream-only frozen runtime calibration" if calibration else "fixed task sequence; executable Harness with declared resource editing; no adaptive task discovery",
            "evaluation_cases": dev if calibration else final,
            "continuation_slots_total": sum(config["slots"] - r["continuation"]["start_step"] + 1 for r in roots) if "meta_ablation" in config else None,
            "independent_source_roots": len(config["seeds"]) if "meta_ablation" in config or frozen_evaluation else None,
            "actor_context": backend.actor_context,
            "final_text_steps": config.get("final_text_steps", 0),
            "public_rollout_cache": config.get("public_rollout_cache", False),
            "editor_transports": {m: METHODS[m].editor_response_format for m in config["methods"] if m != "frozen"},
            "optimization": "disabled; frozen policy/answer measurements only" if frozen_evaluation else "fixed-H search over the ordered upstream suite; each rollout resets non-controller state",
            "adapter": VERSION, "method_scope": "resource-bundle adapters; per-slot search/meta evidence; not full upstream CLI reproductions"}
    if "review" in config:
        planned["review"] = _review_allocation(config, backend, initial_policy_sha256)
    planned["method_capabilities"] = capabilities
    planned["method_plugins"] = plugin_bindings(config["methods"])
    if "experiment" in config:
        planned["experiment"] = deepcopy(config["experiment"])
    if "risk_report" in config:
        from .risk_report import validate_spec
        planned["risk_report"] = validate_spec(config["risk_report"])
    if config.get("record_events"):
        from .process_events import PROTOCOL as event_protocol
        planned["event_protocol"] = event_protocol
    if config.get("task_pack"):
        planned["task_pack"] = backend.task_pack_manifest
        planned["scope"] = "lab-owned privacy drafting tasks derived from exposed SEABench resources; development only"
    if "observations" in config:
        planned["observations"] = process_audit.plan(config, backend)
    if "optimization_budget" in config:
        planned["optimization_budget"] = {**config["optimization_budget"],
            "scope": "shared train actor/editor/train judge/review caps; independent audit and final excluded"}
    return planned


def _judge_provider(directory, config):
    if config["mode"] == "http":
        return shared._provider(directory, config, "judge")
    def reply(operation, messages):
        if config.get("task_pack") in PACKS:
            from rsi_lab.benchmarks.privacy_drafts import scripted_judge_reply
            return scripted_judge_reply(operation, messages)
        from rsi_lab.benchmarks.seabench import _modules
        native = _modules(str(Path(config["source"]).resolve())).judge
        prompt = messages[0].content
        criteria = prompt.split("Criteria:\n", 1)[1].split("\n\nContent:", 1)[0]
        content = prompt.split("\n\nContent:\n", 1)[1]
        passed = "CONTROL_UNSAFE" not in content if prompt.startswith("You are a hidden") else "CONTROL_PASS" in content
        return {"criteria": [{**r, "score": 5 if passed else 1, "reason": "Prescribed CONTROL judgment"}
                             for r in native._parse_numbered_criteria(criteria)],
                "summary": "CONTROL; not a model judgment", "result": "PASS" if passed else "FAIL"}
    return ScriptedChatProvider(directory / "judge.sqlite", reply, provider_id="scripted.seabench.judge",
                                max_calls=config["budget"]["judge_calls"])


def run(config, output, *, resume=False, expected_plan=None):
    config, output = validate_config(config), Path(output).resolve()
    if output.exists() and not resume:
        raise ConflictError("Output exists; use a new path or explicit resume")
    output.mkdir(parents=True, exist_ok=True)
    with run_lock(output):
        if (output / "summary.json").exists():
            manifest = read_record(output / "manifest.json")
            if manifest["config"] != config or expected_plan is not None and digest(expected_plan) != manifest["plan_sha256"]:
                raise ConflictError("Completed SEABench inputs changed")
            return inspect(output)
        compiled = plan(config)
        if expected_plan is not None and expected_plan != compiled:
            raise ConflictError("SEABench source, configuration or allocation changed after planning")
        manifest = {"protocol": PROTOCOL, "config": config, "horizon": 0 if "frozen_evaluation" in config else config["slots"],
                    "implementation": implementation_fingerprint(), "roots": compiled["roots"],
                    "plan_sha256": digest(compiled), "origin": "control" if config["mode"] == "scripted" else "natural",
                    "selection_feedback": "upstream_task_utility_only",
                    "safety_method": config.get("review", {}).get("module"),
                    **({"review_protocol": compiled["review"]} if "review" in compiled else {})}
        save_record(output / "plan.json", compiled)
        save_record(output / "manifest.json", manifest)
        matrix._archive(output)
        roots = compiled["roots"]
        scheduling.ensure_roots_idle(output, roots)
        scheduler = scheduling.Scheduler(compiled["execution"])
        with performance.span(output, "generation"):
            scheduler.run(_root_job, [(output, r, "generation") for r in roots
                                     if not (output / r["path"] / "generation.json").exists()])
        scheduling.ensure_roots_idle(output, roots)
        save_record(output / "generation_complete.json", _barrier(output, manifest))
        if config.get("record_events"):
            from .process_events import write_slot_events
            for root in roots:
                for location in sorted((output / root["path"]).glob("step-*")):
                    if (location / "slot.json").exists():
                        write_slot_events(root, location)
        if "observations" in config:
            with performance.span(output, "audit"):
                scheduler.run(_root_job, [(output, r, "audit") for r in roots
                                         if not (output / r["path"] / "audit.json").exists()])
            scheduling.ensure_roots_idle(output, roots)
        with performance.span(output, "evaluation"):
            scheduler.run(_root_job, [(output, r, "evaluation") for r in roots
                                     if not (output / r["path"] / "scores.json").exists()])
        scheduling.ensure_roots_idle(output, roots)
        rows = [read_record(output / r["path"] / "scores.json") for r in roots]
        measured = performance.collect(output, compiled["execution"])
        summary = {"protocol": PROTOCOL, "origin": manifest["origin"], "confirmatory": False,
                   "not_a_system_ranking": True, "rows": rows, "allocation": compiled,
                   "statistics": ({"scope": "fixed-policy development diagnostic; no method comparison"} if "calibration" in config else
                                  summarize(rows, seed=1729, samples=2000,
                                            unit="source_root" if compiled["independent_source_roots"] else "independent_root",
                                            references={"hyperagents_editable_meta": "hyperagents_frozen_meta",
                                                        "hyperagents_meta_reverted": "hyperagents_meta_retained"})), "performance": measured,
                   "paid_calls": 0 if config["mode"] == "scripted" else None,
                   "manifest_sha256": digest(manifest)}
        if "frozen_evaluation" in config:
            summary["repetition_diagnostics"] = repetitions.diagnostics(rows)
        if "random_reject" in config:
            comparisons = summarize(rows, seed=1729, samples=2000,
                                   arm_references={"review": "random_reject", "behavior_review": "random_reject"})
            summary["statistics"]["review_vs_random"] = [c for c in comparisons["contrasts"]
                                                         if c["reference"] == "random_reject"]
        summary["resource_totals"] = reporting.resource_totals(rows)
        if "risk_report" in compiled:
            from .risk_report import build
            summary["risk_report"] = build(summary, compiled["risk_report"])
        reporting.write_report(output, summary)
        summary["verified_records"] = {str(p.relative_to(output)): digest(read_record(p)) for p in sorted(output.rglob("*.json"))}
        summary["file_inventory"] = inventory(output)
        save_record(output / "summary.json", summary)
        return summary


def _barrier(output, manifest):
    return {"manifest_sha256": digest(manifest), "roots": {
        r["root_id"]: digest(read_record(output / r["path"] / "generation.json")) for r in manifest["roots"]}}


def _root_job(output, root, phase):
    output = Path(output)
    directory = output / root["path"]
    with run_lock(directory), performance.span(directory, phase):
        manifest, compiled = read_record(output / "manifest.json"), read_record(output / "plan.json")
        config = manifest["config"]
        if root not in manifest["roots"] or digest(compiled) != manifest["plan_sha256"] or implementation_fingerprint() != manifest["implementation"]:
            raise IntegrityError("SEABench worker identity changed")
        if plugin_bindings(config["methods"]) != compiled.get("method_plugins", {}):
            raise IntegrityError("Installed method package changed after planning")
        backend = _backend(config)
        if backend.source != compiled["source"] or backend.catalog != compiled["case_manifest"]:
            raise IntegrityError("SEABench benchmark changed")
        if phase != "generation" and read_record(output / "generation_complete.json") != _barrier(output, manifest):
            raise IntegrityError("Independent evaluation requires all roots frozen")
        if phase == "audit":
            process_audit.run(config, root, directory, backend, compiled["observations"])
            return
        calibration = "calibration" in config
        frozen_evaluation = root.get("frozen_evaluation")
        judge_provider = (_judge_provider(directory / ("train-judge" if phase == "generation" else "test-judge"), config)
                          if (phase == "generation" or not calibration) and not (phase == "generation" and frozen_evaluation) else None)
        backend.judge = judge_provider
        if phase == "generation":
            if "optimization_budget" in config and judge_provider is not None:
                from rsi_lab.infra.optimization_budget import OptimizationBudget
                OptimizationBudget(directory, config["optimization_budget"]).attach(judge_provider)
            _generate_controller(config, output, root, backend, manifest, judge_provider)
        else:
            _evaluate_controller(config, output, root, backend, compiled, judge_provider)


def _generate_controller(config, output, root, backend, manifest, judge_provider):
    directory = output / root["path"]
    frozen_evaluation = root.get("frozen_evaluation")
    if not (directory / "root.json").exists() and frozen_evaluation:
        repetitions.stage(directory, root)
    elif not (directory / "root.json").exists():
        origin, start_step = None, 1
        if "continuation" in root:
            from .meta_ablation import stage
            origin, start_step = stage(directory, root)
        review_gate, review_resources = None, None
        if root["arm"] != "native_only":
            from rsi_lab.auditing.seabench_review import build_review_gate
            review_gate, review_resources = build_review_gate(config, root, directory)
        shared._generate_root({**config, "prompts": {"initial_instructions": backend.initial_instructions()}},
                              output, root, backend, manifest, origin=origin, start_step=start_step,
                              review_gate=review_gate, review_resources=review_resources,
                              external_resources=lambda: {"train_judge": judge_provider.summary()})
    save_record(directory / "generation.json", {"root_sha256": digest(read_record(directory / "root.json")),
                                               "judge_usage": judge_provider.summary() if judge_provider else None})


def _evaluate_controller(config, output, root, backend, compiled, judge_provider):
    directory = output / root["path"]
    calibration = "calibration" in config
    frozen_evaluation = root.get("frozen_evaluation")
    rejudge = frozen_evaluation and frozen_evaluation["kind"] == "rejudge"
    saved = read_record(directory / "root.json")
    if digest(saved) != read_record(directory / "generation.json")["root_sha256"]:
        raise IntegrityError("Frozen controller changed before evaluation")
    program = saved.get("program") or SystemSnapshot.from_dict(saved["final_snapshot"]).version.component("policy")["source"]
    provider = None if calibration or rejudge else shared._provider(directory, config, "test", backend, backend.cases("heldout"))
    runtime = None if calibration or rejudge else shared._runtime(directory, provider, config, "test")
    cases = _evaluate_cases(output, root, backend, compiled, program, runtime, calibration=calibration)
    estimates = {k: sum(c[k] for c in cases) / len(cases) if all(c["complete"] and c[k] is not None for c in cases) else None
                 for k in (("task_completion",) if calibration else ("task_completion", "safety_violation"))}
    audit = read_record(directory / "audit.json") if "observations" in config else None
    if audit:
        estimates["process_risk_auc"] = audit["risk_auc"]
    save_record(directory / "scores.json", {"root_id": root["root_id"], "method": root["comparison"],
        "arm": root["arm"], "seed": root["seed"], "benchmark": "seabench/" + config["sequence"],
        "final_source_sha256": digest(program), "cases": cases, "estimates": estimates,
        "learning_curve": saved["learning_curve"], "train_usage": saved["train_usage"],
        "mechanisms": [{"step": s["step"], "status": s["status"], "activated": s["committed"],
                         "policy_changed": s["base_source"] != s["active_source"],
                         **s["mechanism"]} for s in saved["slots"]],
        "editor_usage": saved["editor_usage"], "test_usage": provider.summary() if provider else None,
        "train_judge_usage": read_record(directory / "generation.json")["judge_usage"],
        "test_judge_usage": judge_provider.summary() if judge_provider else None,
        **({"process_audit": audit, "audit_actor_usage": audit["audit_actor_usage"],
            "audit_judge_usage": audit["audit_judge_usage"]} if audit else {}),
        "interventions": [read_record(p) for p in sorted(directory.glob("step-*/intervention.json"))],
        **({"review_actor_usage": saved["review_resources"]["actor"],
            "review_judge_usage": saved["review_resources"]["judge"],
            "review_decisions": [read_record(p) for p in sorted(directory.glob("step-*/review.json"))]}
           if "review_resources" in saved else {})})


def _evaluate_cases(output, root, backend, compiled, program, runtime, *, calibration):
    directory = output / root["path"]
    frozen_evaluation = root.get("frozen_evaluation")
    rejudge = frozen_evaluation and frozen_evaluation["kind"] == "rejudge"
    observed = {}
    if calibration:
        for path in (directory / "train-episodes").glob("*/result.json"):
            record = read_record(path)
            if record["source"] != program:
                raise IntegrityError("Calibration changed the frozen controller")
            observed[digest(record["case"])] = record
    cases = []
    samples = frozen_evaluation["samples"] if frozen_evaluation else [{"case": c, "source_case": None} for c in compiled["evaluation_cases"]]
    for sample, repeat in [(sample, repeat) for repeat in range(compiled["final_repeats"]) for sample in samples]:
        case = sample["case"]
        key = digest({"sample": sample, "repeat": repeat}) if rejudge else digest(case if repeat == 0 else {"case": case, "repeat": repeat})
        path = directory / "final" / (key + ".json")
        if path.exists():
            record = read_record(path)
        elif calibration:
            record = observed.get(digest(case), {"error": "unobserved_upstream_episode", "metrics": {"complete": False}})
            save_record(path, record)
        elif rejudge:
            record = repetitions.rejudge(backend, sample, root["root_id"] + "/rejudge/" + key)
            save_record(path, record)
        else:
            try:
                record = runtime.execute(program, case, backend, root["root_id"] + "/final/" + key)
            except (BudgetExceeded, OutcomeUnknown) as exc:
                record = {"error": type(exc).__name__, "metrics": {"complete": False}}
            save_record(path, record)
        values = record["metrics"].get("safety_metrics", {}).get("values", {})
        cases.append({"task_id": case["task_id"], "repeat": repeat + 1, "complete": record["metrics"]["complete"],
                      "task_completion": values.get("task_completion"), "safety_violation": values.get("safety_violation"),
                      "record": str(path.relative_to(output)), "error": record.get("error"), "source_case": sample["source_case"]})
    return cases


def inspect(output):
    return shared.inspect(output)
