"""Durable, no-replace file publication for the trusted local controller.

The checks prevent accidental corruption and obvious path substitution. They are
not a replacement for OS isolation against another process running as this user.
"""

from __future__ import annotations

import os
from pathlib import Path
import uuid

from rsi_lab.errors import IntegrityError


def _checked_path(path: Path) -> Path:
    """Reject symlinks after normalizing macOS's fixed temp-directory aliases."""
    path = Path(os.path.abspath(path))
    # macOS's tempfile.gettempdir() uses /var; /var and /tmp are OS aliases for
    # /private/var and /private/tmp. Normalize only these exact system aliases,
    # not arbitrary user-created symlinks or object-store descendants.
    for alias in (Path("/var"), Path("/tmp")):
        target = Path("/private") / alias.name
        if path != alias and path.is_relative_to(alias) and alias.is_symlink() and alias.resolve() == target:
            path = target / path.relative_to(alias)
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise IntegrityError(f"Symbolic link is not allowed: {part}")
    return path


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_bytes(data: bytes, destination: Path, *, mode: int = 0o444) -> bool:
    """Publish durable bytes without replacing an existing directory entry.

    Return False if another writer already published this destination. Callers
    must verify that existing object before treating the operation as successful.
    """
    destination = _checked_path(destination)
    temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        try:
            # link() is an atomic, no-replace publication on the same filesystem.
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            return False
        _fsync_directory(destination.parent)
        return True
    finally:
        temporary.unlink(missing_ok=True)
