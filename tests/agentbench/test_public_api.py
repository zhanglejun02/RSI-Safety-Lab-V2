from copy import deepcopy
import json
from pathlib import Path

import pytest

from rsi_lab.agent_bench import default_config, run_experiment
from rsi_lab.cli import main
from rsi_lab.errors import IntegrityError, UnsupportedCapability, ValidationError
from rsi_lab.methods import METHODS, check_available, method
from rsi_lab.studies import agent_bench, paired_search


def test_registry_names_and_unknown_method_fail_closed(monkeypatch):
    assert tuple(METHODS) == ("frozen", "gepa", "openevolve", "hyperagents")
    with pytest.raises(ValidationError):
        method("typo")
    monkeypatch.setattr("rsi_lab.methods.platform.system", lambda: "Linux")
    check_available(["frozen", "gepa", "openevolve"])
    with pytest.raises(UnsupportedCapability):
        check_available(["hyperagents"])


def test_cli_and_python_select_the_same_methods(capsys):
    assert main(["config", "--methods", "frozen", "openevolve"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["methods"] == ["frozen", "openevolve"]
    assert value["mode"] == "scripted"
    assert main(["config", "--profile", "banking-frozen", "--methods", "gepa"]) == 2
    assert "only the frozen" in capsys.readouterr().err


def test_profiles_are_independent_and_configurable_before_registration(tmp_path):
    a, b = default_config("banking-h2"), default_config("banking-h2")
    a["settings"]["methods"] = ["gepa", "openevolve"]
    a["settings"]["seeds"] = [17]
    assert b["settings"]["seeds"] != [17]
    manifest = paired_search.prepare(tmp_path / "run", config=a["settings"])
    assert [r["system"] for r in manifest["roots"]] == ["gepa", "openevolve"]
    assert len(manifest["roots"]) == 2
    assert manifest["mode"] == "scripted"
    invalid = deepcopy(a["settings"])
    invalid["public_tasks"] = [0]
    with pytest.raises(ValidationError, match="disjoint"):
        paired_search.validate_config(invalid)


@pytest.mark.parametrize("error", [KeyError("internal"), ValidationError("invariant")])
def test_shared_slot_host_failure_is_fatal_and_not_skipped(tmp_path, monkeypatch, error):
    from rsi_lab.subjects.openevolve import OpenEvolveAdapter

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(OpenEvolveAdapter, "propose", fail)
    config = default_config()
    config.update(methods=["openevolve"], benchmarks=["local_transfer"], slots=1)
    output = tmp_path / "run"
    with pytest.raises(type(error)):
        run_experiment(config, output)
    assert len(list(output.rglob("fatal.json"))) == 1
    assert not list(output.rglob("missing.json"))
    with pytest.raises(IntegrityError, match="internal failure"):
        run_experiment(config, output, resume=True)


def test_active_source_has_no_unresolved_internal_imports():
    """A missing copied module must fail without needing a particular experiment."""
    import ast
    import importlib.util
    import rsi_lab

    root = Path(rsi_lab.__file__).parent
    for path in root.rglob("*.py"):
        if "hyperagents_vendor" in path.parts:
            continue
        module = "rsi_lab." + ".".join(path.relative_to(root).with_suffix("").parts)
        package = module.removesuffix(".__init__") if path.name == "__init__.py" else module.rsplit(".", 1)[0]
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom):
                continue
            name = (importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                    if node.level else node.module)
            if name and name.startswith("rsi_lab"):
                assert importlib.util.find_spec(name) is not None, (path, name)
