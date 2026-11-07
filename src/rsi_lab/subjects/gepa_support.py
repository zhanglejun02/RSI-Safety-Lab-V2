"""Pinned GEPA dependency verification and its quiet native logger."""
from importlib.metadata import distribution, PackageNotFoundError
from importlib.resources import files
import hashlib

from rsi_lab.errors import IntegrityError, UnsupportedCapability
from rsi_lab.serialization import decode_json

GEPA_REVISION = "8b0ce6cd99a234f6b74daf37558a2ac0ce18f975"
GEPA_URL = "https://github.com/gepa-ai/gepa"

def require_gepa():
    """Require the reviewed source commit, not an unrelated release with same version."""
    try:
        dist = distribution("gepa")
    except PackageNotFoundError as exc:
        raise UnsupportedCapability("GEPA is optional: install rsi-safety-lab[gepa]") from exc
    lock = decode_json(files("rsi_lab").joinpath("data/gepa_source_lock.json").read_text())
    if dist.version != lock["package_version"]:
        raise UnsupportedCapability("GEPA must be installed at release 0.1.4")
    for name, expected in lock["git_blob_sha1"].items():
        path = dist.locate_file(name)
        if not path.is_file():
            raise IntegrityError("Pinned GEPA source is missing: " + name)
        data = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise IntegrityError("GEPA source differs from pinned release: " + name)
    from gepa import optimize
    from gepa.core.adapter import EvaluationBatch
    return optimize, EvaluationBatch



class _QuietLogger:
    def log(self, message):
        pass

