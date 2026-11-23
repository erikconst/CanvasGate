"""Local CanvasGate Studio: authenticated same-origin UI, editor and durable runs."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

from .backends import ApiBackend, CodexBackend, MockBackend, WorkflowError
from .canvasgate import CanvasGateWorkflow
from .markdown import frontmatter
from .observability import export_run_view
from .security import SecurityPolicy, ensure_no_secrets, redact, relative_name
from .snapshots import RunSession, backend_config, claim_operation, fingerprint
from .transactions import TransactionStore, atomic_bytes, digest


STATIC = Path(__file__).parent / "webui"
DOCS = Path(__file__).parent / "docs"
MOCK_RESULT = {"status": True, "confidence": 0.95, "text": json.dumps({
    "tasks": ["Validate container and field types without mutating input.", "Reject booleans for integer fields and duplicate SKUs.", "Calculate totals in integer cents only for valid orders."],
    "tests": ["Cover missing fields and wrong types.", "Check zero, minimum, maximum and oversized values.", "Verify duplicate SKUs, indexed errors and unchanged input."],
    "risks": ["Syntax and structure checks do not establish business correctness."]}, indent=2)}


def create_demo(vault):
    policy = SecurityPolicy(vault)
    note_path = policy.path("Studio/Specification.md", writing=True)
    if not note_path.exists():
        atomic_bytes(note_path, b"---\nrevision: 3\nrole: policy\nstatus: approved\n---\n# Order validation\n\n## Policy\n\nPOLICY_ID: order-v3\n\nValidate a pure Python order function. Do not mutate input.\nReject booleans as integers. Reject duplicate SKUs.\nUse integer cents, never floating point.\nEvery order has customer_id and 1-100 items. Each item has sku, quantity 1-50, and unit_price_cents 0-1000000.\nReturn valid, errors and total_cents. Invalid totals are null.\n\n## Background\nMarketing ideas and visual branding do not affect this policy.\n")
    path = policy.path("Studio/Order review.canvas", writing=True)
    if path.exists():
        return path.relative_to(vault).as_posix()
    required = {"path": "Studio/Specification.md", "sha256": digest(note_path.read_bytes()), "version": {"key": "revision", "equals": 3}, "role": "policy"}
    schema = {"type": "object", "required": ["tasks", "tests", "risks"], "properties": {
        "tasks": {"type": "array", "minItems": 2, "items": {"type": "string"}},
        "tests": {"type": "array", "minItems": 3, "items": {"type": "string"}},
        "risks": {"type": "array", "minItems": 1, "items": {"type": "string"}}}}
    contract = {"description": "Pinned policy and essential rules must reach the model.", "input": {"required_sources": [required],
        "allowed_sources": ["Studio/Specification.md"], "required_text": ["POLICY_ID: order-v3", "Reject booleans as integers", "Reject duplicate SKUs", "Use integer cents"]},
        "output": {"required_fields": ["tasks", "tests", "risks"], "schema": schema}}
    nodes = [{"id": "spec", "type": "file", "file": "Studio/Specification.md", "x": 30, "y": 160, "width": 220, "height": 130}]
    entries = [
        ("approved", "GATE: YAML_EQ:status=approved", 290, 160),
        ("policy", "SLICE: SECTION:Policy", 550, 45),
        ("plan", "AGENT:\n" + json.dumps({"prompt": "Write an English implementation plan from the supplied policy. Return JSON text with tasks, tests and risks arrays. Include at least 2 tasks, 3 tests, and 1 risk. Do not generate code.", "schema": "json", "max_retries": 1}), 810, 45),
        ("review", "AGENT:\n" + json.dumps({"prompt": "The policy is not approved. Return JSON text with tasks, tests and risks arrays describing review work. Include at least 2 tasks, 3 checks, 1 risk. Do not implement code.", "schema": "json", "max_retries": 1}), 550, 335),
        ("join", "JOIN: ANY", 1070, 160),
        ("write", "WRITE: OVERWRITE:Studio/Output/Plan.md", 1070, 390),
        ("out", "OUTPUT: Accepted implementation plan", 810, 390),
    ]
    for key, text, x, y in entries:
        nodes.append({"id": key, "type": "text", "text": text, "x": x, "y": y, "width": 220, "height": 130})
    routes = [("spec", "approved", ""), ("approved", "policy", "true"), ("policy", "plan", ""), ("approved", "review", "false"),
              ("plan", "join", ""), ("review", "join", ""), ("join", "write", ""), ("write", "out", "")]
    raw = {"nodes": nodes, "edges": [{"id": f"e{i}", "fromNode": a, "toNode": b, "label": label} for i, (a, b, label) in enumerate(routes)],
        "canvasgate": {"version": 3, "require_contracts": ["AGENT", "WRITE"],
            "permissions": {"read_dirs": ["Studio"], "write_dirs": ["Studio/Output"], "allow_cli": True},
            "contracts": {"plan": contract, "review": {"input": {"required_sources": [required], "allowed_sources": [required["path"]]}, "output": contract["output"]},
                          "write": {"input": {"required_fields": ["tasks", "tests", "risks"], "allowed_sources": [required["path"]]}}}}}
    atomic_bytes(path, json.dumps(raw, indent=2).encode("utf-8"))
    return path.relative_to(vault).as_posix()


class Studio:
    def __init__(self, vault, *, seed_demo=True):
        self.vault = Path(vault).resolve()
        if not self.vault.is_dir():
            raise WorkflowError("Vault directory does not exist.")
        self.policy = SecurityPolicy(self.vault)
        self.default_workflow = create_demo(self.vault) if seed_demo else next(iter(self.files({".canvas"})), None)
        self.store = TransactionStore(self.vault)
        self.jobs, self.guard = {}, threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="canvasgate")
        self.session_cookie, self.csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)

    def files(self, suffixes):
        found = []
        for root, folders, names in os.walk(self.vault, followlinks=False):
            folders[:] = [name for name in folders if not name.startswith(".") and name != "node_modules" and not (Path(root) / name).is_symlink()]
            for name in names:
                if Path(name).suffix.casefold() in suffixes:
                    relative = (Path(root) / name).relative_to(self.vault).as_posix()
                    if relative.startswith("Studio/Runs/") and Path(name).suffix.casefold() == ".canvas":
                        continue
                    try:
                        self.policy.path(relative)
                    except WorkflowError:
                        continue
                    found.append(relative)
                    if len(found) >= 2000:
                        return sorted(found)
        return sorted(found)

    def read_file(self, name, *, graph=False):
        path = self.policy.path(name)
        if path.suffix.casefold() not in ({".canvas"} if graph else {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".csv", ".toml"}):
            raise WorkflowError("Unsupported document type.")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise WorkflowError("Editor file limit is 2 MiB.")
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
        ensure_no_secrets(text)
        return {"path": name, "sha256": digest(data), "text": text, **({"graph": json.loads(text)} if graph else {})}

    def validate_graph(self, name, graph):
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
            raise WorkflowError("Graph needs nodes and edges arrays.")
        if len(graph["nodes"]) > 500 or len(graph["edges"]) > 2000:
            raise WorkflowError("Studio supports up to 500 nodes and 2,000 edges.")
        ensure_no_secrets(graph)
        for node in graph["nodes"]:
            for coordinate in ("x", "y", "width", "height"):
                value = node.get(coordinate, 220 if coordinate == "width" else (130 if coordinate == "height" else 0))
                if type(value) not in (int, float) or not -100000 <= value <= 100000:
                    raise WorkflowError("Invalid node geometry.")
        workflow = CanvasGateWorkflow(self.policy.path(name, writing=True), self.vault, raw=graph)
        return workflow

    def save_file(self, body, *, graph=False):
        name = relative_name(body["path"])
        path = self.policy.path(name, writing=True)
        if path.suffix.casefold() not in ({".canvas"} if graph else {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".csv", ".toml"}):
            raise WorkflowError("Unsupported editor file type.")
        if "expected_sha256" not in body:
            raise WorkflowError("Saving requires the expected file hash.")
        if graph:
            self.validate_graph(name, body["graph"])
            content = json.dumps(body["graph"], ensure_ascii=False, indent=2)
        else:
            content = body["text"]
            if not isinstance(content, str):
                raise WorkflowError("Source content must be text.")
        ensure_no_secrets(content)
        with self.store.lock():
            current = digest(path.read_bytes()) if path.exists() else None
            if current != body["expected_sha256"]:
                raise WorkflowError("File changed externally. Reload before saving; your draft was not overwritten.")
            atomic_bytes(path, content.encode("utf-8"))
        return self.read_file(name, graph=graph)

    def runs(self):
        root = self.store.metadata_path("runs")
        rows = []
        if not root.exists():
            return rows
        for directory in root.iterdir():
            if not directory.is_dir():
                continue
            try:
                manifest = RunSession.read(directory / "manifest.json")
                report = RunSession.read(directory / "report.json") if (directory / "report.json").exists() else {}
                rows.append({"run_id": directory.name, "state": manifest["state"], "workflow": manifest.get("canvas_path"),
                             "started_at": manifest.get("started_at"), "replay_of": manifest.get("replay_of"),
                             "snapshot_sha256": manifest.get("snapshot_sha256"), "usage": report.get("usage"),
                             "outcome": report.get("outcome"), "simulation": report.get("simulation"),
                             "transaction_state": report.get("transaction_state"), "external_calls": report.get("external_calls"),
                             "node_count": len(manifest.get("nodes", {})), "error": manifest.get("error")})
            except (WorkflowError, KeyError):
                continue
        return sorted(rows, key=lambda row: row["started_at"] or "", reverse=True)[:200]

    def run_detail(self, run_id):
        session = RunSession.load(self.vault, run_id, verify_engine=False)
        report = session.read(session.root / "report.json") if (session.root / "report.json").exists() else None
        effects = []
        for effect_id in session.manifest["effects"]:
            effect = session.read(session.effect_path(effect_id))
            effects.append({key: effect.get(key) for key in ("idempotency_key", "state", "node_id", "attempt", "error", "reconciliation")})
        return {"manifest": session.manifest, "graph": session.graph, "report": report, "effects": effects}

    def backend(self, config):
        kind = config.get("backend", "mock")
        model = config.get("model") or "gpt-6.1-sol"
        timeout = config.get("timeout", 180)
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise WorkflowError("Timeout must be 1–600 seconds.")
        if not isinstance(model, str) or not model or len(model) > 100:
            raise WorkflowError("Invalid model name.")
        if kind == "mock":
            return MockBackend(MOCK_RESULT)
        if kind == "codex":
            return CodexBackend(model, timeout, "medium")
        if kind == "api":
            if not os.environ.get("OPENAI_API_KEY"):
                raise WorkflowError("Configure OPENAI_API_KEY in the server environment. Keys are never entered in Studio.")
            return ApiBackend(model, timeout, 2000, reasoning_effort="medium")
        raise WorkflowError("Unknown backend.")

    def submit(self, body, mode="live", parent_id=None):
        operation_key = body.get("operation_key")
        backend = MockBackend(MOCK_RESULT) if mode == "replay" else self.backend(body)
        if mode == "live":
            name = body["path"]
            current = self.read_file(name, graph=True)
            if current["sha256"] != body.get("expected_sha256"):
                raise WorkflowError("Saved workflow differs from the editor. Save/reload before running.")
            workflow = self.validate_graph(name, current["graph"])
            if body.get("strict_isolation", True):
                SecurityPolicy(self.vault, workflow.settings.get("permissions"), strict_isolation=True).check_backend(backend)
            max_calls = body.get("max_calls", 3)
            if type(max_calls) is not int or not 0 <= max_calls <= 20:
                raise WorkflowError("Studio max_calls must be 0–20.")
            request = {"mode": mode, "path": name, "graph_sha256": fingerprint(workflow.raw), "backend": backend_config(backend),
                       "max_calls": max_calls, "commit": bool(body.get("commit", False)), "strict": bool(body.get("strict_isolation", True))}
        else:
            session = RunSession.load(self.vault, parent_id)
            workflow = CanvasGateWorkflow.from_snapshot(self.vault, parent_id)
            request = {"mode": mode, "parent_id": parent_id, "backend": backend_config(backend) if mode == "resume" else "recorded-responses"}
        with self.guard:
            job_id, reused = claim_operation(self.vault, operation_key, request)
            if job_id in self.jobs:
                return self.jobs[job_id]
            job_path = self.store.metadata_path("jobs/" + job_id + ".json")
            if reused and job_path.exists():
                saved = RunSession.read(job_path)
                if saved["state"] in {"COMPLETED", "FAILED"}:
                    return saved
            job = {"job_id": job_id, "run_id": parent_id if mode == "resume" else job_id, "state": "QUEUED", "mode": mode, "error": None}
            self.jobs[job_id] = job
            self._save_job(job)
            self.pool.submit(self._work, job, workflow, backend, body, parent_id)
            return copy.deepcopy(job)

    def _save_job(self, job):
        ensure_no_secrets(job)
        atomic_bytes(self.store.metadata_path("jobs/" + job["job_id"] + ".json"), json.dumps(job, indent=2).encode())

    def _work(self, job, workflow, backend, body, parent_id):
        job["state"] = "RUNNING"
        self._save_job(job)
        try:
            if job["mode"] == "replay":
                report = CanvasGateWorkflow.replay_run(self.vault, parent_id, new_run_id=job["run_id"])
            elif job["mode"] == "resume":
                report = CanvasGateWorkflow.resume_run(self.vault, parent_id, backend)
            else:
                root = self.store.metadata_path("runs/" + job["run_id"])
                if root.exists():
                    report = CanvasGateWorkflow.resume_run(self.vault, job["run_id"], backend)
                else:
                    report = workflow.run(backend, run_id=job["run_id"], commit=bool(body.get("commit", False)),
                        max_calls=body.get("max_calls", 3), strict_isolation=body.get("strict_isolation", True))
            try:
                directory = self.policy.path("Studio/Runs/" + report["run_id"], writing=True)
                view = export_run_view(workflow, report, directory)
                if report.get("audit_log"):
                    atomic_bytes(directory / "RunReport.md", Path(report["audit_log"]).read_bytes())
                job["inspection_canvas"] = Path(view).relative_to(self.vault).as_posix() if view else None
            except Exception as exc:
                job["export_warning"] = redact(str(exc))
            job.update({"state": "COMPLETED", "outcome": report["outcome"], "transaction_state": report["transaction_state"],
                        "usage": report["usage"], "external_calls": report.get("external_calls", 0)})
        except Exception as exc:
            job.update({"state": "FAILED", "error": redact(str(exc))})
        self._save_job(job)

    def job(self, job_id):
        self.store.validate_id(job_id)
        job = copy.deepcopy(self.jobs.get(job_id))
        if job is None:
            job = RunSession.read(self.store.metadata_path("jobs/" + job_id + ".json"))
        path = self.store.metadata_path("runs/" + job["run_id"] + "/manifest.json")
        if path.exists():
            try:
                manifest = RunSession.read(path)
                job["nodes"] = manifest.get("nodes", {})
            except WorkflowError:
                if job["state"] not in {"QUEUED", "RUNNING"}:
                    raise
        return job

    def pin_sources(self, body):
        graph = copy.deepcopy(body["graph"])
        workflow = self.validate_graph(body["path"], graph)
        updates = []
        for contract in graph.get("canvasgate", {}).get("contracts", {}).values():
            for direction in ("input", "output"):
                for source in contract.get(direction, {}).get("required_sources", []):
                    path = workflow.policy.path(source["path"])
                    data = path.read_bytes()
                    ensure_no_secrets(data.decode("utf-8-sig"))
                    source["sha256"] = digest(data)
                    updates.append(source["path"])
        return {"graph": graph, "pinned_sources": sorted(set(updates))}


class Handler(BaseHTTPRequestHandler):
    server_version = "CanvasGate/0.3"

    @property
    def studio(self):
        return self.server.studio

    def log_message(self, *args):
        pass

    def allowed_origin(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in allowed:
            raise WorkflowError("Untrusted Host header.")
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + name for name in allowed}:
            raise WorkflowError("Cross-origin requests are forbidden.")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise WorkflowError("Cross-site requests are forbidden.")

    def authenticated(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        return "canvasgate_session" in cookie and secrets.compare_digest(cookie["canvasgate_session"].value, self.studio.session_cookie)

    def respond(self, value, status=200, *, content_type="application/json", cookie=False, headers=None):
        data = value if isinstance(value, bytes) else json.dumps(redact(value), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        if cookie:
            self.send_header("Set-Cookie", f"canvasgate_session={self.studio.session_cookie}; HttpOnly; SameSite=Strict; Path=/")
        for key, item in (headers or {}).items():
            self.send_header(key, item)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self.allowed_origin()
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/mcp" and self.server.agents:
                if not self.mcp_authorized():
                    return self.respond({"error": "Unauthorized MCP client."}, 401)
                return self.respond(b"", 405, headers={"Allow": "POST, DELETE"})
            if url.path.startswith("/api/"):
                if not self.authenticated():
                    return self.respond({"error": "Open Studio to establish a local session."}, 401)
                if url.path == "/api/bootstrap":
                    return self.respond({"csrf": self.studio.csrf, "vault": str(self.studio.vault), "default_workflow": self.studio.default_workflow,
                        "desktop": self.server.agents is not None,
                        "workflows": self.studio.files({".canvas"}), "sources": self.studio.files({".md", ".json", ".txt", ".yaml", ".yml", ".py"}),
                        "runs": self.studio.runs(), "api_configured": bool(os.environ.get("OPENAI_API_KEY")), "cli_installed": bool(shutil.which("codex.exe") or shutil.which("codex"))})
                if url.path == "/api/agents" and self.server.agents:
                    return self.respond(self.server.agents.status())
                if url.path == "/api/guides":
                    return self.respond({name: (DOCS / name).read_text(encoding="utf-8") for name in
                                         ("USER_GUIDE.md", "HOW_IT_WORKS.md")})
                if url.path == "/api/agents/guide" and self.server.agents:
                    from .agent_bridge import GUIDE, GUIDE_URI
                    user_guide = Path(__file__).with_name("MCP_USER_GUIDE.md").read_text(encoding="utf-8")
                    return self.respond({"agent": GUIDE, "user": user_guide, "resource": GUIDE_URI})
                if url.path == "/api/workflow":
                    return self.respond(self.studio.read_file(query["path"][0], graph=True))
                if url.path == "/api/source":
                    return self.respond(self.studio.read_file(query["path"][0]))
                if url.path == "/api/runs":
                    return self.respond(self.studio.runs())
                if url.path.startswith("/api/jobs/"):
                    return self.respond(self.studio.job(url.path.split("/")[3]))
                if url.path.startswith("/api/runs/"):
                    run_id = url.path.split("/")[3]
                    if url.path.endswith("/bundle"):
                        session = RunSession.load(self.studio.vault, run_id, verify_engine=False)
                        return self.respond({"format": "canvasgate-snapshot-1", "manifest": session.manifest, "graph": session.graph,
                            "sources": {name: {"sha256": digest(data), "base64": base64.b64encode(data).decode()} for name, data in session.sources.items()},
                            "nodes": {key: session.read(session.root / "nodes" / value["file"]) for key, value in session.manifest["nodes"].items()},
                            "effects": {key: session.read(session.effect_path(key)) for key in session.manifest["effects"]},
                            "report": session.read(session.root / "report.json") if (session.root / "report.json").exists() else None})
                    if url.path.endswith("/node"):
                        session = RunSession.load(self.studio.vault, run_id, verify_engine=False)
                        key = query["id"][0]
                        return self.respond(session.read(session.root / "nodes" / (fingerprint(key) + ".json")))
                    return self.respond(self.studio.run_detail(run_id))
                return self.respond({"error": "API route not found."}, 404)
            name = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                    "/workbench.css": "workbench.css", "/agents.js": "agents.js",
                    "/guides.js": "guides.js"}.get(url.path)
            if not name:
                return self.respond({"error": "Not found."}, 404)
            content_type = "text/html" if name.endswith("html") else ("text/javascript" if name.endswith("js") else "text/css")
            self.respond((STATIC / name).read_bytes(), content_type=content_type, cookie=name == "index.html")
        except Exception as exc:
            self.respond({"error": redact(str(exc))}, 400)

    def do_POST(self):
        try:
            self.connection.settimeout(10)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2 * 1024 * 1024:
                raise WorkflowError("Request size must be 1 byte–2 MiB.")
            payload = self.rfile.read(length)
            self.allowed_origin()
            path = urlparse(self.path).path
            if path == "/mcp" and self.server.agents:
                return self.mcp_post(payload)
            if not self.authenticated() or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), self.studio.csrf):
                return self.respond({"error": "A valid local session and CSRF token are required."}, 403)
            if not self.headers.get("Origin"):
                raise WorkflowError("Mutation requests require the same-origin Origin header.")
            if self.headers.get_content_type() != "application/json":
                raise WorkflowError("JSON request required.")
            body = json.loads(payload)
            if not isinstance(body, dict):
                raise WorkflowError("JSON object required.")
            ensure_no_secrets(body)
            if path == "/api/agents/verify" and self.server.agents:
                from .agent_bridge import PROVIDERS, verify_bridge
                provider = body.get("provider")
                if provider not in PROVIDERS:
                    raise WorkflowError("Unknown agent.")
                return self.respond(verify_bridge(self.server.agents, provider))
            if path == "/api/workflow/save":
                return self.respond(self.studio.save_file(body, graph=True))
            if path == "/api/source/save":
                return self.respond(self.studio.save_file(body))
            if path == "/api/validate":
                workflow = self.studio.validate_graph(body["path"], body["graph"])
                return self.respond({"valid": True, "plan": workflow.plan(), "graph_sha256": fingerprint(workflow.raw),
                                     "contract_count": len(workflow.contracts), "permissions": workflow.policy.public()})
            if path == "/api/contracts/pin":
                return self.respond(self.studio.pin_sources(body))
            if path == "/api/runs":
                return self.respond(self.studio.submit(body), 202)
            if path.startswith("/api/runs/"):
                parts = path.split("/")
                run_id, action = parts[3], parts[4]
                if action in {"replay", "resume"}:
                    return self.respond(self.studio.submit(body, action, run_id), 202)
                if action == "reconcile":
                    session = RunSession.load(self.studio.vault, run_id)
                    return self.respond(session.reconcile(body["effect_id"], body["action"], body.get("response")))
                if action == "recover":
                    return self.respond(TransactionStore(self.studio.vault).recover(run_id))
            self.respond({"error": "API route not found."}, 404)
        except Exception as exc:
            self.respond({"error": redact(str(exc))}, 400)

    def mcp_authorized(self):
        return not self.headers.get("Origin") and secrets.compare_digest(
            self.headers.get("Authorization", "").encode(), ("Bearer " + self.server.agents.token).encode())

    def mcp_post(self, payload):
        from .agent_bridge import PROTOCOLS, PROVIDERS

        if not self.mcp_authorized():
            return self.respond({"error": "Unauthorized MCP client."}, 401,
                                headers={"WWW-Authenticate": "Bearer"})
        if len(payload) > 32768 or self.headers.get_content_type() != "application/json":
            return self.respond({"error": "MCP requires a JSON request up to 32 KiB."}, 400)
        version = self.headers.get("MCP-Protocol-Version")
        if version and version not in PROTOCOLS:
            return self.respond({"error": "Unsupported MCP protocol version."}, 400)
        provider = self.headers.get("X-CanvasGate-Client")
        session, result = self.server.agents.request(self.studio, json.loads(payload),
            self.headers.get("Mcp-Session-Id"), provider if provider in PROVIDERS else None)
        if not session:
            return self.respond({"error": "MCP session expired or missing. Initialize again."}, 404)
        if result is None:
            return self.respond(b"", 202)
        return self.respond(result, headers={"Mcp-Session-Id": session})

    def do_DELETE(self):
        try:
            self.allowed_origin()
            if urlparse(self.path).path != "/mcp" or not self.server.agents:
                return self.respond({"error": "Route not found."}, 404)
            if not self.mcp_authorized():
                return self.respond({"error": "Unauthorized MCP client."}, 401)
            found = self.server.agents.detach(self.headers.get("Mcp-Session-Id"))
            self.respond(b"", 204 if found else 404)
        except Exception as exc:
            self.respond({"error": redact(str(exc))}, 400)


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, vault, *, agents=None, seed_demo=True):
        self.studio = Studio(vault, seed_demo=seed_demo)
        self.agents = agents
        super().__init__(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=Path(__file__).resolve().parents[1] / "examples/vault")
    parser.add_argument("--port", type=int, default=8874)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = StudioServer(("127.0.0.1", args.port), args.vault)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"CanvasGate Studio: {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.studio.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
