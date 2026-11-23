"""Immutable inputs, durable inference ledger and offline replay.

External calls are not magically exactly-once: a pending call after a process
crash is uncertain and requires reconciliation before it can be repeated.
"""

import base64
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

from .backends import WorkflowError
from .security import ensure_no_secrets, redact, relative_name
from .transactions import TransactionStore, atomic_bytes, digest


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _engine_code_hash():
    root = Path(__file__).parent
    names = ["engine.py", "canvasgate.py", "contracts.py", "markdown.py", "providers.py", "backends.py", "security.py", "snapshots.py", "transactions.py"]
    return fingerprint({"sources": {name: digest((root / name).read_bytes()) for name in names}, "runtime": RUNTIME})


RUNTIME = {"python": sys.version, "PyYAML": version("PyYAML"), "jsonschema": version("jsonschema")}
LOADED_ENGINE_SHA256 = _engine_code_hash()


def engine_fingerprint():
    return LOADED_ENGINE_SHA256


def backend_config(backend):
    result = {"backend": type(backend).__name__}
    for key in ("model", "timeout", "reasoning_effort", "max_output_tokens", "response"):
        if hasattr(backend, key):
            result[key] = getattr(backend, key)
    ensure_no_secrets(result)
    return result


def decision_signature(report):
    return {key: {"state": node["state"], "signal": node.get("signal"),
                  "text_sha256": digest(node.get("text", "").encode("utf-8")),
                  "input_sha256": node.get("decision", {}).get("input_sha256"),
                  "active_edges": node.get("decision", {}).get("active_edges", [])}
            for key, node in report["nodes"].items()}


class ReplayBackend:
    """Marker: the router must use the recorded ledger, never a provider."""

    def generate(self, *args):
        raise WorkflowError("Replay cannot call a live model.")


class RunSession:
    def __init__(self, vault, run_id):
        self.store = TransactionStore(vault)
        self.store.validate_id(run_id)
        self.id = run_id
        self.root = self.store.metadata_path("runs/" + run_id)
        self.parent = None
        self.replay = False
        self.last_effect = {}

    @staticmethod
    def read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkflowError("Snapshot record is missing or invalid.") from exc

    def save(self, path, value):
        ensure_no_secrets(value)
        atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

    @classmethod
    def load(cls, vault, run_id, *, verify_engine=True):
        session = cls(vault, run_id)
        session.manifest = session.read(session.root / "manifest.json")
        if session.manifest.get("format") != 1:
            raise WorkflowError("Unsupported snapshot format.")
        session.graph = session.read(session.root / "graph.json")
        if fingerprint(session.graph) != session.manifest["graph_sha256"]:
            raise WorkflowError("Snapshot graph hash mismatch.")
        if verify_engine and session.manifest["engine_sha256"] != engine_fingerprint():
            raise WorkflowError("The engine differs from this snapshot. Exact replay/resume is refused.")
        session.sources = {}
        for name, source in session.manifest["sources"].items():
            relative_name(name)
            sha = source.get("sha256", "")
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise WorkflowError("Invalid source hash in snapshot.")
            data = (session.root / "sources" / (sha + ".bin")).read_bytes()
            if digest(data) != sha:
                raise WorkflowError("Snapshot source hash mismatch.")
            session.sources[name] = data
        identity = {key: session.manifest[key] for key in ("graph_sha256", "engine_sha256", "sources", "configuration")}
        if fingerprint(identity) != session.manifest["snapshot_sha256"]:
            raise WorkflowError("Snapshot manifest hash mismatch.")
        for node_id, entry in session.manifest.get("nodes", {}).items():
            name = fingerprint(node_id) + ".json"
            if entry["file"] != name:
                raise WorkflowError("Invalid node checkpoint path.")
            checkpoint = session.read(session.root / "nodes" / name)
            if checkpoint.get("node_id") != node_id or fingerprint(checkpoint) != entry.get("record_sha256"):
                raise WorkflowError("Node checkpoint hash mismatch.")
        if session.manifest.get("report_sha256"):
            if fingerprint(session.read(session.root / "report.json")) != session.manifest["report_sha256"]:
                raise WorkflowError("Snapshot result hash mismatch.")
        return session

    @classmethod
    def create(cls, workflow, backend, run_id, config, *, parent=None):
        session = cls(workflow.vault, run_id)
        session.graph = workflow.raw
        ensure_no_secrets(session.graph)
        session.sources = {}
        source_records = {}
        total_bytes = 0
        for node in workflow.nodes.values():
            if node.kind != "FILE":
                continue
            name = node.config["file"]
            if name in session.sources:
                continue
            if workflow.source_snapshot is not None:
                if name not in workflow.source_snapshot:
                    raise WorkflowError("Source is missing from pinned snapshot.")
                data = workflow.source_snapshot[name]
            else:
                path = workflow.policy.path(name)
                if path.stat().st_size > 10 * 1024 * 1024:
                    raise WorkflowError("Snapshot source exceeds 10 MiB.")
                data = path.read_bytes()
            total_bytes += len(data)
            if total_bytes > 20 * 1024 * 1024:
                raise WorkflowError("Snapshot source budget exceeds 20 MiB.")
            ensure_no_secrets(data.decode("utf-8-sig"))
            session.sources[name] = data
            source_records[name] = {"sha256": digest(data), "bytes": len(data)}
        with session.store.lock():
            if session.root.exists():
                raise WorkflowError("Run already exists. Use replay or explicit resume; a new run ID is a new operation.")
            session.root.mkdir(parents=True)
            session.save(session.root / "graph.json", session.graph)
            for name, data in session.sources.items():
                atomic_bytes(session.root / "sources" / (source_records[name]["sha256"] + ".bin"), data)
            session.manifest = {"format": 1, "run_id": run_id, "state": "RUNNING", "graph_sha256": fingerprint(session.graph),
                "canvas_path": workflow.canvas.relative_to(workflow.vault).as_posix(),
                "graph_version": session.graph.get("canvasgate", {}).get("version", 1), "engine_sha256": engine_fingerprint(), "runtime": RUNTIME,
                "sources": source_records, "configuration": config, "nodes": {}, "effects": {},
                "started_at": datetime.now(timezone.utc).isoformat(), "replay_of": parent.id if parent else None}
            identity = {key: session.manifest[key] for key in ("graph_sha256", "engine_sha256", "sources", "configuration")}
            session.manifest["snapshot_sha256"] = fingerprint(identity)
            session.save(session.root / "manifest.json", session.manifest)
        session.parent, session.replay = parent, parent is not None
        return session

    def persist(self):
        self.save(self.root / "manifest.json", self.manifest)

    def effect_id(self, node_id, attempt):
        return fingerprint({"run_id": self.id, "node_id": node_id, "attempt": attempt})

    def effect_path(self, effect_id):
        if len(effect_id) != 64 or any(c not in "0123456789abcdef" for c in effect_id):
            raise WorkflowError("Invalid effect ID.")
        return self.root / "effects" / (effect_id + ".json")

    def execute(self, node_id, attempt, config, context, feedback, function):
        request = {"node_id": node_id, "attempt": attempt, "config": config, "context": context, "feedback": feedback}
        ensure_no_secrets(request)
        request_hash = fingerprint(request)
        reference = self.parent if self.replay else self
        effect_id = reference.effect_id(node_id, attempt)
        path = reference.effect_path(effect_id)
        effect = reference.read(path) if path.exists() else None
        self.last_effect = {"idempotency_key": effect_id, "replayed": False, "cached": False, "usage": None}
        if effect:
            if effect["request_sha256"] != request_hash:
                raise WorkflowError("Saved call input differs; refusing to reuse a response for another request.")
            if effect["state"] == "COMPLETED":
                if fingerprint(effect["response"]) != effect["response_sha256"]:
                    raise WorkflowError("Saved response hash mismatch.")
                self.last_effect.update({"cached": True, "replayed": self.replay, "original_usage": effect.get("usage")})
                return effect["response"]
            if self.replay and effect["state"] == "UNCERTAIN" and effect.get("error"):
                self.last_effect["replayed"] = True
                raise WorkflowError(effect["error"])
            if effect["state"] not in {"RETRY_AUTHORIZED"}:
                raise WorkflowError("Uncertain external outcome. Reconcile effect " + effect_id + " before resuming.")
        if self.replay:
            raise WorkflowError("Replay has no saved response; live inference is forbidden.")
        effect = {"idempotency_key": effect_id, "node_id": node_id, "attempt": attempt, "state": "PENDING",
                  "request_sha256": request_hash, "request": request, "started_at": datetime.now(timezone.utc).isoformat()}
        self.save(path, effect)
        self.manifest["effects"][effect_id] = {"state": "PENDING", "node_id": node_id, "attempt": attempt}
        self.persist()
        try:
            response = function()
            ensure_no_secrets(response)
            effect.update({"state": "COMPLETED", "response": response, "response_sha256": fingerprint(response)})
            self.save(path, effect)
            self.manifest["effects"][effect_id]["state"] = "COMPLETED"
            self.persist()
            return response
        except Exception as exc:
            effect.update({"state": "UNCERTAIN", "error": redact(str(exc))})
            self.save(path, effect)
            self.manifest["effects"][effect_id]["state"] = "UNCERTAIN"
            self.persist()
            raise

    def record_usage(self, usage):
        if self.last_effect.get("cached") or self.replay:
            return
        effect_id = self.last_effect.get("idempotency_key")
        if not effect_id:
            return
        path = self.effect_path(effect_id)
        effect = self.read(path)
        effect["usage"] = usage
        self.save(path, effect)

    def checkpoint(self, node_id, result, actual_inputs):
        ensure_no_secrets(result)
        ensure_no_secrets(actual_inputs)
        record = {"node_id": node_id, "inputs": actual_inputs, "result": result}
        name = fingerprint(node_id) + ".json"
        self.save(self.root / "nodes" / name, record)
        self.manifest["nodes"][node_id] = {"file": name, "state": result["state"], "result_sha256": fingerprint(result), "record_sha256": fingerprint(record)}
        self.persist()

    def finalize(self, report):
        if self.replay:
            original = self.parent.read(self.parent.root / "report.json")
            a, b = decision_signature(original), decision_signature(report)
            different = [key for key in set(a) | set(b) if a.get(key) != b.get(key)]
            report["replay_comparison"] = {"matches": not different, "different_nodes": sorted(different),
                                           "scope": "node decisions and payloads; writes are not replayed"}
        self.save(self.root / "report.json", report)
        self.manifest.update({"state": "COMPLETED" if report["outcome"] == "completed" else "FAILED",
                              "finished_at": datetime.now(timezone.utc).isoformat(), "report_sha256": fingerprint(report)})
        self.persist()

    def reconcile(self, effect_id, action, response=None):
        with self.store.lock("run-locks/" + self.manifest["run_id"] + ".lock"):
            self.manifest = self.read(self.root / "manifest.json")
            return self._reconcile_locked(effect_id, action, response)

    def _reconcile_locked(self, effect_id, action, response=None):
        path = self.effect_path(effect_id)
        with self.store.lock():
            effect = self.read(path)
            if effect["state"] not in {"PENDING", "UNCERTAIN"}:
                raise WorkflowError("Only uncertain or interrupted effects can be reconciled.")
            if action == "record_result":
                from .backends import validate_response
                validate_response(response)
                ensure_no_secrets(response)
                effect.update({"state": "COMPLETED", "response": response, "response_sha256": fingerprint(response), "usage": None})
            elif action == "authorize_retry":
                effect["state"] = "RETRY_AUTHORIZED"
            else:
                raise WorkflowError("Reconciliation requires record_result or authorize_retry.")
            effect["reconciliation"] = {"action": action, "at": datetime.now(timezone.utc).isoformat(), "actor": "explicit-user-action"}
            self.save(path, effect)
            self.manifest["effects"][effect_id]["state"] = effect["state"]
            self.persist()
        return {"idempotency_key": effect_id, "state": effect["state"]}


def claim_operation(vault, operation_key, request):
    """Bind a caller idempotency key to one run, rejecting changed requests."""
    store = TransactionStore(vault)
    if not isinstance(operation_key, str) or not 1 <= len(operation_key) <= 200:
        raise WorkflowError("An operation key of 1–200 characters is required.")
    key, request_hash = fingerprint(operation_key), fingerprint(request)
    path = store.metadata_path("operations/" + key + ".json")
    with store.lock("operations.lock"):
        if path.exists():
            saved = RunSession.read(path)
            if saved["request_sha256"] != request_hash:
                raise WorkflowError("Idempotency key already belongs to a different operation.")
            return saved["run_id"], True
        run_id = "op-" + key[:28]
        atomic_bytes(path, canonical({"run_id": run_id, "request_sha256": request_hash}))
        return run_id, False
