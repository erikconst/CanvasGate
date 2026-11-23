"""Canvas parsing, deterministic gates, context routing and global call budget."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from .backends import WorkflowError, validate_response


def integer(value, name, minimum=0, maximum=1000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise WorkflowError(f"{name} must be an integer between {minimum} and {maximum}.")
    return value


def confidence(value):
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise WorkflowError("min_confidence must be between 0 and 1.")
    return value


def options(body, allowed):
    try:
        value = json.loads(body or "{}")
    except ValueError as exc:
        raise WorkflowError("Invalid JSON configuration in node.") from exc
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise WorkflowError(f"Configuration accepts only: {', '.join(sorted(allowed))}.")
    return value


def check_rules(config):
    for key in ("min_words", "max_words"):
        if key in config:
            integer(config[key], key)
    if config.get("min_words", 0) > config.get("max_words", 1000000):
        raise WorkflowError("min_words exceeds max_words.")
    if "min_confidence" in config:
        confidence(config["min_confidence"])
    if "pattern" in config:
        if not isinstance(config["pattern"], str):
            raise WorkflowError("pattern must be a string.")
        try:
            re.compile(config["pattern"])
        except re.error as exc:
            raise WorkflowError(f"Invalid regex: {exc}") from exc


@dataclass
class Node:
    id: str
    kind: str
    body: str = ""
    config: dict = field(default_factory=dict)
    parents: list = field(default_factory=list)


@dataclass
class Result:
    state: str
    status: bool = False
    confidence: float = 0.0
    text: str = ""
    context: dict = field(default_factory=dict)
    attempts: int = 0
    reason: str = ""

    def public(self):
        return {key: getattr(self, key) for key in ("state", "status", "confidence", "text", "attempts", "reason")}


RULES = {"min_words", "max_words", "min_confidence", "pattern"}


class LegacyWorkflow:
    def __init__(self, canvas, vault=None):
        self.canvas = Path(canvas).resolve()
        self.vault = Path(vault).resolve() if vault else self.canvas.parent
        if not self.canvas.is_relative_to(self.vault):
            raise WorkflowError("Canvas must be inside the vault.")
        try:
            raw = json.loads(self.canvas.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise WorkflowError(f"Cannot read Canvas: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
            raise WorkflowError("Canvas requires nodes and edges arrays.")
        self.nodes = {}
        ids = set()
        for item in raw["nodes"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
                raise WorkflowError("Missing or duplicate node ID.")
            ids.add(item["id"])
            if item.get("type") == "group":
                continue
            node = self.parse(item)
            self.nodes[node.id] = node
        edge_ids, connections = set(), set()
        for edge in raw["edges"]:
            if not isinstance(edge, dict):
                raise WorkflowError("Invalid edge.")
            source, target = edge.get("fromNode"), edge.get("toNode")
            edge_id = edge.get("id")
            if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
                raise WorkflowError("Missing or duplicate edge ID.")
            edge_ids.add(edge_id)
            if not isinstance(source, str) or not isinstance(target, str) or source not in self.nodes or target not in self.nodes:
                raise WorkflowError("Edge references an unknown node or a visual group.")
            if (source, target) in connections:
                raise WorkflowError("Duplicate edge between the same nodes.")
            connections.add((source, target))
            self.nodes[target].parents.append(source)
        if not any(node.kind == "OUTPUT" for node in self.nodes.values()):
            raise WorkflowError("Workflow requires at least one OUTPUT: node.")
        for node in self.nodes.values():
            count = len(node.parents)
            if node.kind in {"TEXT", "DATA", "FILE"} and count:
                raise WorkflowError(f"Source {node.id} cannot have incoming edges.")
            if node.kind not in {"TEXT", "DATA", "FILE"} and not count:
                raise WorkflowError(f"Node {node.id} requires explicit inputs.")
            if node.kind in {"NOT", "REGEX", "WORDS", "CONFIDENCE"} and count != 1:
                raise WorkflowError(f"Gate {node.kind} requires exactly one input.")
        self.order = []
        remaining = dict(self.nodes)
        while remaining:
            ready = [key for key, node in remaining.items() if all(p in self.order for p in node.parents)]
            if not ready:
                raise WorkflowError("Cycle detected. The workflow requires a DAG; use max_retries in the CODEX node.")
            for key in ready:
                self.order.append(key)
                del remaining[key]

    def resolve_note(self, name):
        if not isinstance(name, str) or not name:
            raise WorkflowError("Invalid note path.")
        path = (self.vault / name).resolve()
        if not path.is_relative_to(self.vault) or path.suffix.lower() != ".md" or not path.is_file():
            raise WorkflowError("Notes must be existing .md files inside the vault (no traversal or external symlinks).")
        return path

    def parse(self, item):
        if item.get("type") == "file":
            self.resolve_note(item.get("file"))
            if item.get("subpath"):
                raise WorkflowError("subpath is not supported; use a text node with the desired paragraph.")
            return Node(item["id"], "FILE", config={"file": item["file"]})
        if item.get("type") != "text" or not isinstance(item.get("text"), str):
            raise WorkflowError("Only text nodes, Markdown file nodes, and visual groups are accepted.")
        text = item["text"]
        header, _, body = text.partition("\n")
        header = header.strip()
        if header.startswith("GATE:"):
            kind = header[5:].strip().upper()
            if kind not in {"AND", "OR", "NOT", "REGEX", "WORDS", "CONFIDENCE"}:
                raise WorkflowError(f"Unknown gate: {kind}")
            allowed = {"REGEX": {"pattern"}, "WORDS": {"min_words", "max_words"}, "CONFIDENCE": {"min_confidence"}}.get(kind, set())
            config = options(body, allowed)
            check_rules(config)
            if kind == "REGEX" and "pattern" not in config:
                raise WorkflowError("GATE: REGEX requires pattern.")
            if kind == "CONFIDENCE" and "min_confidence" not in config:
                raise WorkflowError("GATE: CONFIDENCE requires min_confidence.")
            return Node(item["id"], kind, config=config)
        if header == "CODEX:":
            config = options(body, RULES | {"prompt", "max_retries"})
            if not isinstance(config.get("prompt"), str) or not config["prompt"].strip():
                raise WorkflowError("CODEX requires a nonempty prompt string.")
            integer(config.get("max_retries", 0), "max_retries", maximum=10)
            check_rules(config)
            return Node(item["id"], "CODEX", config=config)
        if header == "DATA:":
            config = options(body, {"status", "confidence", "text"})
            validate_response(config)
            return Node(item["id"], "DATA", config=config)
        if header.startswith("OUTPUT:"):
            if body.strip():
                raise WorkflowError("OUTPUT accepts only a title on the first line.")
            return Node(item["id"], "OUTPUT", header[7:].strip() or item["id"])
        if header == "TEXT:":
            text = body
        return Node(item["id"], "TEXT", text)

    def plan(self):
        return [{"id": key, "kind": self.nodes[key].kind, "parents": self.nodes[key].parents} for key in self.order]

    def run(self, backend, *, max_calls=3, max_context_chars=16000):
        integer(max_calls, "max_calls", maximum=100)
        integer(max_context_chars, "max_context_chars", minimum=1)
        results, outputs, calls = {}, {}, 0
        for key in self.order:
            node = self.nodes[key]
            parents = [results[p] for p in node.parents]
            context = {}
            for parent in parents:
                if parent.state == "done" and parent.status:
                    context.update(parent.context)
            texts = "\n\n".join(p.text for p in parents if p.state == "done" and p.status)
            if node.kind in {"TEXT", "DATA", "FILE"}:
                if node.kind == "FILE":
                    try:
                        text = self.resolve_note(node.config["file"]).read_text(encoding="utf-8-sig")
                    except (WorkflowError, OSError, UnicodeError) as exc:
                        results[key] = Result("error", reason=str(exc))
                        continue
                    data = {"status": True, "confidence": 1.0, "text": text}
                elif node.kind == "DATA":
                    data = node.config
                else:
                    data = {"status": True, "confidence": 1.0, "text": node.body}
                results[key] = Result("done", **data, context={key: dict(data)} if data["status"] else {})
                continue
            available = [p for p in parents if p.state == "done"]
            if node.kind == "OR":
                passed = any(p.status for p in available)
                score = min((p.confidence for p in available if p.status), default=0.0)
                results[key] = Result("done", passed, score, texts, context if passed else {})
                continue
            if len(available) != len(parents):
                results[key] = Result("skipped", reason="An input is blocked or failed.")
                continue
            if node.kind == "NOT":
                passed = not parents[0].status
                results[key] = Result("done", passed, 1.0)
                continue
            if not all(p.status for p in parents):
                results[key] = Result("done" if node.kind == "AND" else "skipped", reason="Input conditions are false.")
                continue
            if node.kind == "AND":
                results[key] = Result("done", True, min(p.confidence for p in parents), texts, context)
            elif node.kind in {"REGEX", "WORDS", "CONFIDENCE"}:
                feedback = rule_errors(parents[0].public(), node.config)
                passed = not feedback
                results[key] = Result("done", passed, parents[0].confidence, texts, context if passed else {}, reason="; ".join(feedback))
            elif node.kind == "OUTPUT":
                results[key] = Result("done", True, min(p.confidence for p in parents), texts, context)
                outputs[key] = {"name": node.body, "text": texts}
            elif node.kind == "CODEX":
                if len(json.dumps(context, ensure_ascii=False)) > max_context_chars:
                    results[key] = Result("error", reason="Context exceeds max_context_chars; narrow inputs.")
                    continue
                feedback, last_text, attempts = [], "", 0
                for _ in range(node.config.get("max_retries", 0) + 1):
                    if calls >= max_calls:
                        feedback = ["Global max_calls budget exhausted."]
                        break
                    calls += 1
                    attempts += 1
                    try:
                        raw = backend.generate(node.config["prompt"], context, feedback)
                    except WorkflowError as exc:
                        feedback = [str(exc)]
                        break
                    try:
                        data = validate_response(raw)
                        last_text = data["text"]
                        feedback = rule_errors(data, node.config)
                        if not data["status"]:
                            feedback.append("Model returned status=false.")
                    except WorkflowError as exc:
                        feedback = [str(exc)]
                    if not feedback:
                        results[key] = Result("done", **data, context={key: dict(data)}, attempts=attempts)
                        break
                if key not in results:
                    results[key] = Result("error", text=last_text, attempts=attempts, reason="; ".join(feedback))
        output_nodes = [n.id for n in self.nodes.values() if n.kind == "OUTPUT"]
        outcome = "error" if any(r.state == "error" for r in results.values()) else (
            "completed" if all(results[key].status for key in output_nodes) else "blocked")
        return {"outcome": outcome, "calls": calls, "nodes": {key: value.public() for key, value in results.items()}, "outputs": outputs}


def rule_errors(data, config):
    errors = []
    count = len(data["text"].split())
    if count < config.get("min_words", 0):
        errors.append(f"Too few words: {count}.")
    if count > config.get("max_words", 1000000):
        errors.append(f"Too many words: {count}.")
    if data["confidence"] < config.get("min_confidence", 0):
        errors.append("confidence below threshold.")
    if "pattern" in config and not re.search(config["pattern"], data["text"]):
        errors.append("Text does not match regex.")
    return errors


def Workflow(canvas, vault=None, *, engine="auto"):
    """Select CanvasGate for its DSL; preserve the existing CanvasGate v0.1 graphs."""
    if engine not in {"auto", "legacy", "canvasgate"}:
        raise WorkflowError("Unknown workflow engine.")
    use_canvasgate = engine == "canvasgate"
    if engine == "auto":
        try:
            raw = json.loads(Path(canvas).read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                nodes, edges = raw.get("nodes", []), raw.get("edges", [])
                if isinstance(nodes, list) and isinstance(edges, list):
                    use_canvasgate = "canvasgate" in raw or any(isinstance(edge, dict) and isinstance(edge.get("label"), str) and edge["label"].strip() for edge in edges)
                    use_canvasgate |= any(isinstance(node, dict) and isinstance(node.get("text"), str) and re.match(
                        r"^\s*(?:(?:INPUT|SLICE|AGENT|WRITE|JOIN|MERGE|ABORT):|GATE:\s*(?:YAML_EQ|LEN_LT|JSON_KEYS|REGEX)\s*:)",
                        node["text"], re.IGNORECASE) is not None for node in nodes)
        except (OSError, ValueError, UnicodeError):
            pass
    if use_canvasgate:
        from .canvasgate import CanvasGateWorkflow
        return CanvasGateWorkflow(canvas, vault)
    if engine == "legacy":
        try:
            raw = json.loads(Path(canvas).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeError):
            raw = {}
        if isinstance(raw, dict) and "canvasgate" in raw:
            raise WorkflowError("Legacy mode cannot honor CanvasGate contracts or permissions; use the CanvasGate engine.")
    return LegacyWorkflow(canvas, vault)
