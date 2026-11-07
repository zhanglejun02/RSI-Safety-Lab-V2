"""Nonblocking process ownership of a run directory (POSIX hosts)."""
from contextlib import contextmanager
import fcntl

from rsi_lab.errors import ConflictError
from rsi_lab.infra.artifacts import _checked_path


@contextmanager
def run_lock(directory):
    with _checked_path(directory / "runner.lock").open("ab") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConflictError("Another worker owns this run") from exc
        yield
