"""Source-locked native simulations, with independent post-execution grading.

Only the audited subset is executable. No remote tools, native solver or native
ShieldAgent are implied. Candidate code sees the original instruction and tools,
never the private environment parameters, risk taxonomy or judgment.
"""
import builtins
from copy import deepcopy
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
from types import ModuleType

from rsi_lab.errors import IntegrityError, UnsupportedCapability, ValidationError
from rsi_lab.serialization import digest

VERSION = "agent-safetybench-subset-v1"
SCORER = "agent-safetybench-derived-judge-v2"
METRICS = {
    "agent_safetybench/safety_violation": {"direction": "lower", "unit": "binary_rate",
        "denominator": "all_completed_episodes_with_valid_derived_judgment",
        "description": "Derived model judgment of unsafe behavior; not official ShieldAgent"},
    "agent_safetybench/task_success": {"direction": "higher", "unit": "binary_rate",
        "denominator": "native_fulfillable_episodes_with_valid_derived_judgment",
        "description": "Full user-goal completion, independently of safety; unfulfillable tasks excluded"},
}


def source_lock():
    return json.loads(files("rsi_lab.data").joinpath("agent_safetybench_subset_v1.json").read_text())


@lru_cache(maxsize=None)
def _native(name):
    """Resolve the upstream absolute BaseEnv import without global sys.path edits."""
    root = files("rsi_lab.benchmarks.agent_safetybench_vendor")
    path = root.joinpath(name + ".py")
    module = ModuleType("_rsi_asb_" + name)
    module.__file__ = str(path)
    def native_import(key, globals=None, locals=None, fromlist=(), level=0):
        if key == "BaseEnv":
            return _native("BaseEnv")
        if name == "BaseEnv" and key in ("json", "os"):
            return builtins.__import__(key, globals, locals, fromlist, level)
        raise ImportError("Import outside audited Agent-SafetyBench subset: " + key)
    module.__dict__["__builtins__"] = {**vars(builtins), "__import__": native_import}
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


class Catalog:
    def __init__(self, settings):
        if type(settings) is not dict or set(settings) != {"partitions"}:
            raise ValidationError("Agent-SafetyBench requires explicit ID partitions")
        partitions = settings["partitions"]
        if (type(partitions) is not dict or set(partitions) != {"dev", "probe", "heldout"}
                or partitions["dev"] or partitions["probe"] or not partitions["heldout"]):
            raise UnsupportedCapability("This exploratory subset supports frozen heldout evaluation only")
        ids = partitions["heldout"]
        if type(ids) is not list or any(type(i) is not int for i in ids) or len(ids) != len(set(ids)):
            raise ValidationError("Use unique integer native task IDs")
        lock = source_lock()
        root = files("rsi_lab.benchmarks.agent_safetybench_vendor")
        for name, sha in lock["files"].items():
            if hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest() != sha:
                raise IntegrityError("Agent-SafetyBench source lock mismatch: " + name)
        rows = {r["id"]: r for r in lock["tasks"]}
        if set(ids) - rows.keys():
            raise UnsupportedCapability("Task environment has not been audited in the locked subset")
        self.catalog, self._rows = [], {}
        for identifier in ids:
            row = rows[identifier]
            case = {"case_id": f"{VERSION}:{identifier}", "task_id": str(identifier),
                "task_pack": VERSION, "partition": "heldout", "family": f"scenario-{identifier}",
                "pair_id": f"agent-safetybench:{identifier}", "condition": "native_scenario",
                "attack_present": False, "native_record_sha256": digest(row),
                "metric_names": ["agent_safetybench/safety_violation"] +
                    (["agent_safetybench/task_success"] if row["fulfillable"] else [])}
            self.catalog.append(case)
            self._rows[digest(case)] = row
        self._description = {"name": "agent-safetybench", "version": VERSION,
            "revision": lock["revision"], "source_lock_sha256": digest(lock),
            "catalog_sha256": digest(self.catalog), "metric_contract": METRICS,
            "grading_protocol": SCORER, "scope": "exploratory_selected_native_scenarios;derived_judge;no_official_aggregate"}

    def describe(self):
        return deepcopy(self._description)

    def cases(self, partition):
        return deepcopy(self.catalog if partition == "heldout" else [])

    def _row(self, case):
        try:
            return deepcopy(self._rows[digest(case)])
        except KeyError as exc:
            raise ValidationError("Case differs from frozen Agent-SafetyBench catalog") from exc

    def new_episode(self, case):
        return Episode(case, self._row(case))

    def scripted_reply(self, case, history, instructions=""):
        from .agent_safetybench_scoring import controls
        item = next(c for c in controls(self) if c["case"] == case and c["kind"] == "safe")
        steps = item["actions"]
        if len(history) < len(steps):
            return {"tool": steps[len(history)][0], "arguments": steps[len(history)][1]}
        return {"done": True, "answer": item["answer"]}

    def scoring_controls(self):
        from .agent_safetybench_scoring import control_records
        return control_records(self)

    def judgment_input(self, case, record):
        from .agent_safetybench_scoring import judgment_input
        return judgment_input(self._row(case), record)

    def judge(self, provider, request_id, payload):
        from .agent_safetybench_scoring import judge
        return judge(provider, request_id, payload)


class Episode:
    def __init__(self, case, row):
        self.case, self.row, self.initial_request = deepcopy(case), row, row["instruction"]
        self._tools, self._environments = {}, []
        for spec in row["environments"]:
            env = getattr(_native(spec["name"]), spec["name"])(parameters=deepcopy(spec.get("parameters")))
            self._environments.append(env)
            for tool in env.get_tool_descs(spec["tools"]):
                if tool["name"] in self._tools:
                    raise ValidationError("Ambiguous native tool name")
                self._tools[tool["name"]] = (env, deepcopy(tool))

    def tools(self):
        return [deepcopy(t) for _, t in self._tools.values()]

    def call(self, name, arguments):
        # Retain native type conversion, error returns and mutation. Copy both
        # sides: upstream tools mutate arguments and return live state aliases.
        env, _ = self._tools[name]
        return deepcopy(env.call_tool(name, deepcopy(arguments)))

    def finish(self, final_text):
        return {"complete": True, "utility": None, "security": None, "attack_present": False,
            "task_success": None, "grading_status": "pending_independent_trace_judgment",
            "safety_metrics": {"family": "agent_safetybench", "judge": "pending",
                "values": {n.split("/", 1)[1]: None for n in self.case["metric_names"]}}}
