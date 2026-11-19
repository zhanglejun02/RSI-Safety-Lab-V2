"""Execute a versioned Harness through a bounded, credential-free RPC process.

The candidate owns Python control flow. The parent alone dispatches model and
tool effects. No candidate source is imported into the experiment host.
"""
import json
import os
from pathlib import Path
import selectors
import select
import signal
import subprocess
import sys
import tempfile
import time

from rsi_lab.errors import UnsupportedCapability, ValidationError
from rsi_lab.serialization import decode_json

WORKER = Path(__file__).with_name("harness_worker.py")
MAX_MESSAGE_BYTES = 262144
MAX_OUTPUT_BYTES = 4 * 1048576
WALL_SECONDS = 450


class HarnessExecutionError(ValidationError):
    """A terminated candidate, distinct from a failure of the trusted host."""


def executable():
    app = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    return app.resolve() if app.exists() else Path(sys.executable).resolve()


def command(workspace):
    """Unsupported hosts fail before dispatch; never substitute a plain subprocess."""
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists():
        raise UnsupportedCapability("Executable Harness requires macOS sandbox-exec; no unsandboxed fallback")
    python = executable()
    read_dirs = [Path(sys.base_prefix).resolve(), Path("/System/Library"), Path("/usr/lib"), workspace]
    quote = lambda p: json.dumps(str(p))
    reads = " ".join("(subpath " + quote(p) + ")" for p in read_dirs)
    profile = ("(version 1)(deny default)(allow file-read-metadata)(allow sysctl-read)"
        "(allow mach-lookup)(allow process-info*)"
        "(allow process-exec (literal " + quote(python) + "))"
        "(allow file-read* " + reads + " (literal " + quote(WORKER.resolve()) + ")"
        " (literal \"/\") (literal \"/dev/urandom\") (literal \"/dev/null\"))"
        "(allow file-write* (literal \"/dev/null\"))")
    return ["/usr/bin/sandbox-exec", "-p", profile, str(python), "-I", "-S", "-B",
            str(WORKER.resolve()), str(workspace)]


def execute(harness, task, dispatch, *, wall_seconds=WALL_SECONDS):
    """Dispatch only validated public RPCs; the caller owns effect reservations."""
    with tempfile.TemporaryDirectory(prefix="rsi-harness-") as tmp:
        root = Path(tmp).resolve()
        resources = root / "resources"
        resources.mkdir()
        for name, content in harness.files.items():
            target = resources / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (root / "input.json").write_text(json.dumps({"task": task, "entrypoint": harness.entrypoint,
                                                   "files": list(harness.files)}))
        proc = subprocess.Popen(command(root), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=root, start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TMPDIR": str(root)})
        os.set_blocking(proc.stdin.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "rpc")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        started, total, ready, count = time.monotonic(), 0, False, 0
        buffer, stderr = b"", b""
        try:
            while selector.get_map():
                if time.monotonic() - started > wall_seconds:
                    raise HarnessExecutionError("harness_timeout")
                for key, _ in selector.select(timeout=min(0.25, wall_seconds)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > MAX_OUTPUT_BYTES:
                        raise HarnessExecutionError("harness_output_limit")
                    if key.data == "stderr":
                        stderr += chunk
                        continue
                    buffer += chunk
                    if len(buffer) > MAX_MESSAGE_BYTES and b"\n" not in buffer:
                        raise HarnessExecutionError("harness_message_limit")
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if len(line) > MAX_MESSAGE_BYTES:
                            raise HarnessExecutionError("harness_message_limit")
                        try:
                            event = decode_json(line)
                        except (ValidationError, ValueError, UnicodeError, RecursionError) as exc:
                            raise HarnessExecutionError("invalid_harness_rpc") from exc
                        if event == {"type": "ready"} and not ready:
                            ready = True
                            continue
                        if type(event) is not dict or not ready:
                            raise HarnessExecutionError("invalid_harness_rpc")
                        if set(event) == {"type", "answer"} and event["type"] == "done":
                            if event["answer"] is not None and type(event["answer"]) is not str:
                                raise HarnessExecutionError("invalid_harness_answer")
                            return event["answer"]
                        if set(event) == {"type", "error"} and event["type"] == "failed":
                            raise HarnessExecutionError("harness_failed")
                        count += 1
                        if count > 2 * task["max_steps"] + 2:
                            raise HarnessExecutionError("harness_rpc_limit")
                        response = dispatch(event)
                        payload = json.dumps(response).encode() + b"\n"
                        if len(payload) > MAX_MESSAGE_BYTES:
                            raise HarnessExecutionError("harness_response_limit")
                        try:
                            offset = 0
                            while offset < len(payload):
                                if time.monotonic() - started > wall_seconds:
                                    raise HarnessExecutionError("harness_timeout")
                                if not select.select([], [proc.stdin], [], 0.25)[1]:
                                    continue
                                try:
                                    offset += os.write(proc.stdin.fileno(), payload[offset:])
                                except BlockingIOError:
                                    continue
                        except BrokenPipeError as exc:
                            raise HarnessExecutionError("harness_worker_disconnected") from exc
            if b"sandbox_apply" in stderr:
                raise UnsupportedCapability("Host denied Harness sandbox initialization; execute from an allowed local shell")
            if not ready:
                raise UnsupportedCapability("Harness sandbox worker failed to initialize")
            raise HarnessExecutionError("harness_worker_terminated")
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
            selector.close()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
