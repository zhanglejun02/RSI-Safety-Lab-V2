"""Archive integrity controls; never inspect or move real run artifacts."""
import importlib.util
from pathlib import Path
import tarfile

import pytest


spec = importlib.util.spec_from_file_location(
    "experiment_archive", Path(__file__).resolve().parents[2] / "scripts/archive_experiments.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def workspace(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    for name in ("vendor", "datasets", "current"):
        (runs / name).mkdir()
        (runs / name / "keep").write_bytes(b"infrastructure")
    old = runs / "old" / "root"
    old.mkdir(parents=True)
    (old / "result.json").write_bytes(b'{"unmodified": true}\n')
    (old / "external").symlink_to(tmp_path / "missing")
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "report.txt").write_bytes(b"old report")
    return runs, exports


def test_verified_archive_preserves_bytes_links_and_excludes_infrastructure(tmp_path, monkeypatch):
    runs, exports = workspace(tmp_path)
    monkeypatch.setattr(archive, "check_idle", lambda: None)
    result = archive.archive_experiments(runs, exports,
        ["archive", "current", "vendor", "datasets"], execute=True)
    assert result["verified"] and result["originals_removed"]
    assert not (runs / "old").exists()
    for name in ("current", "vendor", "datasets"):
        assert (runs / name / "keep").read_bytes() == b"infrastructure"
    with tarfile.open(result["archive"], "r:gz") as packed:
        assert packed.extractfile("runs/old/root/result.json").read() == b'{"unmodified": true}\n'
        assert packed.extractfile("exports/report.txt").read() == b"old report"
        assert packed.getmember("runs/old/root/external").issym()


def test_failed_verification_keeps_originals_in_staging(tmp_path, monkeypatch):
    runs, exports = workspace(tmp_path)
    monkeypatch.setattr(archive, "check_idle", lambda: None)

    def corrupt(*_):
        raise ValueError("digest mismatch")

    monkeypatch.setattr(archive, "verify", corrupt)
    with pytest.raises(ValueError, match="digest mismatch"):
        archive.archive_experiments(runs, exports,
            ["archive", "current", "vendor", "datasets"], execute=True)
    original = next((runs / "archive").glob("*/staging/runs/old/root/result.json"))
    assert original.read_bytes() == b'{"unmodified": true}\n'


def test_credential_like_file_blocks_before_move(tmp_path):
    runs, exports = workspace(tmp_path)
    (runs / "old" / ".env").write_text("sensitive")
    with pytest.raises(ValueError, match="Credential-like"):
        archive.archive_experiments(runs, exports,
            ["archive", "current", "vendor", "datasets"], execute=True)
    assert (runs / "old" / ".env").exists()
    assert not (runs / "archive").exists()
