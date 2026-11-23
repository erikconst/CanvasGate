"""Human-readable node decisions and a separate inspection-only Obsidian Canvas."""

import copy
import json
from pathlib import Path

from .security import ensure_no_secrets, reject_links
from .snapshots import fingerprint
from .transactions import atomic_bytes


def export_run_view(workflow, report, directory):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(workflow.vault):
        return None
    reject_links(workflow.vault, directory.relative_to(workflow.vault).as_posix())
    directory.mkdir(parents=True, exist_ok=True)
    ensure_no_secrets(report)
    view = copy.deepcopy(workflow.raw)
    view.pop("canvasgate", None)
    view["canvasgate_inspection_only"] = {"run_id": report["run_id"], "source_graph": str(workflow.canvas)}
    for node in view["nodes"]:
        key = node["id"]
        if key not in report["nodes"]:
            continue
        result = report["nodes"][key]
        decision = result.get("decision", {})
        filename = fingerprint(key)[:24] + ".md"
        path = directory / "nodes" / filename
        lines = [f"# {key} — {result['state']}", "", f"- Run: {report['run_id']}",
                 f"- Why: {decision.get('why') or result.get('reason') or 'No reason recorded'}",
                 f"- Model attempts: {result.get('attempts', 0)}", f"- Reported tokens: {result.get('tokens_used')}",
                 f"- Duration: {result.get('duration_ms', 0)} ms", f"- Input hash: `{decision.get('input_sha256', '')}`",
                 f"- Output hash: `{decision.get('output_sha256', '')}`", "", "## Received sources", ""]
        for name, source in decision.get("input_sources", {}).items():
            lines.append(f"- [[{name}]] — `{source['sha256']}`")
        lines += ["", "## Branch and contract checks", "", "```json", json.dumps(decision, ensure_ascii=False, indent=2), "```",
                  "", "## Output", "", result.get("text", "") or "No output was forwarded.", ""]
        atomic_bytes(path, "\n".join(lines).encode("utf-8"))
        node.clear()
        original = next(item for item in workflow.raw["nodes"] if item["id"] == key)
        node.update({"id": key, "type": "file", "file": path.relative_to(workflow.vault).as_posix(),
                     "x": original.get("x", 0), "y": original.get("y", 0), "width": max(original.get("width", 280), 280),
                     "height": max(original.get("height", 160), 160), "color": "4" if result["state"] == "EXECUTED" else ("1" if result["state"] == "FAILED" else "2")})
    active = {edge for result in report["nodes"].values() for edge in result.get("decision", {}).get("active_edges", [])}
    for edge in view["edges"]:
        edge["color"] = "4" if edge["id"] in active else "2"
    atomic_bytes(directory / "Inspect.canvas", json.dumps(view, ensure_ascii=False, indent=2).encode("utf-8"))
    return str(directory / "Inspect.canvas")
