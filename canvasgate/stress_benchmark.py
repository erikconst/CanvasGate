"""Contradictory archive benchmark. Does not assume that the baseline will fail."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
from uuid import uuid4

from .backends import ApiBackend, CodexBackend, MockBackend, WorkflowError
from .benchmark import FLEET, ORDERS, POLICY, TASK, VAULT, MODEL, assess, write_json
from .canvasgate import CanvasGateWorkflow
from .providers import normalize_usage, sum_usage


FIXTURE = VAULT / "StressBenchmark"
CURRENT = ("Current-policy.md", "Current-fleet.md", "Current-orders.md")
INSTRUCTION = TASK + " Authoritative sources have YAML status: current AND domain: dispatch. Other domains and superseded revisions are not authoritative."


def note(title, status, domain, body, revision):
    body = re.sub(r"^(#{1,4})(\s+)", r"##\1\2", body, flags=re.MULTILINE)
    provenance = f"Excerpt authority (YAML):\n```yaml\nstatus: {status}\ndomain: {domain}\nrevision: {revision}\n```\n\n"
    return (f"---\ntitle: {title}\nstatus: {status}\ndomain: {domain}\nrevision: {revision}\n---\n"
            f"# {title}\n\n## DispatchInput\n\n{provenance}{body}\n")


def build_notes():
    notes = {
        CURRENT[0]: note("Current dispatch policy", "current", "dispatch", POLICY, 20),
        CURRENT[1]: note("Current fleet", "current", "dispatch", json.dumps(FLEET, indent=2), 20),
        CURRENT[2]: note("Current orders", "current", "dispatch", json.dumps(ORDERS, indent=2), 20),
    }
    for version in range(1, 7):
        old_fleet = json.loads(json.dumps(FLEET))
        old_fleet[0]["temperatures"].append("frozen")
        old_fleet[0]["zones"].append("north")
        old_fleet[0]["weight_kg"] = 1500 + version * 100
        old_fleet[0]["volume_m3"] = 10 + version
        old_fleet[1]["zones"].append("west")
        old_fleet[2]["weight_kg"] = 900 + version * 50
        old_orders = json.loads(json.dumps(ORDERS))
        old_orders[10]["temperature"] = "ambient"
        old_orders[11]["status"] = "active"
        old_orders[12]["status"] = "active"
        old_orders[13]["weight_kg"] = 400
        for item in old_orders:
            item["revenue"] += version * 10
        old_policy = ("ARCHIVE_ONLY: historical dispatch policy snapshot.\n\n"
                      "Priority is evaluated by revenue descending, then order_id. Orders may be split across trucks. "
                      "Each truck may reload for a second departure and may use its full capacity again after reloading. "
                      "The north zone is served by T1, and T1 accepts frozen freight. Held orders may ship if revenue is positive. "
                      "There is no duplicate-SKU or cancellation check in this historical plan.\n\n"
                      "## Historical operating procedure\n"
                      "Dispatchers first total the full order book and place high-value east-zone orders on T1. "
                      "Frozen orders use the same vehicle as chilled orders under the equipment assumptions in this revision. "
                      "North-zone orders take precedence over west-zone orders with equal revenue. A vehicle returning from "
                      "its first trip can be loaded again. Revenue is recognized for each partial shipment rather than for "
                      "the entire accepted order. Warehouse staff reserve oversize loads for the second trip when needed. "
                      "The fleet and order snapshots from this revision contain the corresponding historical assumptions.\n")
        for kind, body in (("policy", old_policy), ("fleet", "ARCHIVE_ONLY\n" + json.dumps(old_fleet, indent=2)),
                           ("orders", "ARCHIVE_ONLY\n" + json.dumps(old_orders, indent=2))):
            notes[f"Archive-{version:02d}-{kind}.md"] = note(f"Dispatch {kind} revision {version}", "superseded", "dispatch", body, version)
    topics = ["marketing", "procurement", "training", "facilities", "customer-research", "design", "finance", "hiring", "events"]
    for index, topic in enumerate(topics):
        body = (f"NOT_DISPATCH_INPUT: current {topic} planning record.\n\n"
                f"The {topic} team is reviewing its quarterly plans, owners and delivery milestones. The proposal is to "
                "collect feedback from stakeholders, compare alternatives, identify implementation risks, and prepare "
                "a short decision record. The first phase covers discovery and interviews. The second phase covers "
                "prototypes, cost estimates and vendor comparisons. The final phase covers a limited rollout and lessons "
                "learned. Each workstream should record its assumptions and revisit them during the next planning cycle.\n\n"
                f"## {topic.title()} decisions\n"
                "The current planning template requires an owner, a target date, a budget range, an acceptance checklist "
                "and links to supporting material. Teams should record unresolved questions before procurement begins. "
                "Reports should distinguish experiments from approved commitments. Customer interviews, accessibility "
                "reviews, staff training, documentation updates and communications are tracked as separate deliverables. "
                "These departmental plans do not amend the authoritative fleet, dispatch policy or current order book.\n")
        notes[f"Department-{index + 1:02d}-{topic}.md"] = note(topic.title() + " planning", "current", topic, body, 20)
    names = list(notes)
    random.Random(29).shuffle(names)
    return {name: notes[name] for name in names}


def build_canvas(names):
    nodes, edges = [], []

    def text(key, content, x, y, width=340, height=160):
        nodes.append(dict(id=key, type="text", text=content, x=x, y=y, width=width, height=height))

    def connect(source, target, label=""):
        edges.append(dict(id=f"e{len(edges)}", fromNode=source, fromSide="right", toNode=target, toSide="left", label=label))

    for index, name in enumerate(names):
        key, y = f"source-{index:02d}", index * 240
        nodes.append(dict(id=key, type="file", file="StressBenchmark/" + name, x=0, y=y, width=340, height=180))
        text(key + "-current", "GATE: YAML_EQ:status=current", 440, y)
        text(key + "-domain", "GATE: YAML_EQ:domain=dispatch", 880, y)
        text(key + "-slice", "SLICE: SECTION:DispatchInput", 1320, y)
        text(key + "-nonempty", 'GATE: WORDS\n{"min_words":40}', 1740, y)
        connect(key, key + "-current")
        connect(key + "-current", key + "-domain", "true")
        connect(key + "-current", "excluded", "false")
        connect(key + "-domain", "excluded", "false")
        connect(key + "-domain", key + "-slice", "true")
        connect(key + "-slice", key + "-nonempty")
        connect(key + "-nonempty", "selected")
    text("excluded", "JOIN: ANY", 2180, len(names) * 240)
    text("selected", "JOIN: ANY", 2180, 0)
    text("dispatch", "AGENT:\n" + json.dumps({"prompt": INSTRUCTION, "schema": "json", "max_retries": 0}), 2620, 0, 500, 420)
    text("output", "OUTPUT: Checked dispatch candidate", 3220, 0)
    connect("selected", "dispatch")
    connect("dispatch", "output")
    return {"nodes": nodes, "edges": edges}


def prepare():
    FIXTURE.mkdir(parents=True, exist_ok=True)
    notes = build_notes()
    for name, content in notes.items():
        (FIXTURE / name).write_text(content, encoding="utf-8")
    write_json(FIXTURE / "workflow.canvas", build_canvas(notes))
    (FIXTURE / "INDEX.md").write_text(
        "# Contradictory archive stress test\n\n30 notes: 3 current dispatch inputs, 18 contradictory historical revisions, and 9 current departmental notes.\n\n"
        "## Authoritative notes for manual selection\n\n" + "\n".join(f"- [[{name[:-3]}]]" for name in CURRENT)
        + "\n\n[[workflow.canvas|Open the YAML-filtered Canvas]]\n\n[[Results/COMPARISON|Read the measured comparison]]\n\n"
        "The full-context baseline receives the same rule about current dispatch sources as every other variant. "
        "A baseline PASS is a valid result. No outcome is selected or hidden.\n\n"
        "Reproduce: `python -m canvasgate.stress_benchmark`. This makes three real CLI calls per repetition. "
        "Use `--prepare-only` for fixtures only. API transport requires `--transport api --model MODEL` and "
        "OPENAI_API_KEY configured outside the vault. Never put credentials in notes.\n", encoding="utf-8")
    return notes


def make_backend(transport, model, stage, timeout, output_budget):
    if transport == "api":
        return ApiBackend(model, timeout, output_budget, reasoning_effort="medium", event_dir=stage / "events")
    return CodexBackend(model, timeout, reasoning_effort="medium", event_dir=stage / "events")


def run_variant(number, notes, directory, *, transport="cli", model=MODEL, timeout=240, output_budget=2000):
    stage = directory / f"{number:02d}"
    stage.mkdir()
    backend = make_backend(transport, model, stage, timeout, output_budget)
    report, response, error = None, None, None
    context = {name: {"status": True, "confidence": 1, "text": text}
               for name, text in notes.items() if number == 1 or name in CURRENT}
    try:
        if number in (1, 2):
            response = backend.generate(INSTRUCTION, context, [])
        else:
            report = CanvasGateWorkflow(FIXTURE / "workflow.canvas", VAULT).run(backend, max_calls=1, max_context_chars=24000)
            write_json(stage / "workflow-report.json", report)
            node = report["nodes"]["dispatch"]
            response = {key: node[key] for key in ("status", "confidence", "text")}
            if report["outcome"] != "completed":
                error = report["abort_reason"]
        write_json(stage / "response.json", response)
    except WorkflowError as exc:
        error = str(exc)
    runs = backend.runs
    usage = sum_usage([normalize_usage(run.get("usage")) for run in runs]) if runs else None
    raw_usages = [run.get("usage") or {} for run in runs]
    reasoning = [u.get("reasoning_output_tokens", u.get("output_tokens_details", {}).get("reasoning_tokens")) for u in raw_usages]
    result = {"variant": number, "transport": transport, "model": model, "usage": usage,
              "reasoning_tokens": sum(reasoning) if reasoning and all(type(v) is int for v in reasoning) else None,
              "quality": assess(response) if response else {"passed": False}, "execution_error": error,
              "elapsed_seconds": round(sum(run.get("elapsed_seconds", 0) for run in runs), 3), "attempts": len(runs)}
    if report:
        result["passed_slices"] = sum(n["state"] == "EXECUTED" for key, n in report["nodes"].items() if key.endswith("-slice"))
        result["excluded_sources"] = len(notes) - result["passed_slices"]
    write_json(stage / "measurement.json", result)
    return result


def report_results(results, directory, notes, model, transport):
    labels = {1: "Full contradictory packet", 2: "Manually selected Obsidian notes", 3: "CanvasGate YAML gates + slicing"}
    lines = ["# Contradictory archive — measured results", "", f"Model: `{model}`; transport: `{transport}`; reasoning: `medium`.", "",
             f"Corpus: {len(notes)} notes; {sum(len(text) for text in notes.values()):,} source characters. These character counts are not token estimates.", "",
             "| Sample | Variant | Input | Cached input | Output | Reasoning (subset) | Total | Seconds | Oracle |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for sample, rows in enumerate(results, 1):
        for row in rows:
            usage = row["usage"] or {}
            fields = [usage.get(key, "unavailable") for key in ("input_tokens", "cached_input_tokens", "output_tokens")]
            lines.append(f"| {sample} | {labels[row['variant']]} | " + " | ".join(map(str, fields))
                         + f" | {row['reasoning_tokens']} | {usage.get('total_tokens', 'unavailable')} | {row['elapsed_seconds']} | {'PASS' if row['quality']['passed'] else 'FAIL'} |")
    lines += ["", "## Summary", ""]
    for number in (1, 2, 3):
        samples = [rows[number - 1] for rows in results]
        totals = [r["usage"]["total_tokens"] for r in samples if r["usage"] is not None]
        lines.append(f"- Variant {number}: {sum(r['quality']['passed'] for r in samples)}/{len(samples)} PASS; median total {statistics.median(totals) if totals else 'unavailable'}.")
    if all(rows[0]["usage"] and rows[2]["usage"] for rows in results):
        baseline = statistics.mean(rows[0]["usage"]["total_tokens"] for rows in results)
        gated = statistics.mean(rows[2]["usage"]["total_tokens"] for rows in results)
        lines.append(f"- Observed mean token reduction, gated versus full: {100 * (1 - gated / baseline):.2f}%.")
    total = sum(row["usage"]["total_tokens"] for rows in results for row in rows if row["usage"])
    lines += [f"- Reported experiment tokens across all attempts: {total:,}.", "", "## Method and limits", "",
              "- All variants have the identical task and source-authority rule. Same model, medium reasoning, one fresh session and at most one model attempt per sample. All successes and failures are retained.",
              "- The corpus contains six historical fleet/policy/order snapshots with conflicting temperatures, capacities, cancellation states and greedy policies. Nine other departments have current status but the wrong domain. Three authoritative notes are interleaved using a fixed seed.",
              "- Variant 1 gets all notes; variant 2 gets a manually curated three-note packet; variant 3 executes the actual CanvasGate graph, requiring status=current AND domain=dispatch, then extracts DispatchInput sections. Rejected branches are consumed locally and cannot enter the agent context.",
              "- Each excerpt retains the authority fields required by the shared task. A minimum-word gate rejects an empty selected section before any model call. Imported headings are nested beneath DispatchInput.",
              "- The oracle is unchanged from the original benchmark: exact assignments, rejection reasons, loads and revenue. It is not a model judge. Model confidence is not used as a quality score.",
              "- Cached input is already inside input. Reasoning tokens are already inside output. Do not add either subset to total again. Totals do not directly represent money or subscription quota.",
              "- Baseline PASS does not disprove deterministic filtering; baseline FAIL is not guaranteed. Larger excluded context is expected to increase token savings even when both answers are correct.",
              "- With one repetition this is a pilot, not evidence of a reliable failure rate. --repetitions can collect more samples. Sample order is rotated on later repetitions; model output remains stochastic.",
              "- This isolates context filtering with the transport fixed. It does not measure CLI-versus-API overhead. API transport is a separate experiment requiring a configured key and explicit model. No sub-1,500-token claim is made without usage measurements.",
              "- No credential was found for direct API access in the initial environment. The API suite is runnable when OPENAI_API_KEY is configured; it is not silently substituted with a CLI call.",
              "- Raw prompts/events, provider usage, outputs, corpus manifest and full graph traces are retained beside this report. Fixture preparation, this chat and development are excluded from the counters.",
              "", "Official token accounting: https://developers.openai.com/api/docs/guides/token-counting", ""]
    prior_tokens, earlier = 0, []
    for path in sorted((FIXTURE / "Results").glob("*/measurements.json")):
        if path.parent == directory:
            continue
        previous = json.loads(path.read_text(encoding="utf-8"))
        prior_tokens += sum((row.get("usage") or {}).get("total_tokens", 0) for rows in previous for row in rows)
        earlier.append(path.parent.name)
    if earlier:
        lines += ["## Earlier attempts retained", "", f"Earlier run folders: {', '.join(earlier)}.",
                  f"Earlier attempts consumed {prior_tokens:,} reported tokens; all stress-test attempts including this run consumed {prior_tokens + total:,}.",
                  "The initial 20261029T160003Z-7a07214f pilot had a fixture defect: an imported # policy heading terminated the selected ## section. Variant 3 received no dispatch rules and returned status=false. That failed attempt's 13,652 tokens and all other pilot counters remain in its original folder. The corpus was corrected and all three variants rerun; earlier answers were not supplied to models.", ""]
    (directory / "COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")
    (FIXTURE / "Results/COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--transport", choices=["cli", "api"], default="cli")
    parser.add_argument("--model")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--api-output-budget", type=int, default=2000)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10 or args.timeout < 1 or args.api_output_budget < 1:
        parser.error("Invalid repetition, timeout or output budget.")
    if args.transport == "api" and not args.prepare_only:
        if not args.model or not os.environ.get("OPENAI_API_KEY"):
            parser.error("API tests need --model and OPENAI_API_KEY configured locally; no requests made.")
    model = args.model or MODEL
    notes = prepare()
    if args.prepare_only:
        print(FIXTURE / "workflow.canvas")
        return 0
    directory = FIXTURE / "Results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    directory.mkdir(parents=True)
    write_json(directory / "corpus.json", [{"name": name, "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text} for name, text in notes.items()])
    write_json(directory / "configuration.json", {"fixture_revision": 2, "model": model, "transport": args.transport,
               "reasoning": "medium", "instruction": INSTRUCTION, "repetitions": args.repetitions})
    results = []
    for repetition in range(args.repetitions):
        sample = directory / f"sample-{repetition + 1:02d}"
        sample.mkdir()
        rows = []
        order = (1, 2, 3) if repetition % 3 == 0 else ((2, 3, 1) if repetition % 3 == 1 else (3, 1, 2))
        for number in order:
            print(f"Sample {repetition + 1}: starting variant {number} ({args.transport})...", flush=True)
            result = run_variant(number, notes, sample, transport=args.transport, model=model, timeout=args.timeout, output_budget=args.api_output_budget)
            rows.append(result)
            print(json.dumps({"variant": number, "usage": result["usage"], "reasoning_tokens": result["reasoning_tokens"], "passed": result["quality"]["passed"], "error": result["execution_error"]}), flush=True)
        results.append(sorted(rows, key=lambda r: r["variant"]))
        write_json(directory / "measurements.json", results)
    report_results(results, directory, notes, model, args.transport)
    print(f"Report: {directory / 'COMPARISON.md'}", flush=True)
    return 0 if all(row["quality"]["passed"] for rows in results for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
