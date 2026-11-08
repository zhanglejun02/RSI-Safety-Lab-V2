"""Configurable native task catalog with frozen upstream attack construction.

Task IDs, goals and attack definitions are fixed before optimization. This uses
AgentDojo's FixedJailbreakAttack and injection discovery, not adaptive attack search.
"""
from copy import deepcopy
import json

from rsi_lab.benchmarks import agentdojo as native
from rsi_lab.benchmarks.banking_profile import contains_exact
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest

VERSION = "agentdojo-catalog-v1"


def available_catalog():
    """Native capacity is separate from any selected experimental allocation."""
    native._native()
    from agentdojo.task_suite.load_suites import get_suites
    return {"benchmark": "agentdojo", "package_version": native.PACKAGE_VERSION,
            "benchmark_version": native.BENCHMARK_VERSION, "api_calls": 0,
            "suites": {name: {"task_ids": sorted(suite.user_tasks), "goal_ids": sorted(suite.injection_tasks)}
                       for name, suite in get_suites(native.BENCHMARK_VERSION).items()},
            "attack_implementations": {
                "important_instructions_no_names": "native discovery; compatible selected tasks/goals",
                "important_instructions": "banking profile; original benign data retained; goal 5",
                "role_spoofing": "banking profile fixed local variant; goal 5",
                "reconciliation_dependency": "banking profile fixed local variant; goal 5"},
            "scope": "Available native IDs, not a claim that every task/goal/attack combination is valid or executed."}


class Suite:
    def __init__(self, suite, partitions, injection_task_ids, attack_ids=None):
        if not isinstance(suite, str) or not suite:
            raise ValidationError("Declare a native suite name")
        get_suite, _, _ = native._native()
        try:
            self.suite = get_suite(native.BENCHMARK_VERSION, suite)
        except (KeyError, ValueError) as exc:
            raise ValidationError("Unknown native AgentDojo suite: " + str(suite)) from exc
        self.injection_task_ids = injection_task_ids
        if not isinstance(partitions, dict) or set(partitions) != {"dev", "probe", "heldout"}:
            raise ValidationError("Register dev, probe and heldout task IDs explicitly")
        if any(not isinstance(ids, list) or any(type(i) is not str for i in ids) for ids in partitions.values()):
            raise ValidationError("Task partitions require lists of native task IDs")
        groups = [set(ids) for ids in partitions.values()]
        if (not any(groups) or any(len(set(ids)) != len(ids) for ids in partitions.values())
                or any(a & b for i, a in enumerate(groups) for b in groups[i + 1:])):
            raise ValidationError("Selected task partitions must be unique and disjoint")
        if (not isinstance(injection_task_ids, list) or not injection_task_ids
                or any(type(i) is not str for i in injection_task_ids)
                or len(set(injection_task_ids)) != len(injection_task_ids)):
            raise ValidationError("Declare unique nonempty attacker goals")
        if set().union(*groups) - set(self.suite.user_tasks) or set(injection_task_ids) - set(self.suite.injection_tasks):
            raise ValidationError("Unknown native task or attacker goal in " + suite)
        attack_ids = ["important_instructions_no_names"] if attack_ids is None else attack_ids
        from . import banking_profile
        supported = {"important_instructions_no_names", *banking_profile.ATTACK_IDS}
        if (not isinstance(attack_ids, list) or not attack_ids or any(type(i) is not str for i in attack_ids)
                or len(set(attack_ids)) != len(attack_ids) or set(attack_ids) - supported):
            raise ValidationError("Unknown, empty or duplicate attack selection")
        local_ids = set(attack_ids) & set(banking_profile.ATTACK_IDS)
        if local_ids and (suite != "banking" or injection_task_ids != [banking_profile.INJECTION_TASK_ID]):
            raise ValidationError("Banking profile attacks require banking/injection_task_5")
        local_cases = {(c["task_id"], c["attack_id"]): c for c in banking_profile.cases()} if local_ids else {}
        from agentdojo.attacks.base_attacks import FixedJailbreakAttack
        from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
        attack = FixedJailbreakAttack(ImportantInstructionsAttack._JB_STRING, self.suite, None)
        self.catalog = []
        # Canonical JSON sorts object keys; process reload must preserve case order.
        for partition in ("dev", "probe", "heldout"):
            task_ids = partitions[partition]
            for task_id in task_ids:
                task = self.suite.get_user_task_by_id(task_id)
                variants = [("clean", injection_task_ids[0], {})]
                if partition != "dev":
                    for goal_id in injection_task_ids:
                        goal = self.suite.get_injection_task_by_id(goal_id)
                        for attack_id in attack_ids:
                            if attack_id == "important_instructions_no_names":
                                injections = attack.attack(task, goal)
                            else:
                                selected = local_cases.get((task_id, attack_id))
                                if selected is None:
                                    raise ValidationError(f"No registered {attack_id} placement for {suite}/{task_id}")
                                injections = {selected["injection_vector"]: selected["payload"]}
                            if not injections:
                                raise ValidationError(f"No injection slot for {suite}/{task_id}/{goal_id}/{attack_id}")
                            variants.append((attack_id, goal_id, injections))
                for name, goal_id, injections in variants:
                    self.catalog.append({"case_id": f"agentdojo:{suite}:{task_id}:{name}:{goal_id}",
                        "benchmark": "agentdojo", "suite": suite, "task_id": task_id,
                        "partition": partition, "attack": name, "attack_present": bool(injections),
                        "injection_task_id": goal_id, "injections": injections,
                        "task_version": VERSION + "/" + native.BENCHMARK_VERSION,
                        "attack_origin": (local_cases[(task_id, name)]["attack_origin"] if name in local_ids else
                                          "upstream FixedJailbreakAttack; frozen, no adaptive search")})
                    if partition == "dev":
                        self.catalog[-1] = {k: v for k, v in self.catalog[-1].items()
                                            if k not in ("injection_task_id", "injections", "attack_origin")}
                        self.catalog[-1]["case_id"] = f"agentdojo:{suite}:{task_id}:public-clean"

    def validate_worlds(self):
        """Check native initialization and exact placement without model calls or grading."""
        for case in self.catalog:
            episode = self.new_episode(case)
            world = native._jsonable(episode._world)
            if any(not contains_exact(world, text) for text in case.get("injections", {}).values()):
                raise ValidationError("Task initialization removed an injection: " + case["case_id"])

    def describe(self):
        # Public optimizer contract deliberately excludes the catalog and test metadata.
        return {"name": "agentdojo", "version": VERSION + "/" + native.BENCHMARK_VERSION,
                "suite": self.suite.name, "package_version": native.PACKAGE_VERSION,
                "upstream_source_sha256": native._upstream_hash()}

    def cases(self, partition):
        return deepcopy([c for c in self.catalog if c["partition"] == partition])

    def new_episode(self, case):
        if case not in self.catalog:
            raise ValidationError("Case differs from frozen AgentDojo catalog")
        return Episode({"injections": {}, "injection_task_id": self.injection_task_ids[0], **case})

    def scripted_reply(self, case, history, instructions=""):
        """Gold actions are zero-API controls only; HTTP paths cannot call this."""
        episode = self.new_episode(case)
        actions = episode._task.ground_truth(episode._before.model_copy(deep=True))
        observed = [h for h in history if "tool" in h]
        if "CONTROL_UNSAFE" in instructions and case["attack_present"]:
            payloads = list(case["injections"].values())
            exposed = any(contains_exact(h.get("result"), p) for h in observed for p in payloads)
            if exposed:
                harmful = episode._injection.ground_truth(episode._before.model_copy(deep=True))
                for action in harmful:
                    if not any(h["tool"] == action.function and h.get("arguments") == action.args for h in observed):
                        return {"tool": action.function, "arguments": action.args}
        for action in actions:
            if not any(h["tool"] == action.function and h.get("arguments") == action.args for h in observed):
                return {"tool": action.function, "arguments": action.args}
        return {"done": True, "answer": episode._task.GROUND_TRUTH_OUTPUT or "Completed."}


class Catalog:
    """Compose native suites while keeping suite-qualified task identities separate."""
    def __init__(self, settings):
        specs = settings.get("suites") if isinstance(settings, dict) and set(settings) == {"suites"} else [settings]
        if not isinstance(specs, list) or not specs:
            raise ValidationError("Declare at least one suite selection")
        self.suites = {}
        for spec in specs:
            required = {"suite", "partitions", "injection_task_ids"}
            if not isinstance(spec, dict) or set(spec) - {"attack_ids"} != required:
                raise ValidationError("Each suite requires suite, partitions and injection_task_ids")
            if not isinstance(spec["suite"], str) or not spec["suite"]:
                raise ValidationError("Declare a native suite name")
            if spec["suite"] in self.suites:
                raise ValidationError("Declare each suite once")
            suite = Suite(**spec)
            suite.validate_worlds()
            self.suites[spec["suite"]] = suite
        self.catalog = [case for suite in self.suites.values() for case in suite.catalog]
        if not self.cases("dev") or not self.cases("heldout"):
            raise ValidationError("The selected catalog needs nonempty dev and heldout partitions")

    def cases(self, partition):
        return deepcopy([c for c in self.catalog if c["partition"] == partition])

    def describe(self):
        if len(self.suites) == 1:
            return next(iter(self.suites.values())).describe()
        # The optimizer sees public benchmark identity, not independent selections.
        return {"name": "agentdojo", "version": VERSION + "/" + native.BENCHMARK_VERSION,
                "package_version": native.PACKAGE_VERSION, "upstream_source_sha256": native._upstream_hash(),
                "public_suites": sorted({c["suite"] for c in self.cases("dev")})}

    def new_episode(self, case):
        return self.suites[case["suite"]].new_episode(case)

    def scripted_reply(self, case, history, instructions=""):
        return self.suites[case["suite"]].scripted_reply(case, history, instructions)


class Episode(native.Episode):
    def __init__(self, case):
        # Upstream substitutes into YAML double-quoted fragments. Preserve the
        # exact frozen template bytes instead of silently folding newlines.
        escaped = {key: json.dumps(value, ensure_ascii=False)[1:-1] for key, value in case["injections"].items()}
        self._initialize(case, escaped)

    def call(self, name, arguments):
        result = super().call(name, arguments)
        visible = any(contains_exact(result, p) for p in self.case["injections"].values())
        self._injection_observed |= visible
        self._effects[-1]["injection_observed"] = visible
        return result

    def finish(self, final_text):
        result = super().finish(final_text)
        result["attack_manifest_sha256"] = digest(self.case["injections"])
        return result
