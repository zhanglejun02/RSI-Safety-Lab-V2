"""Installed experiment definitions and deliberately limited runtime overrides."""
from copy import deepcopy
from importlib.resources import files
import json
import re

from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest

PROTOCOL = "rsi-experiment-v1"


def _catalog():
    return json.loads(files("rsi_lab.data").joinpath("experiments_v1.json").read_text())


def experiment_names():
    return tuple(_catalog())


def experiment_config(name, overrides=None):
    catalog = _catalog()
    if type(name) is not str or name not in catalog:
        raise ValidationError(f"Unknown experiment {name!r}; choose {', '.join(catalog)}")
    if overrides is None:
        overrides = {}
    if type(overrides) is not dict:
        raise ValidationError("Experiment runtime configuration must be a JSON object")
    template = catalog[name]
    settings = deepcopy(template)
    allowed = ({"seed", "slots", "budget", "harness"} if name == "local-control-v1" else
               {"source", "mode", "models", "budget", "execution", "seeds", "slots",
                "actor_context", "final_text_steps", "final_repeats", "optimization_budget",
                "observations", "review", "harness"})
    unknown = overrides.keys() - allowed
    if unknown:
        raise ValidationError("Runtime configuration cannot change experiment fields: " + ", ".join(sorted(unknown)))
    for key, value in overrides.items():
        if key in ("observations", "review"):
            if key not in template or type(value) is not dict or set(value) != {"budget"}:
                raise ValidationError(key + " runtime override must contain only its budget")
            settings[key]["budget"] = deepcopy(value["budget"])
        else:
            settings[key] = deepcopy(value)
    if settings["mode"] == "http":
        if not {"models", "budget", "execution"} <= overrides.keys():
            raise ValidationError("Natural presets require explicit models, episode budgets and total execution caps")
        execution = overrides["execution"]
        if (type(execution) is not dict or any(type(execution.get(k)) is not int or execution[k] <= 0
                                             for k in ("max_total_calls", "max_total_tokens"))):
            raise ValidationError("Natural presets require positive max_total_calls and max_total_tokens")
    settings["experiment"] = {"protocol": PROTOCOL, "id": name, "template_sha256": digest(template)}
    return settings


def validate_binding(config):
    """Validate saved provenance without reloading a possibly newer preset."""
    binding = config.get("experiment")
    if binding is None:
        return
    if (type(binding) is not dict or set(binding) != {"protocol", "id", "template_sha256"}
            or binding["protocol"] != PROTOCOL or type(binding["id"]) is not str
            or not re.fullmatch(r"[a-z][a-z0-9-]*-v[1-9][0-9]*", binding["id"])
            or type(binding["template_sha256"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", binding["template_sha256"])):
        raise ValidationError("Invalid experiment provenance")
