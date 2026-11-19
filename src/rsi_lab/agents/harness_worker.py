"""Small stdlib RPC worker; loaded only inside the OS sandbox."""
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    root = Path(sys.argv[1])
    request = json.loads((root / "input.json").read_text())
    resources = root / "resources"
    channel, incoming = sys.stdout, sys.stdin
    sys.stdout = open(os.devnull, "w")

    def send(value):
        channel.write(json.dumps(value) + "\n")
        channel.flush()

    class API:
        def exchange(self, value):
            send(value)
            response = json.loads(incoming.readline(262145))
            if "error" in response:
                raise ValueError(response["error"])
            return response["result"]

        def model(self, messages, response_format="json_object"):
            return self.exchange({"type": "model", "messages": messages,
                                  "response_format": response_format})

        def tool(self, name, arguments):
            return self.exchange({"type": "tool", "name": name, "arguments": arguments})

        def read(self, path):
            if type(path) is not str or path not in request["files"]:
                raise ValueError("Undeclared Harness resource")
            return (resources / path).read_text()

    send({"type": "ready"})
    filename, function = request["entrypoint"].split(":")
    sys.path.insert(0, str(resources))
    os.chdir(resources)
    spec = importlib.util.spec_from_file_location("candidate_agent", resources / filename)
    agent = importlib.util.module_from_spec(spec)
    sys.modules["candidate_agent"] = agent
    try:
        spec.loader.exec_module(agent)
        answer = getattr(agent, function)(request["task"], API())
        if answer is not None and type(answer) is not str:
            raise ValueError("Harness must return an answer string or None")
        send({"type": "done", "answer": answer})
    except Exception as exc:
        send({"type": "failed", "error": type(exc).__name__})


if __name__ == "__main__":
    main()
