"""Embedded CanvasGate MCP server and a stdio transport for local MCP clients."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

from .backends import WorkflowError
from .mcp_server import handle_request
from .security import ensure_no_secrets, redact


PROVIDERS = {"codex": "Codex", "antigravity": "Antigravity", "claude": "Claude Code"}
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
GUIDE = Path(__file__).with_name("MCP_AGENT_GUIDE.md").read_text(encoding="utf-8")
GUIDE_URI = "canvasgate://docs/agent-guide"
INSTRUCTIONS = (
    "Read canvasgate://docs/agent-guide or call canvasgate_agent_guide before operating the open workspace. "
    "Use canvasgate_status, list workflows, then validate before requesting a simulation. "
    "Simulation and replay save evidence but never commit target writes or call live models."
)


def tool(description, handler, **properties):
    def call(arguments):
        if not isinstance(arguments, dict) or set(arguments) != set(properties):
            raise WorkflowError("Missing or unexpected tool arguments.")
        if any(not isinstance(value, str) or not 1 <= len(value) <= 1024 for value in arguments.values()):
            raise WorkflowError("Tool arguments must be nonempty strings.")
        ensure_no_secrets(arguments)
        return handler(**arguments)
    return {"description": description, "handler": call, "inputSchema": {
        "type": "object", "properties": {key: {"type": "string", "description": value}
                                         for key, value in properties.items()},
        "required": list(properties), "additionalProperties": False}}


def tools_for(studio):
    def status():
        runs = studio.runs()
        return {"ready": True, "workspace": studio.vault.name, "latest_run": runs[0] if runs else None}

    def validate(path):
        saved = studio.read_file(path, graph=True)
        workflow = studio.validate_graph(saved["path"], saved["graph"])
        plan = [{"id": node["id"], "kind": node["kind"]} for node in workflow.plan()]
        return {"valid": True, "plan": plan, "contract_count": len(workflow.contracts)}

    def simulate(path, operation_key):
        saved = studio.read_file(path, graph=True)
        return studio.submit({"path": saved["path"], "expected_sha256": saved["sha256"],
                              "backend": "mock", "strict_isolation": True, "commit": False,
                              "operation_key": operation_key})

    def replay(run_id, operation_key):
        return studio.submit({"operation_key": operation_key}, "replay", run_id)

    def run_status(job_id):
        job = studio.job(job_id)
        if job["state"] == "COMPLETED":
            report = studio.run_detail(job["run_id"])["report"]
            job["decisions"] = {key: {"state": value["state"],
                                     "why": value.get("decision", {}).get("why"),
                                     "tokens": value.get("tokens_used")}
                                for key, value in report["nodes"].items()}
            job["replay_comparison"] = report.get("replay_comparison")
        return job

    key = "A unique operation key. Reuse it when polling or retrying the same submission."
    path = "Vault-relative .canvas path returned by canvasgate_list_workflows."
    return {
        "canvasgate_agent_guide": tool("Read the CanvasGate Studio MCP agent guide.", lambda: {"guide": GUIDE}),
        "canvasgate_status": tool("Check the open workspace and latest run.", status),
        "canvasgate_list_workflows": tool("List workflow paths in the open workspace.",
                                          lambda: {"workflows": studio.files({".canvas"})}),
        "canvasgate_validate_workflow": tool("Validate a saved workflow and return its node order.", validate, path=path),
        "canvasgate_simulate_workflow": tool("Queue an offline mock simulation and save run evidence.", simulate,
                                             path=path, operation_key=key),
        "canvasgate_replay_run": tool("Queue offline replay of a saved Studio run.", replay,
                                      run_id="Run ID in this workspace.", operation_key=key),
        "canvasgate_run_status": tool("Read the status and decisions of a submitted job.", run_status,
                                      job_id="Job ID returned by a simulation or replay submission."),
    }


class AgentConnections:
    def __init__(self, state_path, python_path):
        self.state_path = state_path
        self.python_path = python_path
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.sessions = {}
        self.verified = set()

    def config(self, provider):
        args = ["-I", "-m", "canvasgate.desktop", "--mcp", provider, "--state", str(self.state_path)]
        return {"command": str(self.python_path), "args": args}

    def status(self):
        with self.lock:
            now = time.monotonic()
            return [{"id": key, "name": name, "verified": key in self.verified,
                     "sessions": [value["client"] for value in self.sessions.values()
                                  if value["provider"] == key and value["discovered"] and not value["test"]
                                  and now - value["seen"] <= (24 if value["stdio"] else 60)],
                     "config": self.config(key)} for key, name in PROVIDERS.items()]

    @staticmethod
    def name_provider(name):
        name = name.casefold()
        return next((provider for provider in PROVIDERS if provider in name or
                     (provider == "antigravity" and "gemini" in name)), None)

    def request(self, studio, message, session_id, provider=None):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            raise WorkflowError("Invalid MCP request.")
        method, params = message["method"], message.get("params", {})
        if not isinstance(params, dict):
            raise WorkflowError("Invalid MCP parameters.")
        with self.lock:
            now = time.monotonic()
            self.sessions = {key: value for key, value in self.sessions.items() if now - value["seen"] < 1800}
            if method == "initialize":
                if len(self.sessions) >= 128:
                    raise WorkflowError("Agent session limit reached.")
                client = params.get("clientInfo") or {}
                name = redact(str(client.get("name") or "MCP client"))[:80]
                offered = params.get("protocolVersion")
                protocol = offered if offered in PROTOCOLS else "2025-11-25"
                session_id = secrets.token_hex(16)
                self.sessions[session_id] = {"provider": provider or self.name_provider(name),
                    "client": name, "seen": now, "stdio": provider in PROVIDERS,
                    "test": name == "CanvasGate bridge test", "discovered": False,
                    "initialized": False, "protocol": protocol}
            elif session_id in self.sessions:
                session = self.sessions[session_id]
                session["seen"] = now
                protocol = session["protocol"]
                if method == "notifications/initialized":
                    session["initialized"] = True
                elif method != "ping" and not session["initialized"]:
                    raise WorkflowError("Complete MCP initialization first.")
                if method in {"tools/list", "tools/call"}:
                    session["discovered"] = True
            else:
                return None, None
        reply = handle_request(message, tools=tools_for(studio), protocol=protocol, instructions=INSTRUCTIONS,
                               resources={GUIDE_URI: {"name": "CanvasGate Studio agent guide", "text": GUIDE}})
        return session_id, reply if "id" in message else None

    def detach(self, session_id):
        with self.lock:
            return self.sessions.pop(session_id, None) is not None


class Bridge:
    def __init__(self, state_path, provider):
        self.state_path = Path(state_path)
        self.provider = provider
        self.opener = build_opener(ProxyHandler({}))
        self.active_endpoint = None
        self.session = None
        self.initialization = None
        self.ready = False
        self.done = threading.Event()
        self.lock = threading.Lock()

    def request(self, message=None):
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        port = state["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise WorkflowError("Invalid CanvasGate desktop endpoint.")
        endpoint = f"http://127.0.0.1:{port}/mcp"
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": "Bearer " + state["token"], "X-CanvasGate-Client": self.provider}

        def send(payload, session_id=None):
            request_headers = dict(headers)
            if session_id:
                request_headers["Mcp-Session-Id"] = session_id
            request = Request(endpoint, json.dumps(payload).encode() if payload else None, request_headers,
                              method="POST" if payload else "DELETE")
            with self.opener.open(request, timeout=6) as response:
                return response.headers.get("Mcp-Session-Id"), json.load(response) if response.status == 200 else None

        if message and message.get("method") == "initialize":
            self.initialization = message
            self.session, result = send(message)
            self.active_endpoint = state
            return result
        if self.session and self.active_endpoint != state:
            if message is None:
                return None
            self.session, _ = send(self.initialization)
            send({"jsonrpc": "2.0", "method": "notifications/initialized"}, self.session)
            send({"jsonrpc": "2.0", "id": "bridge-rediscover", "method": "tools/list"}, self.session)
            self.active_endpoint = state
        if not self.session:
            raise WorkflowError("CanvasGate has no attached session.")
        _, result = send(message, self.session)
        return result

    def keep_alive(self):
        while not self.done.wait(6):
            if self.ready:
                try:
                    with self.lock:
                        self.request({"jsonrpc": "2.0", "id": "bridge-ping", "method": "ping"})
                except (OSError, ValueError, KeyError):
                    continue

    def serve(self):
        threading.Thread(target=self.keep_alive, daemon=True).start()
        try:
            for line in sys.stdin.buffer:
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                        continue
                except ValueError:
                    continue
                try:
                    with self.lock:
                        reply = self.request(message)
                        if message.get("method") == "tools/list" and reply and "result" in reply:
                            self.ready = True
                except (OSError, ValueError, KeyError):
                    reply = {"jsonrpc": "2.0", "id": message.get("id"), "error": {
                        "code": -32000, "message": "CanvasGate Studio is unavailable. Open the desktop app and reconnect."}}
                if "id" in message:
                    print(json.dumps(reply), flush=True)
        finally:
            self.done.set()
            if self.session:
                try:
                    with self.lock:
                        self.request()
                except (OSError, ValueError, KeyError):
                    pass


def verify_bridge(connection, provider):
    """Exercise the installed stdio command and its embedded HTTP server."""
    config = connection.config(provider)
    messages = [
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                                                    "clientInfo": {"name": "CanvasGate bridge test", "version": "1"}}},
        {"method": "notifications/initialized"},
        {"id": 2, "method": "tools/list"},
        {"id": 3, "method": "tools/call", "params": {"name": "canvasgate_status"}},
    ]
    result = subprocess.run([config["command"], *config["args"]],
                            input="".join(json.dumps({"jsonrpc": "2.0", **message}) + "\n" for message in messages),
                            text=True, encoding="utf-8", capture_output=True, timeout=15, check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    replies = {reply["id"]: reply for reply in map(json.loads, result.stdout.splitlines())}
    try:
        correct = (replies[1]["result"]["serverInfo"]["name"] == "CanvasGate Studio"
                   and replies[2]["result"]["tools"]
                   and json.loads(replies[3]["result"]["content"][0]["text"]).get("ready"))
    except (ValueError, TypeError, KeyError, IndexError):
        correct = False
    if result.returncode or not correct:
        raise WorkflowError("The bridge did not complete initialization, discovery and the status tool.")
    with connection.lock:
        connection.verified.add(provider)
    return {"verified": True}
