"""One registry for public method names, adapter construction and edit scope."""
from dataclasses import asdict, dataclass
from importlib import import_module
import platform

from rsi_lab.errors import UnsupportedCapability, ValidationError


@dataclass(frozen=True)
class Method:
    name: str
    module: str
    adapter: str
    scope: str
    searches: bool = True
    platforms: tuple[str, ...] = ("Darwin", "Linux")
    editor_response_format: str = "json_object"


METHODS = {
    "frozen": Method("frozen", "frozen_agent", "FrozenAgentAdapter",
                     "fixed instruction agent; no search", searches=False),
    "gepa": Method("gepa", "gepa_program", "GepaProgramAdapter",
                   "iterative instruction search; fixed optimizer"),
    "openevolve": Method("openevolve", "openevolve", "OpenEvolveAdapter",
                         "iterative instruction search; fixed optimizer"),
    "hyperagents": Method("hyperagents", "hyperagents", "HyperAgentsAdapter",
                          "bounded instruction + editable meta profile", platforms=("Darwin",),
                          editor_response_format="text"),
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
        if platform.system() not in spec.platforms:
            raise UnsupportedCapability(f"{name} supports {', '.join(spec.platforms)}; current host is {platform.system()}")


def describe_methods():
    return [asdict(spec) for spec in METHODS.values()]


def create_adapter(name, directory, provider, snapshot):
    spec = method(name)
    check_available([name])
    cls = getattr(import_module("rsi_lab.subjects." + spec.module), spec.adapter)
    if not spec.searches:
        return cls(directory, snapshot)
    return cls(directory, provider, snapshot)


def initial_snapshot(name, seed, package, *, instructions=None, options=None):
    from rsi_lab.agents.runtime import DEFAULT_INSTRUCTIONS, source

    spec = method(name)
    module = import_module("rsi_lab.subjects." + spec.module)
    settings = {"evaluation": package.binding}
    if options:
        if name != "hyperagents" or set(options) != {"meta_mode"} or options["meta_mode"] not in ("frozen", "editable"):
            raise UnsupportedCapability("Unsupported method options; no implicit surface downgrade")
        settings.update(options)
    if name == "openevolve":
        settings["admission_condition"] = "bound_public_evaluation"
    return module.initial_snapshot(seed, source(DEFAULT_INSTRUCTIONS if instructions is None else instructions), package.tool_protocol,
                                   package.contract, **settings)


def retained_policy_sources(snapshot):
    """Policies that can be selected after activation, including optimizer archives."""
    from rsi_lab.serialization import decode_json
    sources = [snapshot.version.component("policy")["source"]]
    state = decode_json(snapshot.state_json)
    if snapshot.version.system_id == "openevolve-bounded" and state.get("population"):
        sources.extend(row["code"] for row in state["population"]["programs"].values())
    elif snapshot.version.system_id == "gepa-bounded-program" and state.get("search"):
        sources.extend(row["policy"] for row in state["search"]["native"]["program_candidates"])
    elif "archive" in state and isinstance(state["archive"], dict):
        sources.extend(row["files"]["policy.py"] for row in state["archive"].values())
    return tuple(dict.fromkeys(sources))
