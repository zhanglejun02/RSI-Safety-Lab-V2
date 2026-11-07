"""Content identity of installed Python sources, independent of a checkout."""
import hashlib
from pathlib import Path
from rsi_lab.serialization import digest


def implementation_fingerprint():
    root = Path(__file__).parent
    sources = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(root.rglob("*.py"))}
    return digest(sources)
