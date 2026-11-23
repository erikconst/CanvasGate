"""CanvasGate DAG execution with typed signals separate from routed payloads."""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ast
import copy
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from .backends import MockBackend, WorkflowError, validate_response
from .engine import RULES, check_rules, integer, options, rule_errors
from .markdown import frontmatter, lookup, render, section, yaml_value
from .providers import BackendRouter, sum_usage
from .contracts import check_contract, validate_contract
from .security import SecurityPolicy, ensure_no_secrets, redact
from .snapshots import ReplayBackend, RunSession, backend_config, claim_operation, fingerprint
from .transactions import StagingBuffer, TransactionStore, atomic_bytes, confined_path, digest


TRUE = {"true", "1", "yes", "da", "pass"}
FALSE = {"false", "0", "no", "nu", "fail"}
GATES = {"AND", "OR", "NOT", "REGEX", "YAML_EQ", "LEN_LT", "JSON_KEYS", "WORDS", "CONFIDENCE"}


@dataclass
class Edge:
    id: str
    source: str
    target: str
    label: str = ""


@dataclass
class Node:
    id: str
    kind: str
    config: dict = field(default_factory=dict)
    incoming: list = field(default_factory=list)
    outgoing: list = field(default_factory=list)


@dataclass
class Value:
    state: str = "EXECUTED"
    signal: object = True
    text: str = ""
    confidence: float = 1.0
    context: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    reason: str = ""
    attempts: int = 0
    duration_ms: float = 0.0
    tokens_used: object = 0
    input_preview: str = ""
    lineage: dict = field(default_factory=dict)
    decision: dict = field(default_factory=dict)

    def public(self):
        return {"state": self.state, "status": self.signal if type(self.signal) is bool else True,
                "signal": self.signal, "confidence": self.confidence, "text": self.text,
                "reason": self.reason, "attempts": self.attempts, "duration_ms": self.duration_ms,
                "tokens_used": self.tokens_used, "input_preview": self.input_preview,
                "lineage": self.lineage, "decision": self.decision}


def edge_open(label, signal):
    if not label:
        return True
    if label.casefold() in TRUE:
        return signal is True
    if label.casefold() in FALSE:
        return signal is False
    return type(signal) is str and signal == label


def emit(node_id, text, *, signal=True, confidence=1.0, metadata=None):
    return Value(signal=signal, text=text, confidence=confidence, metadata=metadata or {},
                 context={node_id: {"status": signal if type(signal) is bool else True, "confidence": confidence, "text": text}})


def merge(inputs):
    context, lineage = {}, {}
    for value in inputs:
        context.update(value.context)
        for name, source in value.lineage.items():
            if name in lineage and lineage[name]["sha256"] != source["sha256"]:
                raise WorkflowError("Conflicting source versions reached the same node.")
            if name not in lineage:
                lineage[name] = copy.deepcopy(source)
            else:
                existing = lineage[name].setdefault("selections", [])
                for selection in source.get("selections", []):
                    if selection not in existing:
                        existing.append(copy.deepcopy(selection))
    text = "\n\n".join(part["text"] for part in context.values())
    return Value(text=text, context=context, confidence=min((v.confidence for v in inputs), default=1.0),
                 metadata=inputs[0].metadata if len(inputs) == 1 else {}, lineage=lineage)


class CanvasGateWorkflow:
    def __init__(self, canvas, vault=None, *, raw=None, source_snapshot=None):
        self.canvas = Path(canvas).resolve()
        self.vault = Path(vault).resolve() if vault else self.canvas.parent
        if not self.canvas.is_relative_to(self.vault):
            raise WorkflowError("Canvas must be inside the vault.")
        if raw is None:
            try:
                raw = json.loads(self.canvas.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                raise WorkflowError(f"Cannot read Canvas: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
            raise WorkflowError("Canvas requires nodes and edges arrays.")
        if raw.get("canvasgate_inspection_only"):
            raise WorkflowError("This is an inspection-only Canvas, not an executable workflow.")
        self.raw, self.source_snapshot = copy.deepcopy(raw), source_snapshot
        self.settings = raw.get("canvasgate", {})
        if not isinstance(self.settings, dict) or set(self.settings) - {"version", "contracts", "permissions", "require_contracts"}:
            raise WorkflowError("Unknown canvasgate graph setting.")
        self.policy = SecurityPolicy(self.vault, self.settings.get("permissions"))
        self.contracts = self.settings.get("contracts", {})
        if not isinstance(self.contracts, dict):
            raise WorkflowError("Graph contracts must map node IDs to contracts.")
        self.nodes, ids = {}, set()
        for item in raw["nodes"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
                raise WorkflowError("Missing or duplicate node ID.")
            ids.add(item["id"])
            if item.get("type") == "group":
                continue
            self.nodes[item["id"]] = self.parse(item)
        self.edges, ids, connections = [], set(), set()
        for item in raw["edges"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
                raise WorkflowError("Missing or duplicate edge ID.")
            ids.add(item["id"])
            source, target, label = item.get("fromNode"), item.get("toNode"), item.get("label", "")
            if not isinstance(source, str) or not isinstance(target, str) or source not in self.nodes or target not in self.nodes:
                raise WorkflowError("Edge references an unknown node or a visual group.")
            if label is None:
                label = ""
            if not isinstance(label, str):
                raise WorkflowError("Edge label must be text.")
            edge = Edge(item["id"], source, target, label.strip())
            identity = (source, target, edge.label)
            if identity in connections:
                raise WorkflowError("Duplicate connection and label.")
            connections.add(identity)
            self.edges.append(edge)
            self.nodes[source].outgoing.append(edge)
            self.nodes[target].incoming.append(edge)
        if not any(n.kind in {"WRITE", "OUTPUT"} for n in self.nodes.values()):
            raise WorkflowError("CanvasGate requires a WRITE or OUTPUT node.")
        sources = {"FILE", "INPUT", "TEXT", "DATA"}
        unary = {"SLICE", "NOT", "REGEX", "YAML_EQ", "LEN_LT", "JSON_KEYS", "WORDS", "CONFIDENCE"}
        for node in self.nodes.values():
            if (node.kind in sources) != (not node.incoming):
                raise WorkflowError(f"Source nodes have no inputs; processing nodes require inputs: {node.id}")
            if node.kind in unary and len(node.incoming) != 1:
                raise WorkflowError(f"{node.kind} requires exactly one incoming edge.")
        required_contracts = self.settings.get("require_contracts", [])
        if not isinstance(required_contracts, list) or any(not isinstance(kind, str) for kind in required_contracts):
            raise WorkflowError("require_contracts must be a list of node kinds.")
        if set(self.contracts) - set(self.nodes):
            raise WorkflowError("Contract references an unknown node ID.")
        for key, contract in self.contracts.items():
            validate_contract(contract)
        for node in self.nodes.values():
            if node.kind in required_contracts and node.id not in self.contracts:
                raise WorkflowError(f"Explicit contract required for {node.id}.")
        remaining = {key: len(node.incoming) for key, node in self.nodes.items()}
        queue = deque(key for key, degree in remaining.items() if degree == 0)
        self.order = []
        while queue:
            key = queue.popleft()
            self.order.append(key)
            for edge in self.nodes[key].outgoing:
                remaining[edge.target] -= 1
                if remaining[edge.target] == 0:
                    queue.append(edge.target)
        if len(self.order) != len(self.nodes):
            raise WorkflowError("Cycle detected before execution; use agent max_retries instead of feedback edges.")

    def parse(self, item):
        key = item["id"]
        if item.get("type") == "file":
            name = item.get("file")
            path = self.policy.path(name, pinned=self.source_snapshot is not None)
            if self.source_snapshot is not None and name not in self.source_snapshot:
                raise WorkflowError("File is absent from the pinned source snapshot.")
            if self.source_snapshot is None and not path.is_file():
                raise WorkflowError(f"Source file not found: {name}")
            subpath = item.get("subpath", "")
            if not isinstance(subpath, str) or (subpath and not subpath.startswith("#")):
                raise WorkflowError("File subpath must be a Markdown heading starting with #.")
            return Node(key, "FILE", {"file": name, "section": subpath[1:]})
        if item.get("type") != "text" or not isinstance(item.get("text"), str):
            raise WorkflowError("Only text, file and visual group nodes are supported.")
        text = item["text"]
        header, _, body = text.partition("\n")
        prefix, colon, inline = header.strip().partition(":")
        prefix, inline = prefix.upper(), inline.strip()
        if not colon:
            return Node(key, "TEXT", {"text": text})
        content = (inline + "\n" + body).strip()
        if prefix == "TEXT":
            return Node(key, "TEXT", {"text": content})
        if prefix == "INPUT":
            try:
                value = json.loads(content, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
            except ValueError as exc:
                if content.startswith(("{", "[", '"')) or content in {"NaN", "Infinity", "-Infinity"}:
                    raise WorkflowError("Malformed INPUT JSON.") from exc
                value = content
            return Node(key, "INPUT", {"value": value})
        if prefix == "DATA":
            data = options(content, {"status", "confidence", "text"})
            validate_response(data)
            return Node(key, "DATA", data)
        if prefix in {"JOIN", "MERGE"}:
            mode = content.upper() or "ANY"
            if mode not in {"ANY", "ALL"}:
                raise WorkflowError("JOIN/MERGE accepts ANY or ALL.")
            return Node(key, "JOIN", {"mode": mode})
        if prefix == "SLICE":
            mode, delimiter, argument = content.partition(":")
            mode, argument = mode.strip().upper(), argument.strip()
            if not delimiter or mode not in {"SECTION", "YAML", "LINES"} or not argument:
                raise WorkflowError("SLICE requires SECTION:title, YAML:key, or LINES:start-end.")
            config = {"mode": mode, "argument": argument}
            if mode == "LINES":
                match = re.fullmatch(r"([1-9]\d*)-([1-9]\d*)", argument)
                if not match or int(match[1]) > int(match[2]):
                    raise WorkflowError("LINES uses a positive, inclusive start-end interval.")
                config["start"], config["end"] = int(match[1]), int(match[2])
            return Node(key, "SLICE", config)
        if prefix == "GATE":
            operator, separator, argument = inline.partition(":")
            operator = operator.strip().upper()
            if operator not in GATES:
                raise WorkflowError(f"Unknown gate: {operator}")
            if separator:
                if body.strip():
                    raise WorkflowError("Inline gates cannot also have a JSON body.")
                argument = argument.strip()
                if operator == "REGEX":
                    config = {"pattern": argument}
                elif operator == "YAML_EQ":
                    name, equal, expected = argument.partition("=")
                    if not equal or not name.strip():
                        raise WorkflowError("YAML_EQ requires key=value.")
                    config = {"key": name.strip(), "expected": yaml_value(expected)}
                elif operator == "LEN_LT":
                    if not argument.isdigit():
                        raise WorkflowError("LEN_LT requires a non-negative integer character limit.")
                    config = {"limit": integer(int(argument), "LEN_LT")}
                elif operator == "JSON_KEYS":
                    keys = [name.strip() for name in argument.split(",")]
                    if not all(keys) or len(set(keys)) != len(keys):
                        raise WorkflowError("JSON_KEYS requires unique, non-empty key names.")
                    config = {"keys": keys}
                else:
                    raise WorkflowError(f"Inline arguments are not supported for {operator}.")
            else:
                allowed = {"REGEX": {"pattern"}, "WORDS": {"min_words", "max_words"}, "CONFIDENCE": {"min_confidence"}}.get(operator, set())
                if operator in {"YAML_EQ", "LEN_LT", "JSON_KEYS"}:
                    raise WorkflowError(f"{operator} requires inline arguments.")
                config = options(body, allowed)
                if operator == "REGEX" and "pattern" not in config:
                    raise WorkflowError("REGEX requires pattern.")
                if operator == "CONFIDENCE" and "min_confidence" not in config:
                    raise WorkflowError("CONFIDENCE requires min_confidence.")
            check_rules(config)
            return Node(key, operator, config)
        if prefix in {"CODEX", "AGENT"}:
            if not inline and body.lstrip().startswith("{"):
                config = options(body, RULES | {"prompt", "max_retries", "model", "max_tokens", "schema"})
            else:
                config, prompt = {}, content
                while prompt.startswith("["):
                    match = re.match(r"\[([a-z_]+)=([^\]\n]+)\]\s*", prompt)
                    if not match or match[1] not in {"model", "max_tokens", "schema", "max_retries"} or match[1] in config:
                        raise WorkflowError("Invalid or duplicate AGENT option.")
                    value = match[2].strip()
                    if match[1] in {"max_tokens", "max_retries"}:
                        if not value.isdigit():
                            raise WorkflowError("AGENT token and retry options must be integers.")
                        value = int(value)
                    config[match[1]] = value
                    prompt = prompt[match.end():]
                config["prompt"] = prompt.strip()
            if not isinstance(config.get("prompt"), str) or not config["prompt"].strip():
                raise WorkflowError("AGENT requires a non-empty prompt.")
            integer(config.get("max_retries", 0), "max_retries", maximum=10)
            if "max_tokens" in config:
                integer(config["max_tokens"], "max_tokens", minimum=1)
            if "model" in config and (not isinstance(config["model"], str) or not config["model"].strip()):
                raise WorkflowError("AGENT model must be a non-empty string.")
            if config.get("schema", "result") not in {"result", "json", "code_only"}:
                raise WorkflowError("Named schemas: result, json, code_only (Python syntax).")
            check_rules(config)
            return Node(key, "AGENT", config)
        if prefix == "WRITE":
            mode, delimiter, name = content.partition(":")
            mode, name = mode.strip().upper(), name.strip()
            if not delimiter or mode not in {"APPEND", "OVERWRITE"}:
                raise WorkflowError("WRITE requires APPEND:path or OVERWRITE:path.")
            confined_path(self.vault, name, writing=True)
            self.policy.path(name, writing=True)
            return Node(key, "WRITE", {"mode": mode, "path": name})
        if prefix == "OUTPUT":
            return Node(key, "OUTPUT", {"name": content or key})
        if prefix == "ABORT":
            return Node(key, "ABORT", {"reason": content or "Explicit workflow abort."})
        raise WorkflowError(f"Unknown CanvasGate node prefix: {prefix}")

    def plan(self):
        return [{"id": key, "kind": self.nodes[key].kind,
                 "parents": [e.source for e in self.nodes[key].incoming],
                 "routes": [{"to": e.target, "label": e.label} for e in self.nodes[key].outgoing]} for key in self.order]

    def gate(self, node, inputs, payload):
        kind, config = node.kind, node.config
        signals = [value.signal for value in inputs]
        if kind in {"AND", "OR", "NOT"}:
            if any(type(signal) is not bool for signal in signals):
                raise WorkflowError("Logical gates require boolean signals. Use INPUT: true/false or a predicate gate.")
            if kind == "AND":
                return len(inputs) == len(node.incoming) and all(signals)
            return any(signals) if kind == "OR" else not signals[0]
        if kind == "YAML_EQ":
            try:
                actual = lookup(payload.metadata, config["key"])
            except WorkflowError:
                return False
            return type(actual) is type(config["expected"]) and actual == config["expected"]
        if kind == "LEN_LT":
            return len(payload.text) < config["limit"]
        if kind == "JSON_KEYS":
            try:
                value = json.loads(payload.text)
                return isinstance(value, dict) and all(name in value for name in config["keys"])
            except ValueError:
                return False
        return not rule_errors({"text": payload.text, "confidence": payload.confidence}, config)

    @classmethod
    def from_snapshot(cls, vault, run_id):
        saved = RunSession.load(vault, run_id)
        return cls(Path(vault) / saved.manifest["canvas_path"], vault, raw=saved.graph, source_snapshot=saved.sources)

    @classmethod
    def replay_run(cls, vault, run_id, *, new_run_id=None):
        original = RunSession.load(vault, run_id)
        if not (original.root / "report.json").exists():
            raise WorkflowError("Incomplete run has no final decision trace to replay; use explicit resume/reconciliation.")
        workflow = cls.from_snapshot(vault, run_id)
        config = original.manifest["configuration"]
        return workflow.run(ReplayBackend(), run_id=new_run_id, commit=False,
                            max_calls=config["max_calls"], max_context_chars=config["max_context_chars"], replay_of=original)

    @classmethod
    def resume_run(cls, vault, run_id, backend):
        workflow = cls.from_snapshot(vault, run_id)
        config = RunSession.load(vault, run_id).manifest["configuration"]
        return workflow.run(backend, run_id=run_id, resume=True, commit=config["commit_requested"],
                            max_calls=config["max_calls"], max_context_chars=config["max_context_chars"],
                            strict_isolation=config["permissions"]["require_process_isolation"])

    def run(self, backend, *, max_calls=3, max_context_chars=16000, run_id=None, commit=True,
            resume=False, replay_of=None, operation_key=None, strict_isolation=False):
        integer(max_calls, "max_calls", maximum=100)
        integer(max_context_chars, "max_context_chars", minimum=1)
        self.policy = SecurityPolicy(self.vault, self.settings.get("permissions"), strict_isolation=strict_isolation)
        if not replay_of:
            self.policy.check_backend(backend)
        configuration = {"backend": backend_config(backend), "max_calls": max_calls,
                         "max_context_chars": max_context_chars, "commit_requested": commit,
                         "permissions": self.policy.public()}
        if operation_key:
            run_id, reused = claim_operation(self.vault, operation_key, {"graph": self.raw, "configuration": configuration})
            resume = resume or reused
        run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
        if resume:
            session = RunSession.load(self.vault, run_id)
            if fingerprint(self.raw) != session.manifest["graph_sha256"] or configuration != session.manifest["configuration"]:
                raise WorkflowError("Resume requires the pinned graph and original model/run configuration.")
        else:
            if replay_of:
                configuration = replay_of.manifest["configuration"]
            session = RunSession.create(self, backend, run_id, configuration, parent=replay_of)
        with session.store.lock("run-locks/" + run_id + ".lock"):
            if resume and session.manifest["state"] == "COMPLETED":
                report = session.read(session.root / "report.json")
                report["resume"] = {"already_completed": True, "external_calls_this_resume": 0, "writes_reapplied": False}
                return report
            try:
                session.manifest["state"] = "RUNNING"
                session.persist()
                report = self._execute(backend, max_calls=max_calls, max_context_chars=max_context_chars,
                                       run_id=run_id, commit=commit, session=session, resume=resume)
                report["snapshot"] = {"sha256": session.manifest["snapshot_sha256"], "path": str(session.root),
                                      "graph_sha256": session.manifest["graph_sha256"], "mode": "replay" if replay_of else ("resume" if resume else "live"),
                                      "replay_of": replay_of.id if replay_of else None}
                session.finalize(report)
                return report
            except Exception as exc:
                session.manifest.update({"state": "FAILED", "error": redact(str(exc))})
                session.persist()
                raise

    def _execute(self, backend, *, max_calls, max_context_chars, run_id, commit, session, resume=False):
        integer(max_calls, "max_calls", maximum=100)
        integer(max_context_chars, "max_context_chars", minimum=1)
        run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
        store = TransactionStore(self.vault)
        store.validate_id(run_id)
        log = store.metadata_path("logs/" + run_id)
        if not resume and (log.with_suffix(".json").exists() or store.metadata_path("transactions/" + run_id).exists()):
            raise WorkflowError("Run ID already has an audit log; refusing to repeat an append or overwrite it.")
        if any(node.kind == "WRITE" for node in self.nodes.values()):
            store.ensure_ready()
        router = BackendRouter(backend, session, self.policy)
        for node in self.nodes.values():
            if node.kind == "AGENT":
                selected = router.select(node.config)
                self.policy.check_backend(selected)
        staging, values, outputs, sources = StagingBuffer(self.vault), {}, {}, {}
        aborted, abort_reason, written = False, "", []
        for key in self.order:
            node = self.nodes[key]
            if aborted:
                values[key] = Value(state="SKIPPED", signal=False, reason="Run aborted before this node.")
                values[key].decision = {"why": "An earlier node failed; this node was not executed.", "active_edges": [], "input_sha256": fingerprint({})}
                session.checkpoint(key, values[key].public(), {})
                continue
            open_edges = [e for e in node.incoming if values[e.source].state == "EXECUTED" and edge_open(e.label, values[e.source].signal)]
            active = [values[e.source] for e in open_edges]
            if node.incoming and (not active or (node.kind == "JOIN" and node.config["mode"] == "ALL" and len(active) != len(node.incoming))):
                values[key] = Value(state="SKIPPED", signal=False, reason="Inactive incoming branch.")
                values[key].decision = {"why": "No active incoming branch, or JOIN ALL has an inactive dependency.", "active_edges": [e.id for e in open_edges], "input_sha256": fingerprint({})}
                session.checkpoint(key, values[key].public(), {})
                continue
            payload = merge(active)
            actual_inputs = {"context": payload.context, "sources": payload.lineage, "active_edges": [e.id for e in open_edges]}
            decision = {"kind": node.kind, "why": "All active dependencies resolved.", "active_edges": [e.id for e in open_edges],
                        "inactive_edges": [{"id": e.id, "source": e.source, "label": e.label, "source_state": values[e.source].state,
                                            "source_signal": values[e.source].signal} for e in node.incoming if e not in open_edges],
                        "input_sha256": fingerprint(actual_inputs), "input_sources": copy.deepcopy(payload.lineage), "retry_history": []}
            started, first_call = time.perf_counter(), len(router.calls)
            result = payload
            try:
                decision["input_contract"] = check_contract(self.contracts.get(key, {}).get("input", {}), payload)
                if node.kind == "FILE":
                    path = self.policy.path(node.config["file"], pinned=True)
                    raw_source = session.sources[node.config["file"]]
                    source = {"path": node.config["file"], "resolved": str(path), "sha256": digest(raw_source)}
                    if str(path) in sources and sources[str(path)]["sha256"] != source["sha256"]:
                        raise WorkflowError("Source file changed between reads in the same run.")
                    sources[str(path)] = source
                    text = raw_source.decode("utf-8-sig")
                    metadata, _ = frontmatter(text) if path.suffix.lower() == ".md" else ({}, text)
                    if node.config["section"]:
                        text = section(text, node.config["section"])
                        metadata = {}
                    result = emit(key, text, metadata=metadata)
                    result.lineage = {node.config["file"]: {"sha256": digest(raw_source), "metadata": metadata,
                                       "selections": [{"node_id": key, "kind": "FILE", "fragment_sha256": digest(text.encode())}]}}
                    decision["why"] = "Loaded the immutable source bytes recorded in this run's snapshot."
                elif node.kind == "INPUT":
                    value = node.config["value"]
                    signal = value if type(value) in (bool, str) else True
                    result = emit(key, render(value), signal=signal)
                elif node.kind == "TEXT":
                    result = emit(key, node.config["text"])
                elif node.kind == "DATA":
                    result = emit(key, node.config["text"], signal=node.config["status"], confidence=node.config["confidence"])
                elif node.kind == "SLICE":
                    mode, argument = node.config["mode"], node.config["argument"]
                    if mode == "SECTION":
                        text = section(payload.text, argument)
                    elif mode == "YAML":
                        text = render(lookup(payload.metadata, argument))
                    else:
                        lines = payload.text.splitlines()
                        if node.config["end"] > len(lines):
                            raise WorkflowError("LINES interval exceeds input length.")
                        text = "\n".join(lines[node.config["start"] - 1:node.config["end"]])
                    result = emit(key, text, confidence=payload.confidence)
                    result.lineage = copy.deepcopy(payload.lineage)
                    for source in result.lineage.values():
                        source.setdefault("selections", []).append({"node_id": key, "kind": mode, "argument": argument, "fragment_sha256": digest(text.encode())})
                    decision["why"] = f"Extracted {mode}:{argument}; only the selected fragment is forwarded."
                elif node.kind in GATES:
                    passed = self.gate(node, active, payload)
                    result = Value(signal=passed, text=payload.text, context=payload.context,
                                   metadata=payload.metadata, confidence=payload.confidence, lineage=copy.deepcopy(payload.lineage))
                    decision["why"] = f"{node.kind} evaluated to {passed}; outgoing edge labels control the next branches."
                    if not passed and not any(e.label.casefold() in FALSE for e in node.outgoing):
                        raise WorkflowError(f"Critical gate {key} ({node.kind}) failed without a false route.")
                elif node.kind == "AGENT":
                    if len(json.dumps(payload.context, ensure_ascii=False)) > max_context_chars:
                        raise WorkflowError("Context exceeds max_context_chars; add a SLICE node.")
                    feedback = []
                    for attempt_index in range(node.config.get("max_retries", 0) + 1):
                        if len(router.calls) >= max_calls:
                            raise WorkflowError("Global max_calls budget exhausted.")
                        raw = router.generate(node.config, payload.context, feedback, node_id=key, attempt=attempt_index + 1)
                        try:
                            data = validate_response(raw)
                            ensure_no_secrets(data)
                            feedback = rule_errors(data, node.config)
                            if not data["status"]:
                                feedback.append("Agent returned status=false.")
                            schema = node.config.get("schema", "result")
                            if schema == "json":
                                json.loads(data["text"])
                            elif schema == "code_only":
                                if not ast.parse(data["text"]).body:
                                    raise WorkflowError("code_only requires non-empty Python code.")
                            if not feedback:
                                result = emit(key, data["text"], confidence=data["confidence"])
                                result.lineage = copy.deepcopy(payload.lineage)
                                decision["output_contract"] = check_contract(self.contracts.get(key, {}).get("output", {}), result)
                                decision["retry_history"].append({"attempt": attempt_index + 1, "accepted": True, "effect": router.calls[-1].get("idempotency_key")})
                                decision["why"] = "Agent output passed envelope, content and output-contract checks."
                                break
                        except (WorkflowError, ValueError, SyntaxError) as exc:
                            feedback = [str(exc)]
                        decision["retry_history"].append({"attempt": attempt_index + 1, "accepted": False, "validation_errors": redact(feedback), "effect": router.calls[-1].get("idempotency_key")})
                    else:
                        raise WorkflowError("Agent validation failed: " + "; ".join(feedback))
                elif node.kind == "WRITE":
                    self.policy.path(node.config["path"], writing=True)
                    staging.stage(node.config["path"], node.config["mode"], payload.text, key)
                    decision["why"] = "Write staged in memory; target files are unchanged until commit."
                elif node.kind == "OUTPUT":
                    outputs[key] = {"name": node.config["name"], "text": payload.text}
                elif node.kind == "ABORT":
                    raise WorkflowError(node.config["reason"])
                if node.kind not in {"FILE", "SLICE", "AGENT", "INPUT", "TEXT", "DATA"}:
                    result.lineage = copy.deepcopy(payload.lineage)
                if node.kind != "AGENT":
                    decision["output_contract"] = check_contract(self.contracts.get(key, {}).get("output", {}), result)
                ensure_no_secrets(result.public())
            except Exception as exc:
                aborted, abort_reason = True, redact(f"{key}: {exc}")
                result = Value(state="FAILED", signal=False, reason=redact(str(exc)))
                decision["why"] = redact(str(exc))
            result.duration_ms = round((time.perf_counter() - started) * 1000, 3)
            result.input_preview = payload.text[:160]
            result.attempts = len(router.calls) - first_call
            usage = sum_usage([call["usage"] for call in router.calls[first_call:]])
            result.tokens_used = usage["total_tokens"] if usage is not None else None
            decision["output_sha256"] = digest(result.text.encode())
            result.decision = decision
            values[key] = result
            session.checkpoint(key, result.public(), actual_inputs)
        terminal_ids = [n.id for n in self.nodes.values() if n.kind in {"WRITE", "OUTPUT"}]
        if not aborted and not any(values[key].state == "EXECUTED" for key in terminal_ids):
            outcome = "blocked"
        elif aborted:
            outcome = "error"
        else:
            outcome = "completed"
        if not aborted and outcome == "completed" and commit:
            try:
                if staging.files:
                    for source in sources.values():
                        path = self.policy.path(source["path"])
                        if str(path) != source["resolved"] or digest(path.read_bytes()) != source["sha256"]:
                            raise WorkflowError(f"Source changed during execution; refusing stale writes: {source['path']}")
                existing = store.metadata_path("transactions/" + run_id)
                if resume and (existing / "manifest.json").exists() and store.read_manifest(existing).get("status") == "committed":
                    prior = store.read_manifest(existing)
                    for entry in prior["files"]:
                        path = self.policy.path(entry["path"], writing=True)
                        if digest(path.read_bytes()) != entry["new_hash"]:
                            raise WorkflowError("Committed output changed externally; refusing to reapply writes.")
                    written = [entry["path"] for entry in prior["files"]]
                else:
                    written = store.commit(run_id, staging.files)
            except Exception as exc:
                aborted, abort_reason, outcome = True, str(exc), "error"
        usage = router.usage()
        transaction_state = "ABORTED" if aborted else ("COMMITTED" if written else ("PREVIEW" if staging.files and not commit else "NO_WRITES"))
        journal = store.metadata_path("transactions/" + run_id)
        if aborted and (journal / "manifest.json").exists():
            try:
                if store.read_manifest(journal).get("status") == "recovery_required":
                    transaction_state = "RECOVERY_REQUIRED"
            except WorkflowError:
                transaction_state = "RECOVERY_REQUIRED"
        report = {"engine": "canvasgate", "run_id": run_id, "canvas": str(self.canvas), "outcome": outcome,
                  "transaction_state": transaction_state,
                  "abort_reason": abort_reason, "calls": len(router.calls), "usage": usage,
                  "simulation": isinstance(backend, MockBackend),
                  "external_calls": sum(not call.get("cached") and not call.get("replayed") and call["backend"] != "MockBackend" for call in router.calls),
                  "cached_calls": sum(bool(call.get("cached")) for call in router.calls),
                  "model_calls": router.calls, "nodes": {key: value.public() for key, value in values.items()},
                  "outputs": outputs if not aborted else {}, "staged_mutations": staging.mutations,
                  "written_files": written, "source_fingerprints": list(sources.values()),
                  "audit_log": str(log.with_suffix(".md")), "timestamp": datetime.now(timezone.utc).isoformat()}
        self.audit(store, log, report)
        return report

    @staticmethod
    def audit(store, log, report):
        report = redact(report)
        atomic_bytes(log.with_suffix(".json"), json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
        usage = report["usage"]
        lines = [f"# CanvasGate run {report['run_id']}", "", f"- State: **{report['transaction_state']}** ({report['outcome']})",
                 f"- Timestamp (UTC): {report['timestamp']}", f"- Simulation: {report['simulation']}",
                 f"- Model attempts: {report['calls']}", f"- Reported tokens: {usage['total_tokens'] if usage is not None else 'unavailable'}",
                 f"- Written files: {len(report['written_files'])}", f"- Abort reason: {report['abort_reason'] or 'none'}", "",
                 "| Node | State | Attempts | Tokens | Duration (ms) | Output / reason |",
                 "| --- | --- | ---: | ---: | ---: | --- |"]
        for key, value in report["nodes"].items():
            preview = (value["reason"] or value["text"])[:100].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {key} | {value['state']} | {value['attempts']} | {value['tokens_used']} | {value['duration_ms']} | {preview} |")
        if report["written_files"]:
            lines += ["", "## Committed files", "", *[f"- [[{name}]]" for name in report["written_files"]]]
        if report["outputs"]:
            lines += ["", "## Accepted outputs", ""]
            for output in report["outputs"].values():
                lines += [f"### {output['name']}", "", output["text"], ""]
        atomic_bytes(log.with_suffix(".md"), "\n".join(lines).encode("utf-8"))
