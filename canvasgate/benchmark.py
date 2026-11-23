"""Three sequential real Codex runs with auditable usage and an exact-answer oracle.

Usage: python -m canvasgate.benchmark --prepare-only
       python -m canvasgate.benchmark
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile

from .backends import CodexBackend, WorkflowError, validate_response
from .engine import Workflow


ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "examples" / "vault"
FIXTURE = VAULT / "Benchmark"
MODEL = "gpt-6.1-sol"
TASK = (
    "Solve the medium-complexity dispatch planning task in English using the CURRENT policy, fleet and orders. "
    "Ignore superseded and unrelated documents. Follow the deterministic greedy policy exactly; do not optimize it. "
    "Return the outer JSON object {status:true, confidence:number, text:string}. The text field must contain "
    "ONLY a JSON-encoded dispatch result with keys assignments, rejected, truck_loads, total_revenue. "
    "assignments: list of {order_id,truck_id} sorted by order_id. rejected: list of {order_id,reason} sorted by order_id. "
    "truck_loads: list of {truck_id,weight_kg,volume_m3} sorted by truck_id, including unused trucks. "
    "total_revenue: integer sum of assigned order revenue. Do not include commentary or Markdown fences."
)

POLICY = """# Current dispatch policy
Status: CURRENT; version: 2.0; authoritative for this benchmark.

1. Reject status=cancelled with reason `cancelled` and status=hold with reason `on_hold`.
2. For active orders, identify trucks serving that order's zone. If none, reject `unsupported_zone`.
3. Within those trucks, filter by supported temperature. If none, reject `unsupported_temperature`.
4. Process the remaining active orders in ascending (priority, deadline_hour, order_id). Priority 1 is highest.
5. For each order, examine compatible trucks in ascending truck_id. Assign it to the FIRST truck for which
   adding its weight AND volume would not exceed the truck's remaining capacity. Equality is allowed.
6. Never split an order, move a previous assignment, or search for a better solution. If no truck fits, reject `capacity`.
7. Each truck has one departure; capacities are cumulative over this one batch. There are no reloads.
8. Sum revenue only for assigned orders. Sort the final output lists as requested in the task.

Use only this current policy, the current fleet, and the current orders. Other notes are background or obsolete.
"""

FLEET = [
    {"truck_id": "T1", "weight_kg": 1000, "volume_m3": 6, "zones": ["east", "west"], "temperatures": ["ambient", "chilled"]},
    {"truck_id": "T2", "weight_kg": 800, "volume_m3": 5, "zones": ["east"], "temperatures": ["ambient"]},
    {"truck_id": "T3", "weight_kg": 600, "volume_m3": 4, "zones": ["west"], "temperatures": ["ambient", "chilled"]},
]


def order(number, priority, deadline, zone, temperature, weight, volume, revenue, status="active"):
    return dict(order_id=f"O{number:02d}", priority=priority, deadline_hour=deadline, zone=zone,
                temperature=temperature, weight_kg=weight, volume_m3=volume, revenue=revenue, status=status)


ORDERS = [
    order(1, 1, 9, "east", "chilled", 700, 4, 500),
    order(2, 1, 9, "west", "chilled", 450, 3, 350),
    order(3, 1, 10, "east", "ambient", 500, 3, 220),
    order(4, 2, 10, "west", "ambient", 250, 1, 180),
    order(5, 2, 11, "east", "chilled", 200, 1, 160),
    order(6, 2, 11, "east", "ambient", 250, 2, 140),
    order(7, 2, 12, "west", "chilled", 150, 1, 130),
    order(8, 3, 12, "east", "ambient", 50, 1, 90),
    order(9, 3, 13, "east", "ambient", 10, 1, 30),
    order(10, 1, 8, "north", "ambient", 100, 1, 100),
    order(11, 1, 8, "east", "frozen", 100, 1, 100),
    order(12, 1, 8, "east", "ambient", 100, 1, 100, "cancelled"),
    order(13, 1, 8, "west", "ambient", 100, 1, 100, "hold"),
    order(14, 2, 10, "west", "ambient", 1100, 1, 800),
]


def expected_result():
    loads = {t["truck_id"]: {"truck_id": t["truck_id"], "weight_kg": 0, "volume_m3": 0} for t in FLEET}
    assignments, rejected, total = [], [], 0
    for item in sorted(ORDERS, key=lambda o: (o["priority"], o["deadline_hour"], o["order_id"])):
        reason = {"cancelled": "cancelled", "hold": "on_hold"}.get(item["status"])
        candidates = [t for t in FLEET if item["zone"] in t["zones"]]
        if not reason and not candidates:
            reason = "unsupported_zone"
        candidates = [t for t in candidates if item["temperature"] in t["temperatures"]]
        if not reason and not candidates:
            reason = "unsupported_temperature"
        if not reason:
            chosen = next((t for t in candidates if all(loads[t["truck_id"]][f] + item[f] <= t[f] for f in ("weight_kg", "volume_m3"))), None)
            if chosen:
                assignments.append({"order_id": item["order_id"], "truck_id": chosen["truck_id"]})
                for field in ("weight_kg", "volume_m3"):
                    loads[chosen["truck_id"]][field] += item[field]
                total += item["revenue"]
            else:
                reason = "capacity"
        if reason:
            rejected.append({"order_id": item["order_id"], "reason": reason})
    return {"assignments": sorted(assignments, key=lambda a: a["order_id"]),
            "rejected": sorted(rejected, key=lambda a: a["order_id"]),
            "truck_loads": list(loads.values()), "total_revenue": total}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def prepare():
    FIXTURE.mkdir(parents=True, exist_ok=True)
    notes = {
        "Policy.md": POLICY,
        "Fleet.md": "# Current fleet\nStatus: CURRENT\n\n```json\n" + json.dumps(FLEET, indent=2) + "\n```\n",
        "Orders.md": "# Current orders\nStatus: CURRENT\n\n```json\n" + json.dumps(ORDERS, indent=2) + "\n```\n",
        "Old-policy.md": "# Historical policy\nStatus: SUPERSEDED; version: 1.0; do not use.\n\n"
            "The former policy sorted by revenue descending and allowed splitting orders. The previous fleet served north. "
            "These historical rules were retired and do not apply to the current batch.\n",
        "Marketing.md": "# Marketing background\nStatus: UNRELATED; not a dispatch input.\n\n"
            "The business plans to refresh its customer portal, photograph vehicles, and launch a monthly newsletter. "
            "Marketing ideas include greener packaging, customer stories, educational videos about refrigerated transport, "
            "and a refreshed visual identity. No proposal here changes current capacities, delivery priorities, or supported zones.\n",
        "Warehouse.md": "# Warehouse retrospective\nStatus: UNRELATED; not a dispatch input.\n\n"
            "The previous quarterly review discussed aisle signs, barcode printers, staff breaks, equipment checks, training, "
            "inventory cycle counting and a future packing bench. A tentative second departure and extra cold storage were "
            "discussed but never approved. Do not infer extra vehicle capacity or reloads from these discussions.\n",
    }
    for filename, text in notes.items():
        (FIXTURE / filename).write_text(text, encoding="utf-8")
    index = ("# Dispatch benchmark — English\n\n" + TASK + "\n\n"
             "## Authoritative inputs\nRead only these three current notes:\n"
             "- [[Policy]] — deterministic dispatch rules\n- [[Fleet]] — three vehicles\n- [[Orders]] — fourteen orders\n\n"
             "## Excluded material\n[[Old-policy]] is superseded; [[Marketing]] and [[Warehouse]] are unrelated.\n\n"
             "[[workflow.canvas|Open the gated workflow]]\n\nAfter running, open [[Results/COMPARISON|the measured comparison]].\n")
    (FIXTURE / "INDEX.md").write_text(index, encoding="utf-8")
    nodes, edges = [], []

    def node(key, text, x, y, width=340, height=230):
        nodes.append(dict(id=key, type="text", text=text, x=x, y=y, width=width, height=height))

    def edge(source, target):
        edges.append(dict(id=f"e{len(edges)}", fromNode=source, fromSide="right", toNode=target, toSide="left"))

    for i, filename in enumerate(notes):
        key = filename[:-3].lower()
        nodes.append(dict(id=key, type="file", file="Benchmark/" + filename, x=0, y=i * 280, width=340, height=240))
        if i < 3:
            node(key + "-check", 'GATE: REGEX\n{"pattern":"Status: CURRENT"}', 420, i * 280)
            edge(key, key + "-check")
            edge(key + "-check", "ready")
        else:
            node(key + "-off", 'DATA:\n{"status":false,"confidence":1,"text":"Excluded: superseded or unrelated source."}', 420, i * 280)
            node(key + "-gate", "GATE: AND", 830, i * 280)
            edge(key, key + "-gate")
            edge(key + "-off", key + "-gate")
            edge(key + "-gate", "selected")
    node("ready", "GATE: AND", 830, 280)
    node("selected", "GATE: OR", 1240, 280)
    edge("ready", "selected")
    node("dispatch", "CODEX:\n" + json.dumps({"prompt": TASK, "max_retries": 0, "pattern": "total_revenue"}), 1650, 280, 520, 420)
    node("output", "OUTPUT: English dispatch plan", 2270, 280)
    edge("selected", "dispatch")
    edge("dispatch", "output")
    write_json(FIXTURE / "workflow.canvas", {"nodes": nodes, "edges": edges})
    return notes


def assess(response):
    try:
        validate_response(response)
        parsed = json.loads(response["text"])
        expected = expected_result()
        checks = {key: type(parsed) is dict and parsed.get(key) == value for key, value in expected.items()}
        return {"passed": response["status"] and all(checks.values()) and set(parsed) == set(expected), "checks": checks, "result": parsed}
    except (ValueError, KeyError, TypeError) as exc:
        return {"passed": False, "error": str(exc)}


def run_stage(number, notes, directory, timeout, *, agent_reads=False):
    stage = directory / f"{number:02d}"
    stage.mkdir()
    backend = CodexBackend(MODEL, timeout=timeout, reasoning_effort="medium", event_dir=stage / "events")
    report = None
    response = None
    try:
        if number == 1:
            packet = "\n\n".join(f"--- DOCUMENT: {name} ---\n{text}" for name, text in notes.items())
            prompt = TASK + "\n\nUse only this supplied document packet; do not read files or use tools.\n\n" + packet
            response = backend.run_prompt(prompt)
        elif number == 2:
            if not agent_reads:
                selected = {name: notes[name] for name in ("Policy.md", "Fleet.md", "Orders.md")}
                packet = "\n\n".join(f"--- DOCUMENT: {name} ---\n{text}" for name, text in selected.items())
                prompt = TASK + "\n\nThese authoritative notes were selected manually in Obsidian. Use only this packet; do not read files or use tools.\n\n" + packet
                response = backend.run_prompt(prompt)
            else:
                with tempfile.TemporaryDirectory(prefix="canvasgate-organized-") as folder:
                    snapshot = Path(folder)
                    for filename in [*notes, "INDEX.md"]:
                        shutil.copyfile(FIXTURE / filename, snapshot / filename)
                    prompt = (TASK + "\n\nThe current directory is a snapshot of the Obsidian benchmark notes. "
                              "Read INDEX.md first and follow its authoritative-input links. Use read-only shell commands "
                              "to read the required notes; do not edit files. Do not access other folders or network. "
                              "Do not read unrelated notes. The Canvas engine is not available in this variant.")
                    response = backend.run_prompt(prompt, allow_tools=True, working_directory=snapshot)
        else:
            workflow = Workflow(FIXTURE / "workflow.canvas", VAULT)
            report = workflow.run(backend, max_calls=1, max_context_chars=24000)
            write_json(stage / "workflow-report.json", report)
            model_node = report["nodes"]["dispatch"]
            response = {key: model_node[key] for key in ("status", "confidence", "text")}
        write_json(stage / "response.json", response)
        result = {"variant": number, "execution_error": None, "quality": assess(response)}
    except WorkflowError as exc:
        result = {"variant": number, "execution_error": str(exc), "quality": {"passed": False}}
    result.update({"usage": backend.token_usage(), "model_runs": backend.runs,
                   "elapsed_seconds": round(sum(r["elapsed_seconds"] or 0 for r in backend.runs), 3),
                   "tool_calls": sum(r["tool_calls"] for r in backend.runs)})
    write_json(stage / "measurement.json", result)
    return result


def comparison(results, directory, excluded=None):
    labels = {1: "Direct Codex — full packet", 2: "Obsidian — manually selected notes", 3: "Obsidian + CanvasGate — gated context"}
    lines = ["# Measured token comparison", "", "English medium-complexity dispatch task: 14 orders, 3 trucks.", "",
             f"Model: `{MODEL}`. Reasoning effort: `medium`. One fresh session per invocation.", "",
             "| Variant | Input | Cached input (subset) | Uncached input | Output | Total | Seconds | Completed tool calls | Exact result |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for result in results:
        usage = result["usage"] or {}
        values = [str(usage.get(key, "unavailable")) for key in ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "total_tokens")]
        lines.append(f"| {labels[result['variant']]} | " + " | ".join(values) + f" | {result['elapsed_seconds']} | {result['tool_calls']} | {'PASS' if result['quality']['passed'] else 'FAIL'} |")
    base = results[0]["usage"]
    lines += ["", "## Comparison with direct run", ""]
    for result in results[1:]:
        if base and result["usage"]:
            delta = 100 * (1 - result["usage"]["total_tokens"] / base["total_tokens"])
            lines.append(f"- Variant {result['variant']}: {delta:+.2f}% fewer total tokens than variant 1 (negative = more tokens).")
    if excluded:
        failed_total = sum((r.get("usage") or {}).get("total_tokens", 0) for r in excluded)
        all_total = failed_total + sum((r.get("usage") or {}).get("total_tokens", 0) for r in results)
        lines += ["", "## Blocked preliminary attempt (included in experiment spend)", "",
                  "Actual execution order: 1 → 2 (blocked) → 3 → 2 (manual export fallback). The successful second variant was rerun after the third; previous answers were never supplied as input.",
                  "Automatic approval review rejected the initial second variant's attempts to read INDEX.md using Get-Content and type as `blocked by policy`. That session returned no dispatch result. Completed-tool counts do not include those rejected attempts.",
                  f"The blocked attempt consumed **{failed_total:,} reported tokens**. Its full events and response are preserved in `02-blocked/`.",
                  f"Successful samples plus the blocked attempt consumed **{all_total:,} reported tokens** in total. The main table compares only successful, quality-checked samples; the blocked attempt is not evidence that Obsidian itself is expensive."]
    lines += ["", "## Method and limits", "",
              "- These are CLI-reported turn usage counters from raw `turn.completed` events, not character-based estimates.",
              "- Total = input + output. Cached input is already included in input; it is not added again.",
              "- Full run usage includes intermediate model/tool interactions. Output can include hidden reasoning; visible answer length is not a token count.",
              "- Variant 1 receives all six source notes as a direct prompt. Variant 2 receives a manual export of the three notes selected using the Obsidian index, without Canvas gates or model file reads. Variant 3 uses the actual Canvas engine to gate out three irrelevant/superseded notes, then sends the same three authoritative notes as context without model file reads.",
              "- Obsidian itself makes no model call. Savings come from context selection and avoided agent interactions; the app alone has no token-reduction mechanism.",
              "- This compares three practical workflows, not an isolated causal effect of Obsidian. Input packaging and tool availability differ intentionally. Curating the index and Canvas required setup work.",
              "- Exactly one sample per variant; no statistical claim. Execution order and cache reuse can affect counters, latency and billing. Cached tokens are reported separately; token totals are not monetary cost or subscription-quota percentages.",
              "- Confidence 1.0 is not a quality measurement; quality PASS means the complete structured result matched the independent local oracle.",
              "- Benchmark fixture preparation, this chat, and test-harness development are excluded. Runtime retries, if any, are included; each variant is limited to one external Codex invocation in this benchmark.",
              "- All outputs are checked locally against an independent deterministic oracle for assignments, rejection reasons, loads and revenue. No model judge is used.",
              "- Raw events, exact prompts, responses and measurement JSON are stored beside this report in 01/, 02/ and 03/. Earlier results are never included in the next variant's context.",
              "", "## Expected result", "", "```json", json.dumps(expected_result(), indent=2), "```", ""]
    lines += ["Official usage event documentation: https://developers.openai.com/codex/noninteractive", ""]
    (directory / "COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")
    (FIXTURE / "Results" / "COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--agent-reads", action="store_true", help="Try model-driven file reads for variant 2 instead of manual note export")
    parser.add_argument("--repair-organized", type=Path, help="Preserve a blocked variant 2 and rerun only that variant using manual export")
    args = parser.parse_args()
    notes = prepare()
    if args.prepare_only:
        print(FIXTURE / "workflow.canvas")
        return 0
    if args.repair_organized:
        directory = args.repair_organized.resolve()
        if not directory.is_relative_to((FIXTURE / "Results").resolve()):
            raise WorkflowError("Repair directory must be inside this benchmark's Results folder.")
        results = json.loads((directory / "measurements.json").read_text(encoding="utf-8"))
        failed = results[1]
        if failed["quality"]["passed"] or (directory / "02-blocked").exists():
            raise WorkflowError("Expected one blocked, unarchived organized attempt.")
        (directory / "02").rename(directory / "02-blocked")
        (directory / "COMPARISON.md").rename(directory / "COMPARISON-initial.md")
        print("Retrying only variant 2 with manual Obsidian note export...", flush=True)
        results[1] = run_stage(2, notes, directory, args.timeout)
        write_json(directory / "excluded-attempts.json", [failed])
        write_json(directory / "measurements.json", results)
        comparison(results, directory, [failed])
        print(json.dumps(results[1], indent=2), flush=True)
        print(f"Report: {directory / 'COMPARISON.md'}", flush=True)
        return 0 if results[1]["quality"]["passed"] else 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = FIXTURE / "Results" / stamp
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "expected.json", expected_result())
    results = []
    for number in (1, 2, 3):
        print(f"Starting variant {number}/3 ({MODEL}, medium)...", flush=True)
        result = run_stage(number, notes, directory, args.timeout, agent_reads=args.agent_reads)
        results.append(result)
        print(json.dumps({key: result[key] for key in ("variant", "usage", "elapsed_seconds", "tool_calls", "execution_error")}), flush=True)
        print(f"Exact-answer check: {'PASS' if result['quality']['passed'] else 'FAIL'}", flush=True)
        write_json(directory / "measurements.json", results)
    comparison(results, directory)
    print(f"Report: {directory / 'COMPARISON.md'}", flush=True)
    return 0 if all(result["quality"]["passed"] and result["usage"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
