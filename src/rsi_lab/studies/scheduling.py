"""Independent root jobs with bounded spawn workers and a phase barrier."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import ExitStack
import multiprocessing
import signal

from rsi_lab.errors import ValidationError
from rsi_lab.infra.dispatch import DispatchLimiter
from rsi_lab.infra.runlock import run_lock

DEFAULTS = {"root_workers": 1, "max_in_flight": 1, "requests_per_minute": None,
            "cooldown_seconds": 30, "max_total_calls": None, "max_total_tokens": None}
_limiter = None


def settings(config):
    value = config.get("execution", {})
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValidationError("Unknown execution settings")
    value = DEFAULTS | value
    for key in ("root_workers", "max_in_flight"):
        if type(value[key]) is not int or not 1 <= value[key] <= 8:
            raise ValidationError(key + " must be an integer in [1,8]")
    for key in ("requests_per_minute", "max_total_calls", "max_total_tokens"):
        if value[key] is not None and (type(value[key]) is not int or value[key] < 1):
            raise ValidationError(key + " must be a positive integer or null")
    if type(value["cooldown_seconds"]) is not int or not 0 <= value["cooldown_seconds"] <= 300:
        raise ValidationError("cooldown_seconds must be an integer in [0,300]")
    return value


def allocation(config, roots, final):
    """Reserve the full provider allocation up front, without a racing shared budget."""
    options, budget = settings(config), config["budget"]
    calls, tokens = 0, 0
    for root in roots:
        phases = ["train"] + ["test"] * len(final)
        if root["system"] != "frozen":
            phases.append("editor")
        if root["arm"] == "probe_gate":
            phases.append("probe")
        judges = len(final) - 1 - (int("xstest" in final) if config["mode"] == "scripted" else 0)
        phases += ["judge"] * judges
        for phase in phases:
            calls += (config["slots"] * budget["editor_calls_per_slot"] if phase == "editor"
                      else budget[phase + "_calls"])
            if config["mode"] == "http":
                role = phase if phase in ("editor", "judge") else "actor"
                tokens += config["models"][role].get("max_total_tokens", 1000000)
    for key, total in (("max_total_calls", calls), ("max_total_tokens", tokens)):
        if options[key] is not None and total > options[key]:
            raise ValidationError(f"{key} cannot cover the whole study allocation ({total}); reduce per-provider caps first")
    return {**options, "allocated_calls": calls, "allocated_tokens": tokens,
            "budget_policy": "full provider caps checked before dispatch; no cross-root budget race",
            "token_bound": "reservation estimates, not a universal tokenizer or monetary guarantee",
            "scheduling": "serial" if options["root_workers"] == 1 else "spawn_process_per_root_phase"}


def limiter():
    return _limiter


def ensure_roots_idle(output, roots):
    """A replaced coordinator must not skip over a still-running root's saved result."""
    with ExitStack() as locks:
        for root in roots:
            directory = output / root["path"]
            directory.mkdir(parents=True, exist_ok=True)
            locks.enter_context(run_lock(directory))


def _initialize(shared):
    global _limiter
    _limiter = shared
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # The coordinator drains in-flight jobs before releasing its lock.


class Scheduler:
    def __init__(self, options):
        self.workers = options["root_workers"]
        self.context = multiprocessing.get_context("spawn") if self.workers > 1 else None
        self.limiter = DispatchLimiter(options["max_in_flight"], options["requests_per_minute"],
                                       options["cooldown_seconds"], context=self.context)

    def run(self, function, jobs):
        global _limiter
        jobs = iter(jobs)
        if self.workers == 1:
            previous, _limiter = _limiter, self.limiter
            try:
                for job in jobs:
                    function(*job)
            finally:
                _limiter = previous
            return
        # Fresh process state per root/phase; adapters, providers and worlds never cross IPC.
        pool = ProcessPoolExecutor(max_workers=self.workers, mp_context=self.context,
            max_tasks_per_child=1, initializer=_initialize, initargs=(self.limiter,))
        pending = set()
        try:
            for _ in range(self.workers):
                if (job := next(jobs, None)) is not None:
                    pending.add(pool.submit(function, *job))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for result in done:
                    result.result()  # Surface failure before scheduling any additional roots.
                for _ in done:
                    if (job := next(jobs, None)) is not None:
                        pending.add(pool.submit(function, *job))
        finally:
            # No job restart. Already-running roots finish; queued work is cancelled on failure.
            pool.shutdown(wait=True, cancel_futures=True)
