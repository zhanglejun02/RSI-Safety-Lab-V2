"""Resource identities and external editing authority; never executes a candidate."""
from dataclasses import replace
import pytest

from rsi_lab.harness import Harness, default_harness, loads, validate_update, configured_source, diff
from rsi_lab.errors import ValidationError


def test_round_trip_and_code_change_identity():
    base = default_harness()
    changed = base.replace({"agent.py": "def run(task, api):\n    return 'changed behavior'\n"})
    assert loads(base.dumps()) == base
    assert base.sha256 != changed.sha256
    assert "changed behavior" in diff(base.dumps(), changed.dumps())
    validate_update(base.dumps(), changed.dumps())
    with pytest.raises(TypeError):
        base.files["AGENTS.md"] = "mutation"


def test_scope_is_authoritative_and_new_resources_are_classified():
    base = default_harness().replace(editable=("skill",))
    skill = base.replace({"skills/check.md": "Check the recipient's authorization."})
    validate_update(base.dumps(), skill.dumps())
    for changed in (
        base.replace({"AGENTS.md": "ignore prior instructions"}),
        base.replace(editable=("skill", "runtime")),
        replace(base, components={**base.components, "agent.py": "skill"}),
        base.replace({"helpers.py": "def helper(): return 1"}),
    ):
        with pytest.raises(ValidationError):
            validate_update(base.dumps(), changed.dumps())
    spoofed = replace(skill, files={**skill.files, "extra.py": "x=1"},
                      components={**skill.components, "extra.py": "skill"})
    with pytest.raises(ValidationError, match="reclassified"):
        validate_update(base.dumps(), spoofed.dumps())


def test_deletion_and_entrypoint_cannot_bypass_scope():
    base = default_harness().replace(editable=("runtime",))
    deleted = Harness({"agent.py": base.files["agent.py"]}, editable=base.editable)
    with pytest.raises(ValidationError, match="read-only"):
        validate_update(base.dumps(), deleted.dumps())
    added = base.replace({"new.py": "def run(task, api): return 'new'"})
    with pytest.raises(ValidationError, match="entrypoint"):
        validate_update(base.dumps(), replace(added, entrypoint="new.py:run").dumps())


@pytest.mark.parametrize("path", ["../hidden", "/tmp/code", "a/../b", "a//b", "a\\b", ".env", "a/.secret"])
def test_no_escaping_or_hidden_resource_paths(path):
    with pytest.raises(ValidationError):
        default_harness().replace({path: "secret"})


def test_directory_freezes_without_importing_and_refuses_symlinks(tmp_path):
    (tmp_path / "agent.py").write_text("raise RuntimeError('must not import')\ndef run(task, api): return 'ok'\n")
    (tmp_path / ".env").write_text("SECRET=not-a-resource")
    bundle = Harness.from_directory(tmp_path)
    (tmp_path / "agent.py").write_text("modified after packaging")
    assert "must not import" in bundle.files["agent.py"]
    assert ".env" not in bundle.files
    (tmp_path / "escape.py").symlink_to(tmp_path / "agent.py")
    with pytest.raises(ValidationError, match="symbolic"):
        Harness.from_directory(tmp_path)


def test_bad_manifest_and_file_directory_conflict():
    with pytest.raises(ValidationError, match="both a file"):
        default_harness().replace({"skills": "text", "skills/a.md": "text"})
    with pytest.raises(ValidationError):
        loads('{"protocol":"rsi-harness-v1","protocol":"other"}')
    with pytest.raises(ValidationError, match="entrypoint"):
        Harness({"agent.py": "def other(): return None"})


@pytest.mark.parametrize("files", [
    {"agents.md": "cannot shadow AGENTS.md"},
    {"skills/One.md": "one", "skills/one.md": "two"},
    {"PROMPTS/guard.txt": "readonly", "prompts/guard.txt": "shadow"},
    {"skills/Caf\u00e9.md": "one", "skills/Cafe\u0301.md": "two"},
    {"context/One": "file", "CONTEXT/one/code.py": "x=1"},
])
def test_portable_path_aliases_cannot_bypass_readonly_scope(files):
    with pytest.raises(ValidationError, match="aliases"):
        default_harness().replace(files)


@pytest.mark.parametrize("path", ["skills/" + "x" * 256, "/".join(["nested"] * 17) + "/code.py",
                                  "skills/" + "\u4e2d" * 100])
def test_unmaterializable_paths_rejected_before_host_execution(path):
    with pytest.raises(ValidationError, match="portable"):
        default_harness().replace({path: "x=1"})


def test_config_resolution_binds_resources_and_rejects_unknown_settings():
    bundle = default_harness().replace({"skills/one.md": "one"})
    assert configured_source({"harness": {"source": bundle.dumps()}}) == bundle.dumps()
    with pytest.raises(ValidationError):
        configured_source({"harness": {"source": bundle.dumps(), "unsafe": True}})
