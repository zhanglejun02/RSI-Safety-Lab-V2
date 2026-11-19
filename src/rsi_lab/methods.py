"""One registry for public method names, adapter construction and edit scope."""
from dataclasses import asdict, dataclass
from importlib import import_module
import platform
from copy import deepcopy

from rsi_lab.errors import UnsupportedCapability, ValidationError

CAPABILITY_PROTOCOL = "rsi-method-capabilities-v1"
OBSERVATIONS = ("process_events", "deployed_policy", "retained_policies")
INTERVENTIONS = ("candidate_review", "random_reject", "observe_only",
                 "archive_withdrawal", "continuation_review")


@dataclass(frozen=True)
class Method:
    name: str
    module: str
    adapter: str
    scope: str
    searches: bool = True
    platforms: tuple[str, ...] = ("Darwin", "Linux")
    editor_response_format: str = "json_object"
    system_id: str = ""


METHODS = {
    "frozen": Method("frozen", "frozen_agent", "FrozenAgentAdapter",
                     "frozen executable Harness; no search", searches=False, system_id="frozen-tool-agent"),
    "gepa": Method("gepa", "gepa_program", "GepaProgramAdapter",
                   "native text reflection over declared Harness resources", system_id="gepa-bounded-program"),
    "openevolve": Method("openevolve", "openevolve", "OpenEvolveAdapter",
                         "native population search over declared Harness resources", system_id="openevolve-bounded"),
    "hyperagents": Method("hyperagents", "hyperagents", "HyperAgentsAdapter",
                          "executable Harness + separately scoped optimizer meta", platforms=("Darwin",),
                          editor_response_format="text", system_id="hyperagents-bounded-meta"),
}


def method(name: str) -> Method:
    try:
        return METHODS[name]
    except (KeyError, TypeError) as exc:
        raise ValidationError(f"Unknown method {name!r}; choose {', '.join(METHODS)}") from exc


def check_available(names):
    """Reject unsupported execution hosts before any provider is constructed."""
    for name in names:
        spec = method(name)
        if platform.system() != "Darwin":
            raise UnsupportedCapability("Executable Harness experiments require macOS sandbox-exec; no unsandboxed fallback")
        if platform.system() not in spec.platforms:
            raise UnsupportedCapability(f"{name} supports {', '.join(spec.platforms)}; current host is {platform.system()}")


def describe_methods():
    return [{**asdict(spec), "capabilities": method_capabilities(spec.name)}
            for spec in METHODS.values()]


def method_capabilities(name, *, options=None):
    """Planning declarations, not permission to mutate an adapter snapshot.

    State paths describe inherited search state. Journals, spent budgets and
    public rollout caches are external and are never restored by rejection.
    """
    spec = method(name)
    plugin = method_plugin(name)
    if plugin:
        if options:
            raise UnsupportedCapability("External method options must be frozen by the adapter package")
        return {"protocol": CAPABILITY_PROTOCOL, "method": name, "system_id": spec.system_id,
                "options": {}, **deepcopy(plugin.capabilities),
                "rollback": "candidate_snapshot_not_committed",
                "external_state": ["provider_journals", "resource_reservations", "public_rollout_cache"]}
    if options is not None and (type(options) is not dict or
            (options and (name != "hyperagents" or set(options) != {"meta_mode"}
                          or options["meta_mode"] not in ("frozen", "editable")))):
        raise ValidationError("Unsupported method capability options")
    mode = (options or {}).get("meta_mode", "editable") if name == "hyperagents" else None
    state = {
        "frozen": [],
        "gepa": ["version.policy", "state.epoch", "state.search.native",
                 "state.search.sampler", "state.search.rng"],
        "openevolve": ["version.policy", "state.population", "state.public_artifacts",
                       "state.rng", "state.generation"],
        "hyperagents": ["version.policy", "state.archive", "state.epoch", "state.active_id"],
    }[name]
    if mode == "editable":
        state.append("version.meta_agent")
    limits = {
        "frozen": ["no_proposals_or_candidate_intervention"],
        "gepa": ["one_reflection_per_slot", "no_merge", "aggregate_best_latest_tie_deployment",
                 "agent_utility_profile_uses_persistent_per_case_pareto"],
        "openevolve": ["one_island", "one_full_rewrite_per_slot",
                       "request_source_matches_do_not_identify_all_prompt_roles"],
        "hyperagents": ["macos_isolated_worker", "configured_editor_replies_per_edit_default_three",
                        "only_policy_and_meta_files_are_inherited"],
    }[name]
    if mode:
        limits.append("meta_" + mode)
    return {"protocol": CAPABILITY_PROTOCOL, "method": spec.name, "system_id": spec.system_id,
            "options": {"meta_mode": mode} if mode else {}, "mutable_state": state,
            "observations": list(OBSERVATIONS if spec.searches else OBSERVATIONS[:2]),
            "interventions": list(INTERVENTIONS[:3]) if spec.searches else [],
            "rollback": "candidate_snapshot_not_committed" if spec.searches else None,
            "external_state": ["provider_journals", "resource_reservations", "public_rollout_cache"],
            "limits": limits + ["exact_source_presence_is_not_semantic_causality",
                                "archive_withdrawal_and_continuation_review_unsupported"]}


def require_capabilities(name, *, observations=(), interventions=(), options=None):
    """Fail before provider construction; unsupported capabilities never downgrade."""
    descriptor = method_capabilities(name, options=options)
    for field, requested, known in (("observations", observations, OBSERVATIONS),
                                    ("interventions", interventions, INTERVENTIONS)):
        if (type(requested) not in (tuple, list) or any(type(x) is not str for x in requested)
                or len(set(requested)) != len(requested) or set(requested) - set(known)):
            raise ValidationError("Unknown or invalid requested " + field)
        missing = set(requested) - set(descriptor[field])
        if missing:
            raise UnsupportedCapability(name + " does not support " + field + ": " + ", ".join(sorted(missing)))
    return descriptor


def create_adapter(name, directory, provider, snapshot):
    spec = method(name)
    check_available([name])
    plugin = method_plugin(name)
    if plugin:
        plugin.state(snapshot)
        adapter = plugin.adapter(directory, provider, snapshot)
        descriptor = adapter.describe()
        if descriptor.system_id != plugin.system_id or descriptor.upstream_revision != plugin.revision:
            raise ValidationError("Plugin adapter descriptor differs from registration")
        return adapter
    cls = getattr(import_module("rsi_lab.subjects." + spec.module), spec.adapter)
    if not spec.searches:
        return cls(directory, snapshot)
    return cls(directory, provider, snapshot)


def initial_snapshot(name, seed, package, *, instructions=None, options=None, harness=None):
    from rsi_lab.harness import DEFAULT_INSTRUCTIONS, source, loads

    spec = method(name)
    program = loads(harness).dumps() if harness is not None else source(DEFAULT_INSTRUCTIONS if instructions is None else instructions)
    plugin = method_plugin(name)
    if plugin:
        method_capabilities(name, options=options)
        snapshot = plugin.initial_snapshot(seed, program,
                                           package.tool_protocol, package.contract, evaluation=package.binding)
        if snapshot.version.component("policy")["source"] != program:
            raise ValidationError("Method plugin replaced the common founding Harness")
        plugin.state(snapshot)
        return snapshot
    module = import_module("rsi_lab.subjects." + spec.module)
    settings = {"evaluation": package.binding}
    if options:
        if name != "hyperagents" or set(options) != {"meta_mode"} or options["meta_mode"] not in ("frozen", "editable"):
            raise UnsupportedCapability("Unsupported method options; no implicit surface downgrade")
        settings.update(options)
    if name == "openevolve":
        settings["admission_condition"] = "bound_public_evaluation"
    return module.initial_snapshot(seed, program, package.tool_protocol,
                                   package.contract, **settings)


def retained_policy_sources(snapshot):
    """Distinct stored policy sources; parent eligibility is method-specific."""
    from rsi_lab.serialization import decode_json
    sources = [snapshot.version.component("policy")["source"]]
    plugin = next((p for p in _PLUGINS.values() if p.system_id == snapshot.version.system_id), None)
    if plugin:
        return tuple(dict.fromkeys(sources + [obj.source for obj in plugin.state(snapshot).objects]))
    state = decode_json(snapshot.state_json)
    if snapshot.version.system_id == "openevolve-bounded" and state.get("population"):
        sources.extend(row["code"] for row in state["population"]["programs"].values())
    elif snapshot.version.system_id == "gepa-bounded-program" and state.get("search"):
        sources.extend(row["policy"] for row in state["search"]["native"]["program_candidates"])
    elif "archive" in state and isinstance(state["archive"], dict):
        sources.extend(row["files"]["policy.py"] for row in state["archive"].values())
    return tuple(dict.fromkeys(sources))


def method_plugin(name):
    return _PLUGINS.get(name)


from rsi_lab.plugins import discover, bindings as plugin_bindings

_PLUGINS = discover(set(METHODS), {m.system_id for m in METHODS.values()})
for _name, _plugin in _PLUGINS.items():
    METHODS[_name] = Method(_name, _plugin.adapter.__module__, _plugin.adapter.__name__,
                            _plugin.scope, platforms=_plugin.platforms,
                            editor_response_format=_plugin.editor_response_format, system_id=_plugin.system_id)
