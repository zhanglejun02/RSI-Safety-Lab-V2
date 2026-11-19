"""Fail-closed extension discovery and explicit native-object identity controls."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from rsi_lab import plugins
from rsi_lab.agent_bench import evaluate
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.sdk import (Component, LocalSystemAdapter, MethodPlugin, PolicyObject,
                         StateView, SystemSnapshot, SystemVersion, candidate_projection,
                         json_text, policy_source)


SOURCE = policy_source("SDK identity control")


def snapshot(*, system_id="test-extension", revision="test-extension-v1"):
    return SystemSnapshot(SystemVersion(system_id, (
        Component("policy", json_text({"source": SOURCE}), "agent"),), revision))


def plugin(**changes):
    value = MethodPlugin(
        name="extension", system_id="test-extension", revision="test-extension-v1",
        scope="SDK identity control", adapter=LocalSystemAdapter,
        initial_snapshot=lambda *args, **kwargs: snapshot(),
        state_view=lambda value: StateView((PolicyObject("parent", SOURCE),), "parent"),
        scripted_reply=lambda operation, program: {"source": program},
        capabilities={"mutable_state": ["version.policy"],
                      "observations": ["process_events", "deployed_policy"],
                      "interventions": ["candidate_review"], "limits": []})
    return replace(value, **changes)


@pytest.fixture
def discover(monkeypatch):
    # Exercise discovery without registering a package in the developer venv or
    # altering the already loaded public method registry.
    monkeypatch.setattr(plugins, "PLUGINS", {})
    monkeypatch.setattr(plugins, "ENTRIES", {})

    def run(values):
        entries = [SimpleNamespace(name=name, value="test_extension:PLUGIN", load=lambda p=p: p)
                   for name, p in values]
        def entry_points(*, group):
            assert group == "rsi_lab.methods"
            return entries
        monkeypatch.setattr(plugins.metadata, "entry_points", entry_points)
        return plugins.discover({"frozen", "gepa", "openevolve", "hyperagents"},
                                {"frozen-tool-agent", "gepa-bounded-program",
                                 "openevolve-bounded", "hyperagents-bounded-meta"})
    return run


@pytest.mark.parametrize("changes,entry_name", [
    ({"sdk_version": "rsi-method-sdk-v1"}, "extension"),
    ({"sdk_version": "unrecognized-sdk-v9"}, "extension"),
    ({"name": "gepa"}, "gepa"),
    ({"system_id": "gepa-bounded-program"}, "extension"),
    ({}, "different_registered_name"),
])
def test_discovery_rejects_incompatible_or_builtin_identity(discover, changes, entry_name):
    with pytest.raises(ValidationError, match="Invalid, incompatible or duplicate"):
        discover([(entry_name, plugin(**changes))])
    assert plugins.PLUGINS == plugins.ENTRIES == {}


@pytest.mark.parametrize("same_field", ["name", "system_id"])
def test_discovery_cannot_overwrite_an_already_registered_plugin(discover, same_field):
    first = plugin()
    second = plugin(name="second", system_id="second-system")
    second = replace(second, **{same_field: getattr(first, same_field)})
    with pytest.raises(ValidationError, match="duplicate"):
        discover([(first.name, first), (second.name, second)])
    assert plugins.PLUGINS == {first.name: first}
    assert plugins.ENTRIES[first.name].load() is first


@pytest.mark.parametrize("field,value", [
    ("observations", ["hidden_labels"]),
    ("interventions", ["archive_withdrawal"]),
    ("observations", ["deployed_policy", "deployed_policy"]),
    ("mutable_state", "version.policy"),
    ("unsupported_declaration", []),
])
def test_discovery_rejects_undeclared_or_malformed_capabilities(discover, field, value):
    declaration = {**plugin().capabilities, field: value}
    with pytest.raises(ValidationError, match="capability declaration"):
        discover([("extension", plugin(capabilities=declaration))])
    assert plugins.PLUGINS == {}


@pytest.mark.parametrize("changes", [
    {"system_id": "different-system"}, {"revision": "different-revision"},
])
def test_state_rejects_foreign_snapshot_before_calling_plugin_projection(changes):
    value = plugin(state_view=lambda _: pytest.fail("Foreign snapshot reached plugin projection"))
    with pytest.raises(IntegrityError, match="implementation mismatch"):
        value.state(snapshot(**changes))


@pytest.mark.parametrize("view,error,message", [
    (StateView((PolicyObject("same", SOURCE), PolicyObject("same", SOURCE)), "same"),
     IntegrityError, "duplicate native IDs"),
    (StateView((PolicyObject("parent", "different source"),), "parent"),
     IntegrityError, "deployment differs"),
    (StateView((PolicyObject("parent", SOURCE),), "missing"),
     IntegrityError, "deployment differs"),
    (StateView((PolicyObject(True, SOURCE),), None), ValidationError, "Invalid plugin policy object"),
    (StateView((PolicyObject(1, SOURCE),), True), ValidationError, "deployed ID"),
    (StateView([PolicyObject("parent", SOURCE)], "parent"), ValidationError, "tuple objects"),
])
def test_state_rejects_ambiguous_native_identity(view, error, message):
    with pytest.raises(error, match=message):
        plugin(state_view=lambda _: view).state(snapshot())


def test_missing_candidate_identity_stays_unknown_even_when_policy_matches():
    state = snapshot()
    projected = candidate_projection(plugin(), SOURCE, {}, candidate=state, active=state, committed=True)
    assert projected["policy_matches_deployment"] is True
    assert projected["object_identity_coverage"] == "not_observed"
    assert projected["native_id"] is None
    assert projected["object_in_candidate_snapshot"] is None
    assert projected["object_retained_after"] is None
    assert projected["object_deployed_after"] is None


def test_declared_absent_candidate_id_is_not_inferred_from_identical_source():
    state = snapshot()
    projected = candidate_projection(plugin(), SOURCE, {"child_id": "absent"},
                                     candidate=state, active=state, committed=False)
    assert projected["policy_matches_deployment"] is True
    assert projected["object_in_candidate_snapshot"] is False
    assert projected["object_retained_after"] is False
    assert projected["object_deployed_after"] is False


def test_distinct_objects_with_identical_policy_keep_meta_and_deployment_identity():
    view = StateView((PolicyObject("a", SOURCE, "meta A"),
                      PolicyObject("b", SOURCE, "meta B")), "a")
    method = plugin(state_view=lambda _: view)
    state = snapshot()
    assert method.state(state) == view
    projected = candidate_projection(method, SOURCE, {"child_id": "b", "proposed_meta_source": "meta B"},
                                     candidate=state, active=state, committed=True)
    assert projected["object_retained_after"] is True
    assert projected["object_deployed_after"] is False
    assert projected["native_id"] == "b" and projected["policy_matches_deployment"] is True
    with pytest.raises(IntegrityError, match="different content"):
        candidate_projection(method, SOURCE, {"child_id": "b", "proposed_meta_source": "meta A"},
                             candidate=state, active=state, committed=True)


def test_retained_identity_does_not_invent_unknown_deployment_identity():
    method = plugin(state_view=lambda _: StateView((PolicyObject("parent", SOURCE),), None))
    state = snapshot()
    projected = candidate_projection(method, SOURCE, {"child_id": "parent"},
                                     candidate=state, active=state, committed=True)
    assert projected["object_retained_after"] is True
    assert projected["object_deployed_after"] is None


def test_evaluate_rejects_non_mapping_configuration_before_creating_output(tmp_path):
    output = tmp_path / "invalid-config"
    with pytest.raises(ValidationError, match="Configuration must be a JSON object"):
        evaluate("frozen", output, config=[])
    assert not output.exists()


def test_source_archive_includes_all_method_packages_referenced_by_distribution_metadata(tmp_path, monkeypatch):
    packages = {"archive_alpha": "alpha", "archive_beta": "beta"}
    package_files = {}
    for package, marker in packages.items():
        directory = tmp_path / package
        directory.mkdir()
        for filename, raw in {"__init__.py": b"# Installed method package\n",
                              "adapter.py": f"MARKER = {marker!r}\n".encode()}.items():
            (directory / filename).write_bytes(raw)
            package_files[f"{package}/{filename}"] = raw
    info = tmp_path / "archive_fixture-1.0.dist-info"
    info.mkdir()
    metadata_files = {
        "METADATA": b"Metadata-Version: 2.1\nName: archive-fixture\nVersion: 1.0\n",
        "entry_points.txt": (b"[rsi_lab.methods]\n"
                             b"alpha = archive_alpha:PLUGIN\n"
                             b"beta = archive_beta:PLUGIN\n"),
    }
    records = [*package_files, *(f"{info.name}/{name}" for name in metadata_files),
               f"{info.name}/RECORD"]
    metadata_files["RECORD"] = "".join(f"{name},,\n" for name in records).encode()
    for name, raw in metadata_files.items():
        (info / name).write_bytes(raw)
    distribution = plugins.metadata.PathDistribution(info)
    entries = {entry.name: entry for entry in distribution.entry_points}
    monkeypatch.setattr(plugins, "ENTRIES", entries)
    monkeypatch.setattr(plugins, "PLUGINS", {
        name: plugin(name=name, system_id=name) for name in entries})
    monkeypatch.setattr(plugins, "import_module", lambda name:
                        SimpleNamespace(__file__=str(tmp_path / name / "__init__.py")))

    # Selecting alpha still restores both registrations from this distribution.
    # Leaving beta's package out makes fresh discovery fail after uninstall.
    files = plugins.source_files(["alpha"])
    assert files == {**package_files,
                     **{f"{info.name}/{name}": raw for name, raw in metadata_files.items()}}
    assert files[f"{info.name}/entry_points.txt"] == metadata_files["entry_points.txt"]
