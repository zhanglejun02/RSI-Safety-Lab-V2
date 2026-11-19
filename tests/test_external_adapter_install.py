"""Offline wheel acceptance in an isolated environment outside both checkouts."""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import venv

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/rsi_echo_adapter"


def _run(arguments, *, directory, environment):
    result = subprocess.run(arguments, cwd=directory, env=environment, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_external_adapter_installs_as_independent_wheel_and_runs_outside_checkout(tmp_path):
    local_builder = all(importlib.util.find_spec(name) for name in ("setuptools", "wheel"))
    uv = shutil.which("uv")
    if not local_builder and uv is None:
        pytest.skip("Offline acceptance requires installed setuptools/wheel or uv with cached build dependencies")
    build = tmp_path / "build"
    core = build / "core"
    core.mkdir(parents=True)
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(ROOT / name, core / name)
    shutil.copytree(ROOT / "src", core / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    example = build / "example"
    shutil.copytree(EXAMPLE, example, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "build", "dist"))
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    outside = tmp_path / "outside-checkouts"
    outside.mkdir()
    environment = {name: os.environ[name] for name in ("PATH", "HOME", "TMPDIR", "LANG") if name in os.environ}
    environment.update(PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    if local_builder:
        _run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index",
              "--wheel-dir", str(wheels), str(core), str(example)], directory=outside, environment=environment)
    else:
        for package in (core, example):
            _run([uv, "build", "--offline", "--no-python-downloads", "--wheel", "--python", sys.executable,
                  "--out-dir", str(wheels), str(package)], directory=outside, environment=environment)
    assert len(list(wheels.glob("rsi_safety_lab-*.whl"))) == 1
    assert len(list(wheels.glob("rsi_echo_adapter-*.whl"))) == 1
    installed = tmp_path / "installed"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(installed)
    python = installed / "bin/python"
    _run([str(python), "-m", "pip", "install", "--no-index", "--find-links", str(wheels),
          "rsi-echo-adapter==0.1.0"], directory=outside, environment=environment)
    _run([str(python), "-m", "pip", "check"], directory=outside, environment=environment)
    shutil.rmtree(build)
    assert not (outside / "configs").exists()
    catalog = json.loads(_run([str(installed / "bin/rsi-lab"), "list"], directory=outside, environment=environment))
    assert any(method["name"] == "echo" for method in catalog["methods"])
    control = textwrap.dedent('''
        import hashlib
        from importlib import metadata, resources
        import json
        from pathlib import Path
        import sys
        import zipfile
        from unittest.mock import patch
        # An external package may import the SDK before the registry is loaded.
        # Top-level API exports must not eagerly re-enter its unfinished PLUGIN.
        import rsi_echo_adapter
        import rsi_lab
        from rsi_lab.sdk import SystemSnapshot, decode_json, digest, read_record, loads

        prefix = Path(sys.prefix).resolve()
        for module in (rsi_lab, rsi_echo_adapter):
            location = Path(module.__file__).resolve()
            assert location.is_relative_to(prefix) and "site-packages" in location.parts, location
        entries = list(metadata.entry_points(group="rsi_lab.methods"))
        assert len(entries) == 1 and entries[0].name == "echo"
        assert entries[0].value == "rsi_echo_adapter:PLUGIN"
        resource = resources.files("rsi_lab").joinpath("data", "experiments_v1.json")
        assert Path(str(resource)).resolve().is_relative_to(prefix)
        catalog = json.loads(resource.read_text())
        checked = rsi_lab.preflight("echo", experiment="local-control-v1")
        assert checked["platform_api_calls"] == 0
        assert checked["checks"] == {"declarations_and_allocation": "passed",
            "interface_execution": "not_run", "mechanism_controls": "not_run",
            "natural_calibration": "not_run"}
        output = Path("installed-control").resolve()
        summary = rsi_lab.evaluate("echo", output=output)
        assert isinstance(summary, dict) and summary.output == output
        assert summary.report_path == output / "report.md" and summary.report_path.is_file()
        manifest = read_record(output / "manifest.json")
        assert manifest["config"] == checked["config"]
        assert manifest["config"]["experiment"] == {"protocol": "rsi-experiment-v1",
            "id": "local-control-v1", "template_sha256": digest(catalog["local-control-v1"])}
        assert summary["paid_calls"] == 0 and summary["origin"] == "control"
        assert {row["method"] for row in summary["rows"]} == {"frozen", "echo"}
        row = next(row for row in summary["rows"] if row["method"] == "echo")
        assert row["method"] == "echo" and row["editor_usage"]["dispatched_calls"] == 2
        assert all(slot["platform_committed"] for slot in row["slots"])
        root = read_record(output / "roots" / row["root_id"] / "root.json")
        final = SystemSnapshot.from_dict(root["final_snapshot"])
        state = decode_json(final.state_json)
        assert state["generation"] == 2 and len(state["history"]) == 3
        view = rsi_echo_adapter.PLUGIN.state(final)
        assert len(view.objects) == 1 and view.deployed_id == state["active_id"]
        harness = loads(view.objects[0].source)
        assert "skills/echo.md" in harness.files
        assert "_echo_original_" in harness.files[harness.entrypoint.split(":")[0]]
        executions = [read_record(path) for path in output.rglob("result.json")]
        assert any("Echo integration skill" in json.dumps(record.get("trace", [])) for record in executions)
        with zipfile.ZipFile(output / "source.zip") as archive:
            assert "rsi_echo_adapter/adapter.py" in archive.namelist()
            assert any(name.endswith(".dist-info/entry_points.txt") for name in archive.namelist())
            assert any(name.endswith(".dist-info/RECORD") for name in archive.namelist())
            assert archive.read("rsi_lab/data/experiments_v1.json") == resource.read_bytes()
        def inventory():
            return {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in output.rglob("*") if p.is_file()}
        before = inventory()
        with patch("rsi_lab.agent_bench.preflight", side_effect=AssertionError("Resume replanned")), \
             patch("rsi_lab.experiments.experiment_config", side_effect=AssertionError("Resume reloaded preset")):
            resumed = rsi_lab.evaluate("echo", output=output, experiment="local-control-v1", resume=True)
        assert resumed == summary and resumed.output == output
        assert inventory() == before
        print(json.dumps({"distribution": metadata.version("rsi-echo-adapter"),
                          "method": row["method"], "committed_slots": len(row["slots"]),
                          "paid_calls": summary["paid_calls"], "resume_readonly": True,
                          "experiment": "local-control-v1", "preset_from_installed_package": True,
                          "implementation": read_record(output / "manifest.json")["implementation"]}))
    ''')
    report = json.loads(_run([str(python), "-I", "-c", control], directory=outside, environment=environment))
    assert {key: value for key, value in report.items() if key != "implementation"} == {
        "distribution": "0.1.0", "method": "echo", "committed_slots": 2,
        "paid_calls": 0, "resume_readonly": True, "experiment": "local-control-v1",
        "preset_from_installed_package": True}
    assert len(report["implementation"]) == 64

    # Remove the installed extension before reviewing: successful discovery must
    # now come from the archived package and dist-info, not the ambient venv.
    _run([str(python), "-m", "pip", "uninstall", "--yes", "rsi-echo-adapter"],
         directory=outside, environment=environment)
    unavailable = _run([str(python), "-I", "-c", "from importlib import metadata; "
        "assert not list(metadata.entry_points(group='rsi_lab.methods'))"],
        directory=outside, environment=environment)
    assert unavailable == ""
    reviewed = json.loads(_run([str(installed / "bin/rsi-lab"), "review-frozen",
        "--run", str(outside / "installed-control"), "--output", str(outside / "frozen-review")],
        directory=outside, environment=environment))
    assert reviewed["worker_exit_code"] == 0 and reviewed["originals_unchanged"]
    replay = reviewed["replay"]
    assert replay["implementation"] == report["implementation"]
    assert replay["api_calls"] == replay["fresh_effects"] == 0
    assert replay["network_disabled"] and replay["logical_ledgers_unchanged"]
    print(json.dumps({**report, "frozen_review": True, "installed_plugin_removed_before_review": True}))
