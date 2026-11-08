"""Verify a completed run using its own frozen source, without new execution.

The archived package is restored into a separate directory and loaded by a fresh
interpreter. Only trusted lab-produced archives should be reviewed: source hashes
establish identity, not permission to execute arbitrary third-party Python.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import zipfile

INSPECTORS = {
    "rsi-safety-study-v1": "safety_study",
    "agent-benchmark-matrix-v1": "agent_bench",
    "agent-benchmark-matrix-v2": "agent_bench",
    "banking-frozen-discrimination-v1": "banking_profile",
    "banking-frozen-discrimination-v2": "frozen_profile",
    "banking-h2-case-finding-v1.1": "banking_h2",
    "banking-h2-case-finding-v2": "paired_search",
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate record field")
        result[key] = value
    return result


def _read(path):
    value = json.loads(path.read_bytes(), object_pairs_hook=_unique)
    if set(value) != {"record", "sha256"} or _digest(value["record"]) != value["sha256"]:
        raise ValueError("Record checksum mismatch: " + path.name)
    return value["record"]


def _write(path, value):
    with path.open("xb") as stream:
        stream.write(_canonical({"record": value, "sha256": _digest(value)}))


def inventory(directory):
    values = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Frozen review does not follow symlinks")
        if path.is_file():
            values[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def _source(run):
    manifest = _read(run / "source-manifest.json")
    archive_path = run / "source.zip"
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Source archive checksum mismatch")
    result = {}
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest["files"]):
            raise ValueError("Source archive inventory mismatch")
        for name, expected in manifest["files"].items():
            relative = PurePosixPath(name)
            if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                    or relative.parts[0] != "rsi_lab" or archive.getinfo(name).is_dir()):
                raise ValueError("Unsafe source archive path")
            raw = archive.read(name)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("Archived source checksum mismatch: " + name)
            result[name] = raw
    return result


def _ledger_inventory(run):
    result = {}
    for path in sorted(run.rglob("*.sqlite")):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            result[str(path.relative_to(run))] = _digest(list(db.iterdump()))
    return result


def _worker(output):
    source, run = output / "source", output / "run"
    sys.path.insert(0, str(source))
    import rsi_lab
    from rsi_lab.frozen import implementation_fingerprint
    from rsi_lab.infra.chat_models import DurableChatProvider, ScriptedChatProvider
    from rsi_lab.agents.runtime import ActorRuntime

    if not Path(rsi_lab.__file__).resolve().is_relative_to(source):
        raise ValueError("Reviewer loaded a different installed package")
    manifest = _read(run / "manifest.json")
    if implementation_fingerprint() != manifest["implementation"]:
        raise ValueError("Restored source fingerprint differs from run")

    def forbidden(*args, **kwargs):
        raise AssertionError("Review cannot dispatch models or create environment effects")

    import socket
    socket.create_connection = socket.socket.connect = socket.socket.connect_ex = forbidden
    DurableChatProvider.generate = ScriptedChatProvider.generate = forbidden
    ActorRuntime.execute = forbidden
    from rsi_lab.benchmarks import agentdojo, local_transfer
    agentdojo.new_episode = local_transfer.new_episode = forbidden
    try:
        from rsi_lab.benchmarks import banking_profile
        banking_profile.new_episode = forbidden
    except ImportError:
        pass
    expected = _read(run / "summary.json")
    before = _ledger_inventory(run)
    inspector = importlib.import_module("rsi_lab.studies." + INSPECTORS[manifest["protocol"]])
    actual = inspector.inspect(run)
    if actual != expected or before != _ledger_inventory(run):
        raise ValueError("Frozen inspection changed a result or ledger")
    requests = 0
    for path in run.rglob("*.sqlite"):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_requests'").fetchone():
                continue
            db.row_factory = sqlite3.Row
            for row in db.execute("SELECT * FROM chat_requests"):
                raw = row["request_json"]
                raw = raw.encode() if isinstance(raw, str) else raw
                if hashlib.sha256(raw).hexdigest() != row["request_sha"]:
                    raise ValueError("Provider request checksum mismatch")
                if row["response_bytes"] is not None and hashlib.sha256(row["response_bytes"]).hexdigest() != row["response_sha"]:
                    raise ValueError("Provider response checksum mismatch")
                requests += 1
    _write(output / "replay.json", {"protocol": manifest["protocol"], "analysis_sha256": _digest(actual),
        "implementation": implementation_fingerprint(), "requests": requests,
        "api_calls": 0, "fresh_effects": 0, "network_disabled": True, "logical_ledgers_unchanged": True})


def review(run, output):
    run, output = Path(run).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(run):
        raise ValueError("Use a new review output outside the input run")
    before = inventory(run)
    manifest = _read(run / "manifest.json")
    if manifest["protocol"] not in INSPECTORS or not (run / "summary.json").exists():
        raise ValueError("A completed supported benchmark run is required")
    files = _source(run)
    output.mkdir(parents=True)
    for name, raw in files.items():
        path = output / "source" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    shutil.copytree(run, output / "run")
    reviewer = output / "reviewer.py"
    shutil.copyfile(__file__, reviewer)
    # -I prevents ambient PYTHONPATH/user-site imports; only the frozen package
    # and explicitly installed third-party dependencies are available.
    environment = {key: value for key, value in os.environ.items()
                   if key in ("PATH", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT")}
    with (output / "worker.log").open("wb") as log:
        child = subprocess.run([sys.executable, "-I", "-B", str(reviewer), "--worker", str(output)],
                               cwd=output, env=environment, stdout=log, stderr=subprocess.STDOUT,
                               timeout=120)
    unchanged = before == inventory(run)
    result = {"protocol": manifest["protocol"], "worker_exit_code": child.returncode,
              "originals_unchanged": unchanged, "original_files": len(before),
              "original_inventory_sha256": _digest(before),
              "reviewer_sha256": hashlib.sha256(reviewer.read_bytes()).hexdigest(),
              "replay": _read(output / "replay.json") if child.returncode == 0 else None}
    _write(output / "review.json", result)
    if child.returncode or not unchanged:
        raise ValueError("Frozen review failed; see review.json and worker.log")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    _worker(parser.parse_args().worker)
