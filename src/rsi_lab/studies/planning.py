"""Pure allocation accounting for a selected catalog, never benchmark execution."""
from collections import Counter
from copy import deepcopy

from rsi_lab.agents.runtime import DEFAULT_INSTRUCTIONS, source
from rsi_lab.errors import ValidationError
from rsi_lab.frozen import implementation_fingerprint
from rsi_lab.serialization import digest
from .scheduling import allocation


def study_scope(config, backend):
    declared = config.get("study")
    if declared is None:
        return {"scope": "legacy_unspecified", "primary_metric": None,
                "interpretation": "No unseen-task or full-benchmark coverage claim is registered."}
    required = {"scope", "primary_metric", "primary_attack_ids", "selection_reason", "screened_tasks", "excluded_tasks"}
    if not isinstance(declared, dict) or set(declared) != required:
        raise ValidationError("Study scope requires endpoint, selection reason, screening history and exclusions")
    if declared["scope"] not in ("development", "screened_pool", "unseen_tasks"):
        raise ValidationError("Unknown study scope")
    if declared["primary_metric"] not in ("clean_utility", "attacked_utility", "attack_success_rate"):
        raise ValidationError("Register one primary metric without combining utility and safety")
    if not isinstance(declared["selection_reason"], str) or not declared["selection_reason"].strip():
        raise ValidationError("Explain the frozen selection before execution")
    selected = {(c["suite"], c["task_id"]) for c in backend.catalog}
    heldout = {(c["suite"], c["task_id"]) for c in backend.cases("heldout")}
    from rsi_lab.benchmarks.agentdojo_suite import available_catalog
    native_ids = available_catalog()["suites"]
    seen = set()
    for field in ("screened_tasks", "excluded_tasks"):
        entries = declared[field]
        if not isinstance(entries, list):
            raise ValidationError(field + " must be an explicit list")
        unique = set()
        for entry in entries:
            keys = {"suite", "task_id"} | ({"reason"} if field == "excluded_tasks" else set())
            if not isinstance(entry, dict) or set(entry) != keys or any(not isinstance(entry[k], str) or not entry[k].strip() for k in keys):
                raise ValidationError("Invalid " + field + " record")
            key = (entry["suite"], entry["task_id"])
            if entry["suite"] not in native_ids or entry["task_id"] not in native_ids[entry["suite"]]["task_ids"]:
                raise ValidationError("Unknown native task in exclusion/history declarations")
            if key in unique or field == "excluded_tasks" and key in selected:
                raise ValidationError("Duplicate or selected task in exclusion/history declarations")
            unique.add(key)
        if field == "screened_tasks":
            seen = unique
    if declared["scope"] == "unseen_tasks" and heldout & seen:
        raise ValidationError("Previously screened tasks cannot be declared unseen heldout tasks")
    attacks = declared["primary_attack_ids"]
    available = {c["attack"] for c in backend.cases("heldout") if c["attack_present"]}
    if (not isinstance(attacks, list) or any(type(a) is not str for a in attacks)
            or len(set(attacks)) != len(attacks) or set(attacks) - available):
        raise ValidationError("Primary attack IDs must belong to the selected final allocation")
    if declared["primary_metric"] != "clean_utility" and not attacks:
        raise ValidationError("Declare the attack variants for the primary safety/attacked-utility endpoint")
    if declared["primary_metric"] == "clean_utility" and attacks:
        raise ValidationError("Clean-utility primary endpoint must not select attack variants")
    return deepcopy(declared)


def compile_plan(config, backend, external):
    roots = [{"root_id": f"{method}-{arm}-{seed}", "path": f"roots/{method}-{arm}-{seed}",
              "system": method, "arm": arm, "seed": seed}
             for method in config["methods"]
             for arm in (["native_only"] if method == "frozen" else config["arms"])
             for seed in config["seeds"]]
    partitions = {}
    for partition in ("dev", "probe", "heldout"):
        cases = backend.cases(partition)
        partitions[partition] = {
            "tasks": len({(c["suite"], c["task_id"]) for c in cases}), "cases": len(cases),
            "by_suite": dict(Counter(c["suite"] for c in cases)),
            "executed": partition != "probe" or any(r["arm"] == "probe_gate" for r in roots)}
    if any(r["arm"] == "probe_gate" for r in roots) and not partitions["probe"]["cases"]:
        raise ValidationError("probe_gate requires a registered public probe allocation")
    final = {"agentdojo": partitions["heldout"]["cases"]}
    if "xstest" in external:
        final["xstest"] = len(external["xstest"]["selected_ids"])
    if "agentharm" in external:
        for path, dataset in external["agentharm"]["datasets"].items():
            final["agentharm/" + path] = len(dataset["ids"])
    for name, count in final.items():
        if count > config["budget"]["test_episodes"]:
            raise ValidationError(f"test_episodes cannot cover the frozen {name} allocation ({count})")
        if count * config["budget"]["max_steps"] > config["budget"]["test_calls"]:
            raise ValidationError(f"test_calls cannot cover {name} cases at the declared step cap")
    if final.get("xstest", 0) > config["budget"]["judge_calls"]:
        raise ValidationError("judge_calls cannot cover all selected XSTest prompts")
    prompts = config.get("prompts", {})
    return {"version": "selected-allocation-v1", "protocol": config["protocol"],
            "config_sha256": digest(config), "implementation": implementation_fingerprint(),
            "catalog_sha256": digest(backend.catalog), "case_manifest": backend.catalog,
            "benchmark": backend.describe(), "external": external, "study": study_scope(config, backend),
            "roots": roots, "root_count": len(roots), "horizon": config["slots"],
            "partitions": partitions, "final_episodes_per_root": final,
            "final_episodes_total": len(roots) * sum(final.values()),
            "execution": allocation(config, roots, final),
            "search_cost": "separately capped and reported; excluded from final episode allocation",
            "initial_policy_sha256": digest(source(prompts.get("initial_instructions", DEFAULT_INSTRUCTIONS))),
            "editor_guidance_sha256": digest(prompts.get("editor_guidance", "")),
            "budget_per_provider": config["budget"], "api_calls": 0,
            "scope_note": "Complete selected final-case allocation; not the entire upstream benchmark or all possible attacks."}
