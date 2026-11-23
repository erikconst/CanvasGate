"""Stdio MCP server exposing CanvasGate and Obsidian vault workflows."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote
from uuid import uuid4

from .backends import ApiBackend, CodexBackend, MockBackend, WorkflowError
from .canvasgate import CanvasGateWorkflow
from .engine import Workflow
from .observability import export_run_view
from .security import SecurityPolicy, relative_name
from .snapshots import RunSession, decision_signature


SERVER_INFO = {"name": "canvasgate", "version": "0.3.0"}
PROTOCOL_VERSION = "2024-11-05"


def _obsidian_config_path():
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "obsidian" / "obsidian.json" if appdata else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "obsidian" / "obsidian.json"


def discover_vaults():
    """Return known Obsidian vaults plus the local repository example vault if present."""
    vaults = []
    seen = set()
    config_path = _obsidian_config_path()
    if config_path and config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for vault_id, entry in (data.get("vaults") or {}).items():
                raw_path = entry.get("path")
                if not raw_path:
                    continue
                resolved = Path(raw_path).resolve()
                key = str(resolved).casefold()
                if key not in seen:
                    seen.add(key)
                    vaults.append({
                        "id": vault_id,
                        "name": resolved.name,
                        "path": str(resolved),
                        "exists": resolved.is_dir(),
                        "open": bool(entry.get("open")),
                        "source": "obsidian",
                    })
        except (OSError, ValueError):
            pass
    repo_vault = (Path(__file__).resolve().parent.parent / "examples" / "vault").resolve()
    if repo_vault.is_dir() and str(repo_vault).casefold() not in seen:
        vaults.append({
            "id": "repo-example",
            "name": repo_vault.name,
            "path": str(repo_vault),
            "exists": True,
            "open": False,
            "source": "canvasgate-examples",
        })
    return vaults


def _resolve_vault(vault_path):
    if vault_path:
        path = Path(vault_path).resolve()
        if not path.is_dir():
            raise WorkflowError(f"Vault directory does not exist: {vault_path}")
        return path
    vaults = [v for v in discover_vaults() if v["exists"]]
    if not vaults:
        raise WorkflowError("No Obsidian vault found. Provide 'vault' path explicitly.")
    open_vault = next((v for v in vaults if v.get("open")), vaults[0])
    return Path(open_vault["path"]).resolve()


def _resolve_canvas(vault, canvas):
    policy = SecurityPolicy(vault)
    safe = relative_name(canvas)
    path = policy.path(safe)
    if path.suffix.casefold() != ".canvas" or not path.is_file():
        raise WorkflowError(f"Canvas file not found: {canvas}")
    return path


def tool_list_vaults(_args):
    return {"vaults": discover_vaults()}


def tool_list_canvases(args):
    vault = _resolve_vault(args.get("vault"))
    include_inspection = bool(args.get("include_inspection", False))
    policy = SecurityPolicy(vault)
    canvases = []
    for root, dirs, names in os.walk(vault, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules" and not (Path(root) / d).is_symlink()]
        for name in names:
            if Path(name).suffix.casefold() != ".canvas":
                continue
            rel = (Path(root) / name).relative_to(vault).as_posix()
            try:
                path = policy.path(rel)
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
            except (WorkflowError, OSError, ValueError):
                continue
            is_inspect = bool(raw.get("canvasgate_inspection_only"))
            if is_inspect and not include_inspection:
                continue
            canvases.append({
                "path": rel,
                "nodes": len(raw.get("nodes", [])),
                "edges": len(raw.get("edges", [])),
                "inspection_only": is_inspect,
                "has_canvasgate_settings": "canvasgate" in raw,
            })
    canvases.sort(key=lambda item: item["path"])
    return {"vault": str(vault), "canvases": canvases}


def tool_validate_canvas(args):
    vault = _resolve_vault(args.get("vault"))
    canvas_path = _resolve_canvas(vault, args["canvas"])
    engine = args.get("engine", "auto")
    workflow = Workflow(canvas_path, vault, engine=engine)
    return {"vault": str(vault), "canvas": canvas_path.relative_to(vault).as_posix(), "plan": workflow.plan()}


def _make_backend(backend_name, model=None, timeout=120, max_output_tokens=1000):
    if backend_name == "mock":
        return MockBackend()
    if backend_name == "api":
        return ApiBackend(model, timeout, max_output_tokens)
    if backend_name == "codex":
        return CodexBackend(model, timeout)
    raise WorkflowError(f"Unsupported backend: {backend_name}")


def tool_run_canvas(args):
    vault = _resolve_vault(args.get("vault"))
    canvas_path = _resolve_canvas(vault, args["canvas"])
    backend_name = args.get("backend", "mock")
    commit = bool(args.get("commit", False))
    strict_isolation = bool(args.get("strict_isolation", True))
    max_calls = int(args.get("max_calls", 3))
    max_context_chars = int(args.get("max_context_chars", 16000))
    workflow = Workflow(canvas_path, vault, engine=args.get("engine", "auto"))
    backend = _make_backend(backend_name, args.get("model"), int(args.get("timeout", 120)), int(args.get("max_output_tokens", 1000)))

    if isinstance(workflow, CanvasGateWorkflow):
        report = workflow.run(
            backend,
            max_calls=max_calls,
            max_context_chars=max_context_chars,
            run_id=args.get("run_id"),
            commit=commit,
            operation_key=args.get("operation_key"),
            strict_isolation=strict_isolation,
        )
    else:
        report = workflow.run(backend, max_calls=max_calls, max_context_chars=max_context_chars)
        report["engine"] = "legacy"

    output_rel = args.get("output_dir", "CanvasGate/Runs")
    output_dir = SecurityPolicy(vault).path(output_rel, writing=True)
    run_folder = output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:10])
    run_folder.mkdir(parents=True, exist_ok=False)
    (run_folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    inspect_path = export_run_view(workflow, report, run_folder) if isinstance(workflow, CanvasGateWorkflow) else None

    return {
        "outcome": report["outcome"],
        "engine": report.get("engine"),
        "run_id": report.get("run_id"),
        "calls": report.get("calls"),
        "external_calls": report.get("external_calls"),
        "transaction_state": report.get("transaction_state"),
        "written_files": report.get("written_files", []),
        "outputs": report.get("outputs", {}),
        "report_path": str(run_folder / "report.json"),
        "inspect_canvas": inspect_path,
    }


def tool_replay_canvas(args):
    vault = _resolve_vault(args.get("vault"))
    run_id = args["run_id"]
    original = RunSession.load(vault, run_id, verify_engine=False)
    original_report = original.read(original.root / "report.json")
    report = CanvasGateWorkflow.replay_run(vault, run_id, new_run_id=args.get("new_run_id"))
    return {
        "outcome": report["outcome"],
        "run_id": report.get("run_id"),
        "replay_of": run_id,
        "external_calls": report.get("external_calls"),
        "matches_original": decision_signature(report) == decision_signature(original_report),
        "outputs": report.get("outputs", {}),
    }


def tool_open_in_obsidian(args):
    vault = _resolve_vault(args.get("vault"))
    vault_name = vault.name
    file_arg = args.get("file")
    if file_arg:
        safe = relative_name(file_arg)
        SecurityPolicy(vault).path(safe)
        uri = f"obsidian://open?vault={quote(vault_name)}&file={quote(safe)}"
    else:
        uri = f"obsidian://open?vault={quote(vault_name)}"
    launched = False
    if args.get("launch", True):
        if os.name == "nt":
            os.startfile(uri)
            launched = True
    return {"uri": uri, "vault": str(vault), "launched": launched}


TOOLS = {
    "list_vaults": {
        "description": "Discover Obsidian vaults registered on this machine and the local example vault.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": tool_list_vaults,
    },
    "list_canvases": {
        "description": "List executable .canvas workflow files inside an Obsidian vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "description": "Optional vault directory path. Defaults to active Obsidian vault."},
                "include_inspection": {"type": "boolean", "description": "Include read-only Inspect.canvas files."},
            },
            "additionalProperties": False,
        },
        "handler": tool_list_canvases,
    },
    "validate_canvas": {
        "description": "Validate a .canvas workflow (preflight checks, contracts, topological order) without executing models or writing files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "canvas": {"type": "string", "description": "Vault-relative path to the .canvas file."},
                "vault": {"type": "string", "description": "Optional vault directory path."},
                "engine": {"type": "string", "enum": ["auto", "legacy", "canvasgate"]},
            },
            "required": ["canvas"],
            "additionalProperties": False,
        },
        "handler": tool_validate_canvas,
    },
    "run_canvas": {
        "description": "Execute a .canvas workflow with deterministic gates, contracts, and snapshot/inspect export (defaults to mock backend and no-commit).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "canvas": {"type": "string", "description": "Vault-relative path to the .canvas file."},
                "vault": {"type": "string", "description": "Optional vault directory path."},
                "backend": {"type": "string", "enum": ["mock", "codex", "api"]},
                "model": {"type": "string"},
                "commit": {"type": "boolean", "description": "Commit WRITE nodes to vault (default false)."},
                "strict_isolation": {"type": "boolean", "description": "Reject host Codex CLI execution (default true)."},
                "max_calls": {"type": "integer", "minimum": 0, "maximum": 100},
                "max_context_chars": {"type": "integer", "minimum": 1},
                "operation_key": {"type": "string"},
                "output_dir": {"type": "string", "description": "Vault-relative directory for run reports and Inspect.canvas."},
            },
            "required": ["canvas"],
            "additionalProperties": False,
        },
        "handler": tool_run_canvas,
    },
    "replay_canvas": {
        "description": "Offline deterministic replay of a previous CanvasGate run using its pinned snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "vault": {"type": "string"},
                "new_run_id": {"type": "string"},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "handler": tool_replay_canvas,
    },
    "open_in_obsidian": {
        "description": "Open an Obsidian vault or specific .canvas/.md file directly in the Obsidian app via obsidian:// URI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "description": "Optional vault directory path."},
                "file": {"type": "string", "description": "Optional vault-relative file or .canvas path."},
                "launch": {"type": "boolean", "description": "Launch Obsidian URI immediately (default true)."},
            },
            "additionalProperties": False,
        },
        "handler": tool_open_in_obsidian,
    },
}


def handle_request(request, *, tools=None, protocol=None, instructions=None, resources=None):
    tools = TOOLS if tools is None else tools
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": protocol or PROTOCOL_VERSION,
                "capabilities": {"tools": {}, **({"resources": {}} if resources else {})},
                "serverInfo": SERVER_INFO if not instructions else {"name": "CanvasGate Studio", "version": "0.4.0"},
                **({"instructions": instructions} if instructions else {}),
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        tool_list = [
            {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
            for name, spec in tools.items()
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tool_list}}
    if resources and method == "resources/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": [
            {"uri": uri, "name": item["name"], "mimeType": "text/markdown"} for uri, item in resources.items()
        ]}}
    if resources and method == "resources/read" and params.get("uri") in resources:
        uri = params["uri"]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"contents": [
            {"uri": uri, "mimeType": "text/markdown", "text": resources[uri]["text"]}
        ]}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in tools:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        try:
            data = tools[name]["handler"](arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}], "isError": False},
            }
        except (WorkflowError, KeyError, ValueError, OSError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True},
            }
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
