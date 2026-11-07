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


METHODS = {
    "frozen": Method("frozen", "frozen_agent", "FrozenAgentAdapter",
                     "fixed instruction agent; no search", searches=False),
    "gepa": Method("gepa", "gepa_program", "GepaProgramAdapter",
                   "iterative instruction search; fixed optimizer"),
    "openevolve": Method("openevolve", "openevolve", "OpenEvolveAdapter",
                         "iterative instruction search; fixed optimizer"),
    "hyperagents": Method("hyperagents", "hyperagents", "HyperAgentsAdapter",
                          "bounded instruction + editable meta profile", platforms=("Darwin",)),
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


def initial_snapshot(name, seed, package):
    from rsi_lab.agents.runtime import DEFAULT_INSTRUCTIONS, source

    spec = method(name)
    module = import_module("rsi_lab.subjects." + spec.module)
    settings = {"evaluation": package.binding}
    if name == "openevolve":
        settings["admission_condition"] = "bound_public_evaluation"
    return module.initial_snapshot(seed, source(DEFAULT_INSTRUCTIONS), package.tool_protocol,
                                   package.contract, **settings)
