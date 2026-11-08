"""Operational timing, separate from benchmark scores and optimization feedback."""
from contextlib import contextmanager, closing
import csv
import os
import resource
import sqlite3
import statistics
import sys
import time

from rsi_lab.engine.continuation import read_record, save_record


def _cpu():
    usage = [resource.getrusage(kind) for kind in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)]
    return sum(r.ru_utime + r.ru_stime for r in usage)


@contextmanager
def span(directory, phase):
    directory = directory / "performance"
    directory.mkdir(exist_ok=True)
    attempt = len(list(directory.glob(phase + "-*.json"))) + 1
    started, cpu, timestamp = time.monotonic(), _cpu(), time.time()
    status = "failed"
    try:
        yield
        status = "complete"
    finally:
        elapsed, used = time.monotonic() - started, _cpu() - cpu
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        save_record(directory / f"{phase}-{attempt:04d}.json", {
            "phase": phase, "attempt": attempt, "status": status, "worker_pid": os.getpid(),
            "started_at": timestamp, "finished_at": time.time(), "elapsed_seconds": elapsed,
            "cpu_seconds_including_children": used, "cpu_percent_one_core": 100 * used / elapsed if elapsed else 0,
            "logical_cpu_count": os.cpu_count(), "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024})


def distribution(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "sum": 0, "mean": None, "p50": None, "p95": None}
    return {"count": len(values), "sum": sum(values), "mean": statistics.mean(values),
            "p50": statistics.median(values), "p95": values[max(0, (95 * len(values) + 99) // 100 - 1)]}


def peak_overlap(intervals):
    """Observed client transport overlap; missing timings cannot establish a bound."""
    events = [(timestamp, change) for start, elapsed in intervals if elapsed > 0
              for timestamp, change in ((start, 1), (start + elapsed, -1))]
    active = peak = 0
    for _, change in sorted(events):
        active += change
        peak = max(peak, active)
    return peak


def _csv(path, rows):
    if rows:
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def collect(output, execution):
    episodes, providers, phases, latency, queue, intervals = [], [], [], [], [], []
    for path in sorted(output.glob("roots/*/performance/*.json")):
        phases.append({"root_id": path.parents[1].name, **read_record(path)})
    for path in sorted(output.glob("roots/*/**/*-episodes/*/result.json")):
        row = read_record(path)
        if row.get("version") != "tool-actor.v1":
            continue
        relative = path.relative_to(output)
        episodes.append({"root_id": relative.parts[1], "runtime": str(relative.parent.parent),
            "operation_id": row["identity"]["operation_id"], "policy_sha256": row["identity"]["source_sha256"],
            "case_id": row["case_id"], "elapsed_seconds": row["usage"]["elapsed_seconds"],
            "actor_calls": row["metrics"]["actor_calls"], "tool_calls": row["metrics"]["tool_calls"],
            "stop_reason": row["stop_reason"]})
    for path in sorted(output.glob("roots/**/*.sqlite")):
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_requests'").fetchone():
                continue
            counts = dict(db.execute("SELECT status,COUNT(*) FROM chat_requests GROUP BY status"))
            times = db.execute("SELECT elapsed_seconds,queue_seconds,http_status,started_at FROM chat_timings").fetchall()
        elapsed, waited = [r[0] for r in times], [r[1] for r in times]
        latency.extend(elapsed)
        queue.extend(waited)
        intervals.extend((r[3], r[0]) for r in times)
        total = sum(counts.values())
        providers.append({"journal": str(path.relative_to(output)), "calls": total,
            "timed_calls": len(times), "timing_missing_calls": total - len(times),
            "transport_mean_seconds": distribution(elapsed)["mean"],
            "transport_p95_seconds": distribution(elapsed)["p95"], "queue_seconds": sum(waited),
            "unknown_calls": counts.get("unknown", 0) + counts.get("pending", 0),
            "http_429": sum(t[2] == 429 for t in times),
            "http_5xx": sum(t[2] is not None and 500 <= t[2] <= 599 for t in times)})
    coordinator = [read_record(p) for p in sorted((output / "performance").glob("*.json"))]
    result = {"execution": execution, "coordinator_phases": coordinator,
        "episode_seconds": distribution([r["elapsed_seconds"] for r in episodes]),
        "transport_seconds": distribution(latency), "queue_seconds": distribution(queue),
        "observed_peak_in_flight": peak_overlap(intervals),
        "http_429": sum(p["http_429"] for p in providers),
        "http_5xx": sum(p["http_5xx"] for p in providers),
        "timing_missing_calls": sum(p["timing_missing_calls"] for p in providers),
        "root_phase_count": len(phases),
        "scope": "Operational diagnostics only; control latency is not remote API latency. Peak overlap uses saved client wall-clock intervals, excluding missing timings. CPU is process-tree CPU, not whole-host utilization. Native Inspect episodes are excluded from episode timing."}
    _csv(output / "performance-episodes.csv", episodes)
    _csv(output / "performance-api.csv", providers)
    _csv(output / "performance-roots.csv", phases)
    save_record(output / "performance.json", result)
    return result
