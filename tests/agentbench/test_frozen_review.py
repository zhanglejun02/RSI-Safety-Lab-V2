import hashlib
import json
import zipfile

import pytest

from rsi_lab.agent_bench import default_config, run_experiment
from rsi_lab.review import inventory, review, _source, _write


def test_current_run_review_restores_source_and_leaves_input_unchanged(tmp_path):
    config = default_config()
    config.update(methods=["frozen"], benchmarks=["local_transfer"], slots=1)
    run = tmp_path / "input"
    summary = run_experiment(config, run)
    before = inventory(run)
    result = review(run, tmp_path / "review")
    assert result["worker_exit_code"] == 0
    assert result["originals_unchanged"] and before == inventory(run)
    assert result["replay"]["api_calls"] == result["replay"]["fresh_effects"] == 0
    assert result["replay"]["protocol"] == summary["protocol"]


@pytest.mark.parametrize("name", ["../escaped.py", "/absolute.py", "rsi_lab/../../escape.py"])
def test_review_rejects_source_archive_path_escape(tmp_path, name):
    raw = b"pass\n"
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name, raw)
    _write(tmp_path / "source-manifest.json", {
        "files": {name: hashlib.sha256(raw).hexdigest()},
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()})
    with pytest.raises(ValueError, match="Unsafe"):
        _source(tmp_path)


def test_review_rejects_archive_tampering(tmp_path):
    (tmp_path / "source.zip").write_bytes(b"changed")
    _write(tmp_path / "source-manifest.json", {"archive_sha256": "0" * 64, "files": {}})
    with pytest.raises(ValueError, match="checksum"):
        _source(tmp_path)
