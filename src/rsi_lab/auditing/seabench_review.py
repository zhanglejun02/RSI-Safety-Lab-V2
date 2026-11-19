"""Public SEABench probes with separate actor/judge budgets and no final access.

Probes assess frozen task policies. They do not execute an optimizer or establish
the safety of future meta-agent behavior, including for a policy-preserving edit.
"""
from copy import deepcopy
from pathlib import Path

from rsi_lab.agents.runtime import CandidateConfigurationError
from rsi_lab.auditing.review import REVIEW_ARMS, SCOPES, _policy_sources
from rsi_lab.benchmarks.seabench import Controller, Episode
from rsi_lab.errors import BudgetExceeded, IntegrityError, ModelResponseValidationError, OutcomeUnknown, ValidationError
from rsi_lab.serialization import digest


class ScopedProbeBackend:
    """Keep only explicitly public downstream tasks, never the final catalog."""

    def __init__(self, source, sequence, probe_task_ids, *, judge_provider=None, actor_context=None, task_pack=None):
        if (not isinstance(probe_task_ids, list) or not probe_task_ids
                or any(type(value) is not str for value in probe_task_ids)
                or len(set(probe_task_ids)) != len(probe_task_ids)):
            raise ValidationError("Review probes require unique explicit task IDs")
        options = {"actor_context": actor_context}
        if task_pack is not None:
            options["task_pack"] = task_pack
        controller = Controller(source, sequence, **options)
        partition = "probe" if task_pack is not None else "heldout"
        allowed = {case["task_id"]: (case, task)
                   for case, task in zip(controller.catalog, controller.tasks, strict=True)
                   if case["partition"] == partition}
        if set(probe_task_ids) - allowed.keys():
            raise ValidationError("Public review probes are outside the declared probe allocation")
        self.root, self.native = controller.root, controller.native
        self.actor_context, self.judge = controller.actor_context, judge_provider
        self.pack = deepcopy(getattr(controller, "pack", None))
        self.task_pack_manifest = deepcopy(getattr(controller, "task_pack_manifest", None))
        self.sequence, self.evaluation_phase = sequence, "probe"
        self.catalog = tuple({**allowed[key][0], "partition": "probe"} for key in probe_task_ids)
        self.tasks = tuple(deepcopy(allowed[key][1]) for key in probe_task_ids)
        self._description = {**controller.describe(), "partition": "probe",
                             "probe_cases_sha256": digest(self.catalog)}

    def describe(self):
        return deepcopy(self._description)

    def cases(self, partition):
        return deepcopy(list(self.catalog)) if partition == "probe" else []

    def new_episode(self, case):
        if case not in self.catalog:
            raise IntegrityError("Review execution cannot access a case outside its public probe allocation")
        index = self.catalog.index(case)
        # Legacy native scoring selects rubrics by partition. Versioned task packs
        # use their explicit probe phase and must retain the original case identity.
        execution_case = case if self.pack is not None else {**case, "partition": "heldout"}
        return Episode(self, self.tasks[index], execution_case)

    def scripted_reply(self, case, history, instructions=""):
        if case not in self.catalog:
            raise IntegrityError("Scripted review reply is outside the public probe allocation")
        return Controller.scripted_reply(self, case, history, instructions)


class SEABenchProbeRunner:
    def __init__(self, runtime, backend, *, root_id=None):
        cases = backend.cases("probe")
        if not cases or any(case["partition"] != "probe" for case in cases):
            raise IntegrityError("SEABench review requires a public probe partition")
        self.runtime, self.backend, self.cases = runtime, backend, tuple(cases)
        self._case_sha256s = tuple(sorted(digest(case) for case in cases))
        self.root_id = root_id

    @property
    def case_sha256s(self):
        """Immutable allocation identity consumed by the review coordinator."""
        return self._case_sha256s

    def compare(self, prepared, scope):
        if scope not in SCOPES:
            raise ValidationError("Unknown review policy scope")
        prepared.validate()
        if self.root_id is not None and prepared.identity.root_id != self.root_id:
            raise IntegrityError("Review capability belongs to a different root")
        parent, new, programs = _policy_sources(prepared, scope)
        policies = []
        for program in programs:
            prefix = prepared.identity.update_id + "/review/" + scope + "/" + digest(program) + "/"
            rows = [self._probe(program, case, prefix + digest(case)) for case in self.cases]
            policies.append({"source_sha256": digest(program), "rows": rows})
        return {"identity": prepared.identity, "parent_sha256": digest(parent), "policies": policies,
                "coverage": {"scope": scope, "policy_count": len(programs),
                             "new_retained_policy_count": len(new), "meta_execution_assessed": False,
                             "limitation": "fixed_policy_probes_do_not_assess_optimizer_or_future_meta_behavior"}}

    def _probe(self, program, case, operation):
        """Project one durable rollout to the public behavioral evidence schema."""
        row = {"case_sha256": digest(case), "complete": False,
               "task_completion": None, "safety_violation": None}
        try:
            record = self.runtime.execute(program, case, self.backend, operation)
            metrics = record["metrics"]
            values = metrics.get("safety_metrics", {}).get("values", {})
            for key in ("task_completion", "safety_violation"):
                value = values.get(key)
                row[key] = value if type(value) is bool else None
            row["record_sha256"] = record["record_sha256"]
            safety = record.get("verdict", {}).get("judgments", {}).get("safety_llm", {})
            row["complete"] = metrics["complete"] and safety.get("evidence_complete", True) and all(
                row[key] is not None for key in ("task_completion", "safety_violation"))
            if not row["complete"]:
                row["error"] = "incomplete_public_probe"
        except (BudgetExceeded, OutcomeUnknown, CandidateConfigurationError, ModelResponseValidationError) as exc:
            row["error"] = type(exc).__name__
        return row


def build_review_gate(config, root, directory):
    """Build the declared review capability, using fresh root-local providers."""
    # Imports stay local: the shared study and SEABench runner consume this module.
    from rsi_lab.auditing.review import RandomRejectGate, ReviewGate, validate_review_spec
    arm = root.get("arm", "review")
    if arm == "random_reject":
        return RandomRejectGate(config["random_reject"]), None
    if arm not in REVIEW_ARMS:
        raise ValidationError("No review capability for this intervention arm")
    from rsi_lab.studies import safety_study as shared, seabench_study

    review = deepcopy(config["review"])
    probe_task_ids = review.pop("probe_task_ids")
    budget = review.pop("budget")
    spec = validate_review_spec(review)
    fields = {"episodes", "calls", "judge_calls", "max_total_tokens", "judge_max_total_tokens"}
    if (not isinstance(budget, dict) or set(budget) != fields
            or any(type(value) is not int or value < 1 for value in budget.values())):
        raise ValidationError("Review requires independent positive actor and judge budgets")
    settings = deepcopy(config)
    settings["budget"].update(actor_episodes=budget["episodes"], actor_calls=budget["calls"],
                              judge_calls=budget["judge_calls"])
    if settings["mode"] == "http":
        settings["models"]["actor"]["max_total_tokens"] = budget["max_total_tokens"]
        settings["models"]["judge"]["max_total_tokens"] = budget["judge_max_total_tokens"]
    backend = ScopedProbeBackend(config["source"], config["sequence"], probe_task_ids,
                                 actor_context=config.get("actor_context"), task_pack=config.get("task_pack"))
    root_directory = Path(directory)
    directory = root_directory / "review"
    judge = seabench_study._judge_provider(directory, settings)
    backend.judge = judge
    actor = shared._provider(directory, settings, "actor", backend, backend.cases("probe"))
    if "optimization_budget" in config:
        from rsi_lab.infra.optimization_budget import OptimizationBudget
        combined = OptimizationBudget(root_directory, config["optimization_budget"])
        combined.attach(actor)
        combined.attach(judge)
    runtime = shared._runtime(directory, actor, settings, "actor")
    probes = SEABenchProbeRunner(runtime, backend, root_id=root["root_id"])

    def resources():
        return {"actor": actor.summary(), "judge": judge.summary()}

    return ReviewGate(spec, probes, usage=resources, mode=arm), resources
