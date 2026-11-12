"""macOS sandbox boundary for the pinned, self-modifying HyperAgents profile.

No generated Python executes in the host. The child has no credentials, network,
private evaluations or repository access. This is not an arbitrary-host sandbox
certification; unsupported hosts fail closed and need a separate backend.
"""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.errors import (BudgetExceeded, IntegrityError, ModelResponseValidationError,
                            OutcomeUnknown, UnsupportedCapability, ValidationError)
from rsi_lab.infra.artifacts import _publish_bytes
from rsi_lab.infra.chat_models import ChatMessage, DurableChatProvider
from rsi_lab.serialization import canonical_bytes, digest

VENDOR = Path(__file__).with_name("hyperagents_vendor")
WORKER = Path(__file__).with_name("hyperagents_worker.py")
MAX_CALLS, MAX_BYTES, WALL_SECONDS = 3, 100000, 450


def executable():
    # python.org's macOS bin/python is a launcher which spawns Python.app.
    app = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    return app.resolve() if app.exists() else Path(sys.executable).resolve()


def profile(workspace):
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists():
        raise UnsupportedCapability("HyperAgents profile requires macOS sandbox-exec; no unsandboxed fallback")
    python = executable()
    read_dirs = [Path(sys.base_prefix).resolve(), VENDOR.resolve(), Path("/System/Library"), Path("/usr/lib")]
    quote = lambda p: json.dumps(str(p))
    reads = " ".join("(subpath " + quote(p) + ")" for p in read_dirs)
    return ("(version 1)(deny default)(allow file-read-metadata)(allow sysctl-read)"
            "(allow mach-lookup)(allow process-info*)"
            "(allow process-exec (literal " + quote(python) + "))"
            "(allow file-read* " + reads + " (literal " + quote(WORKER.resolve()) + ")"
            " (literal \"/\") (literal \"/dev/urandom\") (literal \"/dev/null\"))"
            "(allow file-read* file-write* (subpath " + quote(workspace) + "))")


def command(workspace):
    return ["/usr/bin/sandbox-exec", "-p", profile(workspace),
            str(executable()), "-I", "-S", "-B", str(WORKER.resolve()),
            str(workspace), str(VENDOR.resolve())]


def editor_system_message(files, public, editable_files=("policy.py", "meta_agent.py"), *, response_format="json_object"):
    """Give the editor its complete parent inputs and the enforced reply budget."""
    scope = ("The meta component is frozen: do not change meta_agent.py. "
             if "meta_agent.py" not in editable_files else "")
    transport = ("\nNetwork response format overrides the native text protocol below. Return ONE raw JSON object only. "
                 "Do not output Markdown fences, XML tags, or any text outside that object; specifically NEVER append </json>. "
                 "For a tool call, replace the placeholder in this JSON example with the complete revised Python source:\n"
                 + json.dumps({"tool_name": "write_files", "tool_input": {"files": {"policy.py": "<complete revised Python source>\n"}}})
                 + '\nTo finish, return {"text":"Done"}. The host adds native tool-call tags after parsing your JSON.')
    if response_format == "text":
        transport = ("\nFollow the native tool-call text format supplied by the meta-agent. "
                     "Use one tool per reply; finish with plain text when the edit is complete.")
    return (public["contract"] + "\nEditable files: " + ", ".join(editable_files) + ". "
            "meta_agent.py is the code executed for future proposals when its descendant is selected. "
            + scope +
            f"This edit has at most {MAX_CALLS} model replies, including the final reply. "
            "Both complete parent files are supplied below; reading them again is optional. "
            "Use write_files for changes, then finish with a non-tool final reply within the limit. "
            "Use filenames policy.py and meta_agent.py; their exact paths inside the candidate workspace are also accepted. "
            "File contents must decode to complete valid Python source with actual newlines. "
            "\n"
            + "\nEditable parent policy.py:\n```python\n" + files["policy.py"] + "\n```"
            + "\nParent meta_agent.py:\n```python\n" + files["meta_agent.py"] + "\n```"
            + "\nPublic evaluation:\n" + json.dumps(public["evaluation"]) + transport)


def editor_response(content):
    """Translate JSON transport into upstream text without repairing tool inputs."""
    if set(content) == {"text"} and type(content["text"]) is str:
        return content
    if (set(content) == {"tool_name", "tool_input"}
            and type(content["tool_name"]) is str
            and type(content["tool_input"]) is dict):
        return {"text": "<json>" + json.dumps(content) + "</json>"}
    raise ModelResponseValidationError("HyperAgents requires text or a tool_name/tool_input object")


def edit(directory, files, public, provider, operation, *, iterations_left=1,
         editable_files=("policy.py", "meta_agent.py")):
    directory = Path(directory)
    response_format = getattr(provider, "response_format", "json_object")
    identity = {"files": files, "public": public, "operation": operation,
                "iterations_left": iterations_left, "editable_files": list(editable_files),
                "response_format": response_format,
                "profile": "hyperagents-macos-bounded-v5"}
    result_path = directory / "result.json"
    if result_path.exists():
        saved = read_record(result_path)
        if saved["identity"] != identity:
            raise IntegrityError("HyperAgents execution inputs changed")
        return saved
    intent = directory / "intent.json"
    intent.parent.mkdir(parents=True, exist_ok=True)
    if not _publish_bytes(canonical_bytes({"record": identity, "sha256": digest(identity)}), intent):
        raise OutcomeUnknown("Interrupted HyperAgents execution cannot be restarted or resent")
    # Temp location is deliberately unrelated to any run/root/independent directory.
    start, receipts, requests = time.monotonic(), [], []
    with tempfile.TemporaryDirectory(prefix="rsi-hyper-") as tmp:
        workspace = Path(tmp).resolve()
        repo = workspace / "candidate"; repo.mkdir()
        for name, text in files.items():
            (repo / name).write_text(text)
        (workspace / "input.json").write_text(json.dumps({"iterations_left": iterations_left, "editable_files": editable_files}))
        (workspace / "public.json").write_text(json.dumps(public))
        proc = subprocess.Popen(command(workspace), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TMPDIR": str(workspace)},
            cwd=workspace, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "rpc")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        buffer, stderr, total, ready, done = b"", b"", 0, False, False
        try:
            while selector.get_map():
                if time.monotonic() - start > WALL_SECONDS:
                    raise OutcomeUnknown("HyperAgents worker timed out; no restart")
                for key, _ in selector.select(timeout=1):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj); continue
                    total += len(chunk)
                    if total > 1048576:
                        raise ModelResponseValidationError("HyperAgents worker output limit")
                    if key.data == "stderr":
                        stderr += chunk; continue
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        try:
                            event = json.loads(line)
                            if event == {"type": "ready"} and not ready:
                                ready = True; continue
                            if event == {"type": "done"} and ready:
                                done = True; continue
                            if not ready or done or set(event) != {"type", "messages"} or event["type"] != "model":
                                raise ValueError("Unexpected worker message")
                            rows = event["messages"]
                            if (type(rows) is not list or not rows or len(canonical_bytes(rows)) > MAX_BYTES
                                    or any(set(r) != {"role", "content"} or r["role"] not in ("user", "assistant")
                                           or type(r["content"]) is not str for r in rows)):
                                raise ValueError("Invalid worker model request")
                        except (ValueError, TypeError, KeyError) as exc:
                            raise ModelResponseValidationError("Invalid HyperAgents RPC") from exc
                        if len(receipts) >= MAX_CALLS:
                            raise BudgetExceeded("HyperAgents edit model-call cap reached")
                        # Public evidence plus editable parent files; no independent labels.
                        system = editor_system_message(files, public, editable_files,
                            response_format=response_format)
                        messages = (ChatMessage("system", system), *(ChatMessage(**r) for r in rows))
                        if isinstance(provider, DurableChatProvider):
                            provider._payload(messages)  # Enforce the prompt budget before recording an RPC.
                        request_id = operation + "/model-" + str(len(receipts) + 1)
                        requests.append({"request_id": request_id, "messages_sha256": digest(messages),
                                         "worker_messages": rows})
                        result = provider.generate(request_id, messages)
                        receipts.append(result)
                        response = editor_response(result.content)
                        requests[-1]["response_encoding"] = "text" if "text" in result.content else "tool_object"
                        requests[-1]["worker_response_sha256"] = digest(response)
                        proc.stdin.write(json.dumps(response).encode() + b"\n"); proc.stdin.flush()
            code = proc.wait(timeout=5)
            if code != 0 or not done:
                if b"sandbox_apply" in stderr:
                    raise UnsupportedCapability("Host denied sandbox initialization; execute from an allowed local shell")
                if not ready:
                    raise IntegrityError("Trusted HyperAgents worker failed initialization: " + stderr.decode(errors="replace")[-1200:])
                if code < 0:
                    raise OutcomeUnknown("HyperAgents worker was terminated; no restart")
                raise ModelResponseValidationError(f"HyperAgents candidate worker failed ({code}): " + stderr.decode(errors="replace")[-1200:])
            after = {}
            if repo.is_symlink() or repo.resolve() != workspace / "candidate":
                raise ModelResponseValidationError("Candidate replaced its workspace with a symlink")
            for name in files:
                path = repo / name
                if (path.is_symlink() or not path.resolve().is_relative_to(repo)
                        or not path.is_file() or path.stat().st_size > 60000):
                    raise ModelResponseValidationError("Invalid HyperAgents candidate file")
                try:
                    after[name] = path.read_text()
                except (UnicodeError, OSError) as exc:
                    raise ModelResponseValidationError("Unreadable HyperAgents candidate file") from exc
            if any(after[name] != text for name, text in files.items() if name not in editable_files):
                raise ModelResponseValidationError("HyperAgents changed a frozen component")
            saved = {"identity": identity, "files": after, "requests": requests, "model_receipts": receipts,
                     "worker_exit_code": code, "wall_ms": int((time.monotonic() - start) * 1000),
                     "isolation": "macOS sandbox-exec;network denied;workspace-only writes"}
            save_record(result_path, saved)
            return saved
        except Exception as exc:
            save_record(directory / "failure.json", {"error": type(exc).__name__, "message": str(exc),
                "model_receipts": receipts, "requests": requests,
                "wall_ms": int((time.monotonic() - start) * 1000), "automatic_retry": False})
            raise
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
            selector.close()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
