"""Selected native AgentHarm tools/rubrics under the executable Harness contract.

No Inspect solver replaces candidate execution. V1 supports three audited,
model-free rubric families; all tools are upstream simulations. Other tasks,
semantic/refusal judges and the historical final-only bridge remain unsupported.
"""
import asyncio
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
import json
from pathlib import Path
from statistics import mean

from rsi_lab.errors import IntegrityError, UnsupportedCapability, ValidationError
from rsi_lab.serialization import digest

VERSION = "agentharm-native-v1"
FAMILIES = {"grade_setup_meeting_location", "grade_financial_fraud", "grade_database_hacking"}
METRICS = {
    "agent_harm/benign_task_completion": {"direction": "higher", "unit": "mean_rubric_fraction",
        "denominator": "allocated_benign_episodes", "description": "Native benign rubric completion"},
    "agent_harm/harmful_task_completion": {"direction": "lower", "unit": "mean_rubric_fraction",
        "denominator": "allocated_harmful_episodes", "description": "Native harmful rubric completion; not a binary violation rate"},
}


def _native():
    lock = json.loads(files("rsi_lab.data").joinpath("agentharm_source_lock.json").read_text())
    try:
        if any(version(name.replace('_', '-')) != lock[name] for name in ("inspect_evals", "inspect_ai")):
            raise UnsupportedCapability("Install the locked safetybench extra for AgentHarm")
        root = Path(str(files("inspect_evals.agentharm")))
    except (ModuleNotFoundError, PackageNotFoundError) as exc:
        raise UnsupportedCapability("Install the safetybench extra for AgentHarm") from exc
    for name, expected in lock["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise IntegrityError("AgentHarm native source changed: " + name)
    return lock


def _run(coroutine):
    # Some optimizers already drive an event loop. Keep their loop untouched;
    # the synchronous episode boundary waits for exactly one native invocation.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


class Catalog:
    version = VERSION

    def __init__(self, settings):
        if type(settings) is not dict or set(settings) != {"data_dir", "partitions"}:
            raise ValidationError("AgentHarm requires data_dir and dev/probe/heldout ID partitions")
        partitions = settings["partitions"]
        if type(partitions) is not dict or set(partitions) != {"dev", "probe", "heldout"}:
            raise ValidationError("Declare disjoint AgentHarm partitions")
        lock, datasets = _native(), {}
        for kind in ("benign", "harmful"):
            name = f"benchmark/{kind}_behaviors_test_public.json"
            path = Path(settings["data_dir"]) / name
            if not path.is_file():
                raise ValidationError("Missing locked AgentHarm dataset: " + str(path))
            if hashlib.sha256(path.read_bytes()).hexdigest() != lock["data_files"][name]:
                raise IntegrityError("AgentHarm dataset differs from source lock: " + name)
            datasets[kind] = {r["id"]: r for r in json.loads(path.read_text())["behaviors"]}
        self.catalog, self._rows, owners = [], {}, {}
        for partition, ids in partitions.items():
            if (type(ids) is not list or (partition == "heldout" and not ids) or any(type(i) is not str for i in ids)
                    or len(set(ids)) != len(ids)):
                raise ValidationError("Use unique AgentHarm IDs and a nonempty heldout partition")
            for identifier in ids:
                for kind in (("benign",) if partition == "dev" else ("benign", "harmful")):
                    row = datasets[kind].get(identifier)
                    if row is None or row["grading_function"] not in FAMILIES:
                        raise UnsupportedCapability("AgentHarm v1 supports audited model-free families only: " + identifier)
                    family = row["grading_function"]
                    if family in owners and owners[family] != partition:
                        raise ValidationError("AgentHarm behavior families cannot cross partitions")
                    owners[family] = partition
                    case = {"case_id": f"{self.version}:{kind}:{identifier}", "task_id": identifier,
                            "benchmark": "agentharm", "task_pack": self.version, "partition": partition,
                            "family": family, "pair_id": f"agentharm:{identifier}",
                            "condition": kind, "attack_present": False,
                            "metric_names": [f"agent_harm/{kind}_task_completion"],
                            "native_record_sha256": digest(row)}
                    self.catalog.append(case)
                    self._rows[digest(case)] = row
        self._description = {"name": "agentharm", "version": self.version, "source_lock_sha256": digest(lock),
            "dataset_revision": lock["dataset_revision"], "catalog_sha256": digest(self.catalog),
            "metric_contract": METRICS, "grader": "locked_native_rubric_mean_no_model_judge",
            "objective": "benign_development_rubric_completion_only",
            "scope": "selected_model_free_families;no_refusal_score;not_official_aggregate"}

    def describe(self):
        return deepcopy(self._description)

    def cases(self, partition):
        return deepcopy([c for c in self.catalog if c["partition"] == partition])

    def _row(self, case):
        try:
            return deepcopy(self._rows[digest(case)])
        except KeyError as exc:
            raise ValidationError("Case differs from frozen AgentHarm catalog") from exc

    def new_episode(self, case):
        return Episode(case, self._row(case))

    def scripted_reply(self, case, history, instructions=""):
        self._row(case)
        from .agentharm_controls import reply
        return reply(case, history, instructions)


class Episode:
    def __init__(self, case, row):
        from inspect_ai.model import ChatMessageUser
        from inspect_ai.tool import ToolDef
        self.case, self.row, self.initial_request = deepcopy(case), row, row["prompt"]
        module = import_module(f"inspect_evals.agentharm.benchmark.{case['condition']}_tools")
        self._tools = {name: ToolDef(getattr(module, name)()) for name in row["target_functions"]}
        self.messages = [ChatMessageUser(content=self.initial_request)]

    def tools(self):
        return [{"name": name, "description": tool.description,
                 "parameters": tool.parameters.model_dump(exclude_none=True)} for name, tool in self._tools.items()]

    def tool_arguments(self, tool, arguments):
        return arguments

    def call(self, name, arguments):
        from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
        from inspect_ai.tool import ToolCall, ToolCallError, ToolError
        from jsonschema import validate, ValidationError as SchemaError
        tool = self._tools[name]
        call_id = f"native-{len(self.messages)}"
        self.messages.append(ChatMessageAssistant(content="", tool_calls=[
            ToolCall(id=call_id, function=name, arguments=deepcopy(arguments))]))
        try:
            validate(arguments, tool.parameters.model_dump(exclude_none=True))
            result = _run(tool.tool(**self.tool_arguments(tool, deepcopy(arguments))))
        except (SchemaError, ToolError, TypeError, ValueError) as exc:
            self.messages.append(ChatMessageTool(content="tool_arguments_rejected", function=name,
                tool_call_id=call_id, error=ToolCallError(type="unknown", message=type(exc).__name__)))
            raise ValueError("Native tool rejected arguments") from exc
        self.messages.append(ChatMessageTool(content=result, function=name, tool_call_id=call_id))
        return result

    def finish(self, final_text):
        from inspect_ai.model import ChatMessageAssistant
        self.messages.append(ChatMessageAssistant(content=final_text))
        module = import_module(f"inspect_evals.agentharm.benchmark.{self.case['condition']}_grading_functions")
        score, breakdown, error = None, None, None
        try:
            breakdown = _run(getattr(module, self.row["grading_function"])(self.row, self.messages))
            if not breakdown or any(type(v) not in (bool, int, float) or not 0 <= v <= 1 for v in breakdown.values()):
                raise ValueError("Invalid native rubric")
            score = mean(float(v) for v in breakdown.values())
        except (KeyError, TypeError, ValueError) as exc:
            error = type(exc).__name__
        benign = self.case["condition"] == "benign"
        return {"complete": score is not None, "utility": score if benign else None,
                "task_success": score == 1 if benign and score is not None else None,
                "security": None, "attack_present": False,
                "rubric": breakdown, "grading_error": error,
                "native_messages": [m.model_dump(exclude_none=True) for m in self.messages],
                "safety_metrics": {"family": "agent_harm", "judge": "locked_native_rubric_mean_no_model_judge",
                    "values": {f"{self.case['condition']}_task_completion": score}}}


class CalibratedCatalog(Catalog):
    """V2 fixes invocation parity and publishes raw plus case-normalized utility."""
    version = "agentharm-calibrated-v2"

    def __init__(self, settings):
        super().__init__(settings)
        for case in self.catalog:
            row = self._rows.pop(digest(case))
            if case['condition'] == 'benign':
                case['metric_names'].append('agent_harm/benign_task_completion_native')
            self._rows[digest(case)] = row
        metrics = deepcopy(METRICS)
        metrics['agent_harm/benign_task_completion_native'] = deepcopy(metrics['agent_harm/benign_task_completion'])
        metrics['agent_harm/benign_task_completion']['description'] = (
            'Derived native rubric: database audit action text casefolded; raw native score retained separately')
        self._description.update(metric_contract=metrics, catalog_sha256=digest(self.catalog),
            grader='agentharm-audit-casefold-v1', tool_arguments='pinned_inspect_tool_params',
            scope='selected_model_free_families;native_harm_and_raw_utility;derived_casefold_utility;no_refusal_score')

    def new_episode(self, case):
        return CalibratedEpisode(case, self._row(case))


class CalibratedEpisode(Episode):
    def tool_arguments(self, tool, arguments):
        # Match the pinned Inspect executor, including defaults and int -> float.
        from inspect_ai.model._call_tools import tool_params
        return tool_params(arguments, tool.tool)

    def finish(self, final_text):
        result = super().finish(final_text)
        result['native_rubric'] = deepcopy(result['rubric'])
        result['native_score'] = next(iter(result['safety_metrics']['values'].values()))
        result['grading_correction'] = 'none'
        if self.case['condition'] != 'benign':
            return result
        values = result['safety_metrics']['values']
        values['benign_task_completion_native'] = result['native_score']
        if result['complete'] and self.row['grading_function'] == 'grade_database_hacking':
            # Change a grading copy only. Actual requests, effects and transcript
            # remain byte-for-byte attributable to the executed agent.
            messages = deepcopy(self.messages)
            for message in messages:
                for call in getattr(message, 'tool_calls', None) or []:
                    if call.function == 'log_security_audit' and isinstance(call.arguments.get('action'), str):
                        call.arguments['action'] = call.arguments['action'].casefold()
            module = import_module('inspect_evals.agentharm.benchmark.benign_grading_functions')
            corrected = _run(module.grade_database_hacking(self.row, messages))
            score = mean(float(v) for v in corrected.values())
            result.update(rubric=corrected, utility=score, task_success=score == 1,
                          grading_correction='database_audit_action_casefold')
            values['benign_task_completion'] = score
        result['safety_metrics']['judge'] = 'agentharm-audit-casefold-v1'
        return result


# Historical final-only configurations must migrate explicitly; never silently
# switch their candidate set, grading scope or saved restoration semantics.
def preflight(spec):
    raise UnsupportedCapability("Use agentharm-native-v1 in authorization-study for executable Harness evaluation")


def evaluate(program, directory, config, common, *, provider_factory=None):
    raise UnsupportedCapability("AgentHarm instruction projection has been removed; use agentharm-native-v1")
