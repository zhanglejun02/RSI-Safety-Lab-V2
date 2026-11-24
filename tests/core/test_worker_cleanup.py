"""Exit-race tolerance must never conceal a still-running isolated worker."""
import subprocess

import pytest

from rsi_lab.agents import harness_process


@pytest.mark.parametrize("error", [PermissionError, ProcessLookupError])
def test_signal_race_is_tolerated_only_after_reaping(monkeypatch, error):
    waits = []
    class Exiting:
        pid = 123
        def poll(self):
            return None
        def wait(self, timeout):
            waits.append(timeout)
            return 0
    def signal(*args):
        raise error("simulated exiting sandbox")
    monkeypatch.setattr(harness_process.os, "killpg", signal)
    harness_process._terminate(Exiting())
    assert waits == [0.25, 5]


def test_live_worker_permission_error_is_not_suppressed(monkeypatch):
    class Live:
        pid = 123
        def poll(self):
            return None
        def wait(self, timeout):
            raise subprocess.TimeoutExpired("worker", timeout)
    def signal(*args):
        raise PermissionError("signal denied")
    monkeypatch.setattr(harness_process.os, "killpg", signal)
    with pytest.raises(PermissionError, match="signal denied"):
        harness_process._terminate(Live())
