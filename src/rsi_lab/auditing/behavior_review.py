"""Public effect-based probes, independent of the RSI search implementation.

Backends supply an explicit Boolean task_success verdict and a Boolean security
metric. No grader, attack metadata or final partition crosses into the reviewer.
These finite policy probes do not predict optimizer or descendant behavior.
"""
from copy import deepcopy

from rsi_lab.agents.runtime import CandidateConfigurationError
from rsi_lab.auditing.review import SCOPES, _policy_sources
from rsi_lab.errors import BudgetExceeded, IntegrityError, ModelResponseValidationError, OutcomeUnknown, ValidationError
from rsi_lab.serialization import decode_json, digest, json_text


class PublicProbeBackend:
    """Restrict execution to an immutable public-probe allocation."""

    def __init__(self, backend):
        cases = backend.cases("probe")
        if (not cases or any(case.get("partition") != "probe" for case in cases)
                or len({digest(case) for case in cases}) != len(cases)):
            raise IntegrityError("Behavior review requires unique public probe cases")
        self._backend, self._cases_json = backend, json_text({"cases": cases})
        self._description = {**deepcopy(backend.describe()), "partition": "probe",
                             "probe_cases_sha256": digest(cases)}

    def describe(self):
        return deepcopy(self._description)

    def cases(self, partition):
        return decode_json(self._cases_json)["cases"] if partition == "probe" else []

    def new_episode(self, case):
        if case not in self.cases("probe"):
            raise IntegrityError("Review execution is outside its public probe allocation")
        return self._backend.new_episode(deepcopy(case))

    def scripted_reply(self, case, history, instructions=""):
        if case not in self.cases("probe"):
            raise IntegrityError("Scripted review reply is outside its public probe allocation")
        return self._backend.scripted_reply(case, history, instructions=instructions)


class BehaviorProbeRunner:
    def __init__(self, runtime, backend, *, root_id=None):
        self.runtime, self.backend = runtime, PublicProbeBackend(backend)
        self._case_sha256s = tuple(sorted(digest(case) for case in self.backend.cases("probe")))
        self.root_id = root_id

    @property
    def case_sha256s(self):
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
            rows = [self._probe(program, case, prefix + digest(case))
                    for case in self.backend.cases("probe")]
            policies.append({"source_sha256": digest(program), "rows": rows})
        return {"identity": prepared.identity, "parent_sha256": digest(parent), "policies": policies,
                "coverage": {"scope": scope, "policy_count": len(programs),
                             "new_retained_policy_count": len(new), "meta_execution_assessed": False,
                             "limitation": "fixed_policy_probes_do_not_assess_optimizer_or_future_meta_behavior"}}

    def _probe(self, program, case, operation):
        if digest(case) not in self._case_sha256s:
            raise IntegrityError("Probe case is outside its frozen allocation")
        row = {"case_sha256": digest(case), "complete": False,
               "task_completion": None, "safety_violation": None}
        named = "metric_contract" in self.backend.describe()
        if named:
            from rsi_lab.benchmarks.metrics import declared_measurements
            row = {"case_sha256": digest(case), "complete": False,
                   "measurements": declared_measurements(case, {})}
        try:
            record = self.runtime.execute(program, case, self.backend, operation)
            if named:
                row["measurements"] = declared_measurements(case, record)
                row["record_sha256"] = record["record_sha256"]
                row["complete"] = all(m["value"] is not None for m in row["measurements"])
                if not row["complete"]:
                    row["error"] = "incomplete_public_probe"
                return row
            metrics, verdict = record["metrics"], record.get("verdict", {})
            success, security = verdict.get("task_success"), metrics.get("security")
            row["task_completion"] = success if type(success) is bool else None
            row["safety_violation"] = not security if type(security) is bool else None
            row["record_sha256"] = record["record_sha256"]
            row["complete"] = metrics.get("complete") is True and metrics.get("task_complete") is True and all(
                row[key] is not None for key in ("task_completion", "safety_violation"))
            if not row["complete"]:
                row["error"] = "incomplete_public_probe"
        except (BudgetExceeded, OutcomeUnknown, CandidateConfigurationError, ModelResponseValidationError) as exc:
            row["error"] = type(exc).__name__
        return row
