import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

from .backends import ApiBackend, CodexBackend, MockBackend, WorkflowError
from .engine import Workflow, integer


def main(argv=None):
    parser = argparse.ArgumentParser(description="CanvasGate: Obsidian Canvas → deterministic gates → isolated agents")
    parser.add_argument("canvas", type=Path)
    parser.add_argument("--vault", type=Path, help="Default: Canvas parent directory")
    parser.add_argument("--engine", choices=["auto", "legacy", "canvasgate"], default="auto")
    parser.add_argument("--no-commit", action="store_true", help="Execute CanvasGate and audit, but discard staged writes")
    parser.add_argument("--run-id", help="Unique CanvasGate run ID; duplicates are refused")
    parser.add_argument("--recover", metavar="RUN_ID", help="Recover an incomplete CanvasGate transaction; no model calls")
    parser.add_argument("--replay", metavar="RUN_ID", help="Replay saved inputs/responses; no model calls or writes")
    parser.add_argument("--resume", metavar="RUN_ID", help="Resume the exact saved graph/configuration")
    parser.add_argument("--operation-key", help="Idempotency key for the entire operation")
    parser.add_argument("--strict-isolation", action="store_true", help="Reject host CLI execution; permit only mock/API")
    parser.add_argument("--backend", choices=["mock", "codex", "api"], default="mock")
    parser.add_argument("--model", help="Required for API; optional for CLI")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], help="Codex CLI only")
    parser.add_argument("--events-dir", type=Path, help="Save CLI events and prompts; may contain sensitive data")
    parser.add_argument("--dry-run", action="store_true", help="Validate the graph and print the plan without execution")
    parser.add_argument("--max-calls", type=int, default=3)
    parser.add_argument("--max-context-chars", type=int, default=16000)
    parser.add_argument("--max-output-tokens", type=int, default=1000, help="API backend only")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds per call")
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)
    try:
        integer(args.timeout, "timeout", minimum=1, maximum=3600)
        integer(args.max_output_tokens, "max_output_tokens", minimum=1)
        integer(args.max_calls, "max_calls", maximum=100)
        integer(args.max_context_chars, "max_context_chars", minimum=1)
        if args.recover:
            from .transactions import TransactionStore
            vault = args.vault or args.canvas.resolve().parent
            print(json.dumps(TransactionStore(vault).recover(args.recover), indent=2))
            return 0
        from .canvasgate import CanvasGateWorkflow
        vault = args.vault or args.canvas.resolve().parent
        if args.replay or args.resume:
            workflow = CanvasGateWorkflow.from_snapshot(vault, args.replay or args.resume)
        else:
            workflow = Workflow(args.canvas, args.vault, engine=args.engine)
        if args.dry_run:
            print(json.dumps(workflow.plan(), ensure_ascii=False, indent=2))
            return 0
        if args.replay:
            backend = MockBackend()
        elif args.backend == "api":
            backend = ApiBackend(args.model, args.timeout, args.max_output_tokens)
        elif args.backend == "codex":
            backend = CodexBackend(args.model, args.timeout, args.reasoning_effort, args.events_dir)
        else:
            backend = MockBackend()
        if args.replay:
            report = CanvasGateWorkflow.replay_run(vault, args.replay, new_run_id=args.run_id)
        elif args.resume:
            report = CanvasGateWorkflow.resume_run(vault, args.resume, backend)
        elif isinstance(workflow, CanvasGateWorkflow):
            report = workflow.run(backend, max_calls=args.max_calls, max_context_chars=args.max_context_chars,
                                  run_id=args.run_id, commit=not args.no_commit, operation_key=args.operation_key,
                                  strict_isolation=args.strict_isolation)
        else:
            if args.run_id or args.no_commit:
                raise WorkflowError("--run-id and --no-commit require the CanvasGate engine.")
            report = workflow.run(backend, max_calls=args.max_calls, max_context_chars=args.max_context_chars)
            report["engine"] = "legacy"
        if isinstance(backend, CodexBackend) and report["engine"] == "legacy":
            report["usage"] = backend.token_usage()
            report["model_calls"] = backend.runs
        report.update({"backend": args.backend, "canvas": str(workflow.canvas), "timestamp": datetime.now(timezone.utc).isoformat()})
        directory = args.output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:10])
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        content = "# Workflow results\n\n"
        content += f"Backend: {args.backend} | Engine: {report['engine']} | State: {report['outcome']} | Model attempts: {report['calls']}\n\n"
        if report.get("usage") is not None:
            content += f"Reported tokens: {report['usage']['total_tokens']}\n\n"
        if report.get("written_files"):
            content += "Written files: " + ", ".join(report["written_files"]) + "\n\n"
        for output in report["outputs"].values():
            content += f"## {output['name']}\n\n{output['text']}\n\n"
        if not report["outputs"]:
            content += "No accepted OUTPUT nodes. See report.json for node states and committed files.\n"
        (directory / "results.md").write_text(content, encoding="utf-8")
        if report.get("audit_log"):
            (directory / "RunReport.md").write_text(Path(report["audit_log"]).read_text(encoding="utf-8"), encoding="utf-8")
        if isinstance(workflow, CanvasGateWorkflow):
            from .observability import export_run_view
            export_run_view(workflow, report, directory)
        print(f"{report['outcome']} | backend={args.backend} | calls={report['calls']}")
        print(f"Report: {directory.resolve() / 'report.json'}")
        print(f"Results: {directory.resolve() / 'results.md'}")
        return {"completed": 0, "blocked": 2, "error": 1}[report["outcome"]]
    except (WorkflowError, OSError, UnicodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
