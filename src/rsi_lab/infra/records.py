"""Checksummed immutable JSON records shared by runners and runtime journals."""
from pathlib import Path
from rsi_lab.errors import ConflictError, IntegrityError
from rsi_lab.infra.artifacts import _checked_path, _publish_bytes
from rsi_lab.serialization import canonical_bytes, decode_json, digest


def save_record(path, value):
    path = _checked_path(Path(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {"record": value, "sha256": digest(value)}
    data = canonical_bytes(envelope)
    if not _publish_bytes(data, path) and path.read_bytes() != data:
        raise ConflictError(f"Immutable record changed: {path.name}")


def read_record(path):
    value = decode_json(_checked_path(Path(path)).read_bytes())
    if set(value) != {"record", "sha256"} or digest(value["record"]) != value["sha256"]:
        raise IntegrityError("Record checksum mismatch")
    return value["record"]
