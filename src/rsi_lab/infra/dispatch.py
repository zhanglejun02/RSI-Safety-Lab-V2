"""Bounded, process-shared HTTP admission; failed requests are never retried."""
from contextlib import contextmanager
import math
import threading
import time
from types import SimpleNamespace


class DispatchLimiter:
    def __init__(self, concurrent=1, requests_per_minute=None, cooldown_seconds=30, *, context=None):
        factory = context or threading
        self.slots = factory.BoundedSemaphore(concurrent)
        self.lock = factory.Lock()
        self.next_start = context.Value("d", 0, lock=False) if context else SimpleNamespace(value=0)
        self.interval = 60 / requests_per_minute if requests_per_minute else 0
        self.cooldown_seconds = cooldown_seconds

    @contextmanager
    def admit(self):
        started = time.monotonic()
        with self.slots:
            while True:
                with self.lock:
                    delay = self.next_start.value - time.monotonic()
                    if delay <= 0:
                        self.next_start.value = time.monotonic() + self.interval
                        break
                time.sleep(min(delay, 1))
            yield time.monotonic() - started

    def backoff(self, status, retry_after=None):
        if status != 429 and not (status is not None and 500 <= status <= 599):
            return
        delay = self.cooldown_seconds
        try:
            value = float(retry_after)
            if math.isfinite(value):
                delay = max(delay, min(max(value, 0), 300))
        except (TypeError, ValueError):
            pass
        with self.lock:
            self.next_start.value = max(self.next_start.value, time.monotonic() + delay)
