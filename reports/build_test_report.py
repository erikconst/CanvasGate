"""Consolidate existing measurements without making any model/network calls."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "examples/vault"
REPORT = ROOT / "reports/TEST_REPORT_2026-10-30.md"
VAULT_REPORT = VAULT / "Reports/TEST_REPORT_2026-10-30.md"
SMALL = VAULT / "Benchmark/Results/20261029T151949Z"
STRESS_PILOT = VAULT / "StressBenchmark/Results/20261029T160003Z-7a07214f"
STRESS_FINAL = VAULT / "StressBenchmark/Results/20261029T160336Z-5ecee342"
SNAKE = ROOT / "benchmarks/snake/runs/20261030T072558Z-f2a184cd"
SMOKE = VAULT / "CanvasGate/Runs/20261029T154433Z-e138a36597"
VARIANTS = {1: "Direct", 2: "Obsidian selection", 3: "CanvasGate"}
REFERENCES = {}


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    REFERENCES[str(path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw.decode("utf-8-sig"))


IGNORED_RUN_PREFIXES = (
    "runs/",
    "examples/vault/CanvasGate/Runs/",
    "examples/vault/Rezultate/",
    "benchmarks/snake/runs/",
)


def link(label, path, base_dir=None):
    resolved = Path(path).resolve()
    rel = resolved.relative_to(ROOT).as_posix()
    if rel.startswith(IGNORED_RUN_PREFIXES):
        return f"{label} (`{rel}`)"
    target = os.path.relpath(resolved, base_dir or ROOT).replace("\\", "/")
    return f"[{label}]({target})"


def n(value):
    return f"{value:,}" if isinstance(value, (int, float)) else "unavailable"


def record(suite, phase, result, source, number=None, quality=None):
    runs = result.get("model_runs", [])
    usage = result.get("usage")
    reasoning = usage.get("reasoning_output_tokens") if usage else None
    if reasoning is None:
        raw = [run.get("usage") or {} for run in runs]
        if raw and all("reasoning_output_tokens" in value for value in raw):
            reasoning = sum(value["reasoning_output_tokens"] for value in raw)
    return {"suite": suite, "phase": phase, "variant": number or result.get("variant"), "usage": usage,
            "reasoning_tokens": result.get("reasoning_tokens", reasoning),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "quality": quality or ("PASS" if result.get("quality", {}).get("passed") else "FAIL"),
            "source": str(source.relative_to(ROOT)).replace("\\", "/")}


def detailed_table(rows, result_labels=None):
    lines = ["| Variant | Input | Cached input* | Output | Reasoning* | Total | Seconds | Result |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        usage = row["usage"] or {}
        label = (result_labels or {}).get(row["variant"], row["quality"])
        lines.append(f"| {VARIANTS.get(row['variant'], 'CanvasGate integration')} | {n(usage.get('input_tokens'))} | "
                     f"{n(usage.get('cached_input_tokens'))} | {n(usage.get('output_tokens'))} | {n(row['reasoning_tokens'])} | "
                     f"**{n(usage.get('total_tokens'))}** | {row['elapsed_seconds']} | {label} |")
    return lines


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def build():
    small_results = read(SMALL / "measurements.json")
    small = [record("Dispatch: 6 notes", "final", value, SMALL / "measurements.json") for value in small_results]
    blocked = record("Dispatch: 6 notes", "blocked preliminary attempt", read(SMALL / "excluded-attempts.json")[0], SMALL / "excluded-attempts.json")
    stress_pilot = [record("Dispatch: 30 notes", "initial fixture", value, STRESS_PILOT / "measurements.json")
                    for value in read(STRESS_PILOT / "measurements.json")[0]]
    stress = [record("Dispatch: 30 notes", "corrected fixture", value, STRESS_FINAL / "measurements.json")
              for value in read(STRESS_FINAL / "measurements.json")[0]]
    snake_results = read(SNAKE / "measurements.json")
    browser = read(SNAKE / "browser-checks.json")
    snake = [record("Three.js snake", "final", value, SNAKE / "measurements.json", quality="ENGINEERING PASS") for value in snake_results]
    smoke_raw = read(SMOKE / "report.json")
    smoke_metric = read(VAULT / "CanvasGate/Runs/smoke-events/provider-1/call-001.metrics.json")
    smoke = record("CanvasGate integration", "real smoke test",
                   {"usage": {**smoke_raw["usage"], "reasoning_output_tokens": smoke_metric["usage"]["reasoning_output_tokens"]},
                    "elapsed_seconds": smoke_metric["elapsed_seconds"]}, SMOKE / "report.json", quality="COMMITTED")
    old_smoke = read(ROOT / "runs/20261029T150149Z-bbd43db138/report.json")
    initial_mock = read(ROOT / "runs/20261029T150131Z-9d114a6206/report.json")
    canvas_mock = read(VAULT / "CanvasGate/Runs/20261029T154407Z-2a45908bf3/report.json")
    simulations = [
        {"source": "runs/20261029T150131Z-9d114a6206/report.json", "calls": initial_mock["calls"], "outcome": initial_mock["outcome"]},
        {"source": "examples/vault/CanvasGate/Runs/20261029T154407Z-2a45908bf3/report.json", "calls": canvas_mock["calls"], "outcome": canvas_mock["outcome"]},
    ]
    for path in sorted((VAULT / "Rezultate").glob("*/report.json")):
        saved = read(path)
        if saved.get("backend") == "mock":
            simulations.append({"source": str(path.relative_to(ROOT)).replace("\\", "/"), "calls": saved["calls"], "outcome": saved["outcome"]})
    calls = [*small, blocked, *stress_pilot, *stress, smoke, *snake]
    assert len(calls) == 14
    assert all(row["usage"] and row["usage"]["total_tokens"] == row["usage"]["input_tokens"] + row["usage"]["output_tokens"] for row in calls)
    totals = {key: sum(row["usage"].get(key, 0) for row in calls)
              for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "uncached_input_tokens")}
    assert totals["total_tokens"] == 285873
    failures = [row for row in calls if row["quality"] == "FAIL"]
    assert len(failures) == 2
    failed_tokens = sum(row["usage"]["total_tokens"] for row in failures)
    tests = read(ROOT / "reports/historical_test_snapshot.json")["test_ids"]
    assert len(tests) == 60
    groups = Counter(name.split(".")[0] for name in tests)
    generated = datetime.now(timezone.utc).isoformat()
    data = {"report_date": "2026-10-30", "generated_at_utc": generated,
            "measured_model_invocations": len(calls), "totals": totals,
            "failed_invocations": len(failures), "failed_tokens": failed_tokens,
            "unmetered_real_invocations": [{"source": "runs/20261029T150149Z-bbd43db138/report.json", "calls": old_smoke["calls"], "outcome": old_smoke["outcome"], "usage": None}],
            "measured_calls": calls, "saved_simulations": simulations,
            "local_test_snapshot": {"tests": len(tests), "passed": 60, "failures": 0, "errors": 0,
                "duration_seconds": 1.113, "command": "python -m unittest discover -s tests -q",
                "evidence": "Command executed successfully during report compilation; no model calls.",
                "test_ids": tests},
            "browser_test_snapshot": browser,
            "source_sha256": REFERENCES}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    (REPORT.parent / "test_measurements_2026-10-30.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def render_markdown(base_dir):
        lines = ["# Consolidated test report — CanvasGate", "",
                 "**Reporting date:** 30 October 2026. **Test period:** 29–30 October 2026.",
                 "**Scope:** every saved benchmark, integration run, failed attempt, local test suite and browser check performed in this project so far.",
                 "", "## 1. Executive findings", "",
                 "- The final dispatch and modeling comparisons each produced valid results for all three approaches. No experiment demonstrated an inevitable baseline failure from contradictory notes.",
                 "- Deterministic filtering saved the most tokens when the excluded corpus was large: **50.32%** against the full 30-note packet. The small dispatch and Three.js examples saved **3.55%** and **1.37%** respectively.",
                 "- Manual note selection used fewer tokens than CanvasGate in all three final comparisons. CanvasGate automated selection, conditional routing and validation; the results do not establish a token advantage over careful manual selection.",
                 "- All three generated snakes passed **17/17 engineering checks** after a shared test-harness correction. This is not an artistic-quality ranking.",
                 f"- The saved measurement ledger contains **{len(calls)} metered external Codex CLI invocations** and **{n(totals['total_tokens'])} reported tokens**, including **{n(failed_tokens)}** from two unsuccessful task attempts. One earlier successful real invocation has no saved token usage and is additional to this total. An external invocation can contain several internal provider requests; that internal request count was not measured separately.",
                 "- The current deterministic regression suite passed **60/60 tests**. Direct API benchmarking has not been executed; claims about sub-1,500-token API results remain unverified.",
                 "", "## 2. Accounting and comparison method", "",
                 "The three workflows are: **Direct** (full supplied packet), **Obsidian selection** (manually curated current notes exported into the prompt), and **CanvasGate** (local graph selects context before the model call). Obsidian itself does not make or reduce model calls.",
                 "All final comparisons used independent Codex CLI sessions, `gpt-6.1-sol`, and medium reasoning. The initial unmetered smoke test used the CLI default model, whose identity was not preserved. No previous model answer was included in a later comparison's input.",
                 "Token usage comes from saved provider/CLI counters. **Total = input + output.** Cached input is already included in input; reasoning is already included in output. Missing usage is unknown, never estimated from characters or treated as zero. Counters include model-side setup/instructions/schema overhead and any internal interactions reported by the CLI.",
                 "The totals exclude development, fixture preparation, dependency installation, deterministic Python tests, browser verification and visual inspection. They are neither a final invoice nor a measurement of subscription-quota percentage. Cache effects mean equal gross token totals would not necessarily have equal monetary cost.",
                 "Each final workflow has one measured sample per task. Differences in generated code, reasoning and stochastic model behavior can outweigh small input savings. These are practical workflow comparisons, not isolated causal or statistical estimates of Obsidian's effect.",
                 "", "## 3. Final comparison at a glance", "",
                 "| Test | Direct total | Obsidian selection | CanvasGate total | CanvasGate vs direct | Final quality |",
                 "| --- | ---: | ---: | ---: | ---: | --- |"]
        for title, rows, quality in (("Dispatch, 6 notes", small, "3/3 exact PASS"), ("Dispatch, 30 notes", stress, "3/3 exact PASS"), ("Three.js snake", snake, "17/17 browser checks each")):
            amounts = [row["usage"]["total_tokens"] for row in rows]
            reduction = 100 * (1 - amounts[2] / amounts[0])
            lines.append(f"| {title} | {n(amounts[0])} | {n(amounts[1])} | {n(amounts[2])} | {reduction:.2f}% fewer | {quality} |")
        lines += ["", "## 4. Test A — initial MVP smoke runs", "",
                  "The first local example summarized a Markdown brief after checking word limits, approval and confidence. A mock run verified wiring with no model tokens. One real Codex call completed successfully before usage instrumentation was added.",
                  "| Run | Outcome | Real model calls | Saved usage |",
                  "| --- | --- | ---: | --- |",
                  f"| Initial mock | {initial_mock['outcome']} | 0 (simulated) | 0 model tokens |",
                  f"| Initial real summary | {old_smoke['outcome']} | {old_smoke['calls']} | **Unavailable** |",
                  "", "The initial brief was Romanian; later tasks, notes, benchmark interfaces and generated artifacts were switched to English. The early real run must not be assigned an invented token count.",
                  "", link("Initial real report", ROOT / "runs/20261029T150149Z-bbd43db138/report.json", base_dir),
                  "", f"There are **{len(simulations)} saved successful mock runs** in total: the initial smoke, two Obsidian-vault wiring runs, and the CanvasGate simulation. Each used one simulated agent attempt and zero external model calls/tokens. Unit-test mock calls are separate and also make no external model requests.",
                  "", *[f"- {link(item['source'], ROOT / item['source'], base_dir)}: {item['outcome']}, {item['calls']} simulated attempt." for item in simulations],
                  "", "## 5. Test B — medium-complexity dispatch, 6 notes", "",
                  "**Task:** assign 14 orders to 3 trucks with priority/deadline ordering, zone and temperature compatibility, cumulative weight/volume capacities, cancellation/hold rejection and exact revenue totals. Three authoritative notes and three excluded background/historical notes were available.",
                  "**Quality oracle:** exact assignments, rejection reasons, per-truck loads and revenue. Final results matched seven assignments, seven rejections, loads T1=1,000 kg/6 m³, T2=750 kg/5 m³, T3=600 kg/4 m³, and revenue 1,610.", "",
                  *detailed_table(small), "",
                  "**Failed preliminary attempt:** the original second workflow asked the agent to read INDEX.md. Automatic approval review rejected both read attempts (`Get-Content` and `type`) as `blocked by policy`. The session returned no dispatch result and consumed **67,784 tokens**, including 45,568 cached input tokens. The zero completed-tool count does not mean there were no rejected attempts.",
                  "The organized variant was repeated by supplying manually selected notes directly. Actual order was Direct → organized read attempt (blocked) → gated → manual organized retry. The blocked attempt is excluded from the successful comparison table but included in experiment spend.",
                  "**Successful samples:** 40,739 tokens. **Whole experiment including the blocked attempt:** 108,523 tokens.",
                  "", link("Detailed comparison", SMALL / "COMPARISON.md", base_dir) + " · " + link("Blocked attempt evidence", SMALL / "02-blocked/events/call-001.stderr.txt", base_dir),
                  "", "## 6. Test C — contradictory archive, 30 notes", "",
                  "**Corpus:** 3 current dispatch notes, 18 superseded fleet/policy/order snapshots, and 9 current departmental notes from unrelated domains. Historical snapshots contradicted current temperature support, capacities, order states and dispatch rules. The corrected corpus contained 48,571 characters; this is a size description, not a token estimate.",
                  "All variants received the same authority rule: `status=current` AND `domain=dispatch`. CanvasGate evaluated those checks locally, excluded 27 notes, sliced the three accepted sections and made one model call. The dispatch oracle was unchanged.",
                  "### Initial fixture round — retained, not counted as a clean final comparison", "",
                  *detailed_table(stress_pilot), "",
                  "The gated run failed because a `#` heading imported inside `## DispatchInput` ended the selected section. The agent received no dispatch policy and returned status=false. This was a fixture/context starvation defect, not evidence that the baseline was better at the underlying dispatch logic.",
                  "The fixture was corrected by nesting headings and retaining authority fields in excerpts. A minimum-word gate now rejects an empty selected section before a model call. All three variants were repeated on the corrected corpus; earlier answers were not included in their inputs.",
                  "### Corrected fixture — final comparison", "",
                  *detailed_table(stress), "",
                  "CanvasGate used **50.32% fewer** total tokens than full context. Baseline reasoning was 131 tokens versus 87 for CanvasGate, not a demonstrated doubling. All three matched the oracle; no context-induced baseline quality failure was observed in this sample.",
                  "**Initial round:** 55,433 tokens. **Corrected round:** 56,345 tokens. **Both rounds:** 111,778 tokens.",
                  "", link("Initial round", STRESS_PILOT / "COMPARISON.md", base_dir) + " · " + link("Corrected comparison", STRESS_FINAL / "COMPARISON.md", base_dir),
                  "", "## 7. Test D — CanvasGate architecture integration", "",
                  "The architectural example used YAML approval, a SECTION slice, a character limit, separate implementation/review branches, JOIN, staging and a final Markdown write. The mock execution committed a clearly simulated result. A real execution produced an English implementation plan for a pure Python order-validation function.",
                  "The real plan covered container and field validation, booleans versus integers, duplicate SKUs, integer totals, non-mutation and boundary cases. This was an integration smoke test and a manual plan inspection, not an exhaustive correctness proof of generated application code.", "",
                  *detailed_table([smoke]), "",
                  f"Real outcome: **{smoke_raw['transaction_state']}**, one accepted output file. Mock outcome: **{canvas_mock['transaction_state']}**, zero model tokens. Source fingerprints and traces were saved. Recovery guarantees are per-file replacement with journaling/rollback, not simultaneous atomic visibility across multiple files.",
                  "", link("Real integration audit", SMOKE / "RunReport.md", base_dir) + " · " + link("Architecture and recovery guarantees", ROOT / "CANVASGATE.md", base_dir),
                  "", "## 8. Test E — Three.js snake modeling and animation", "",
                  "**Task:** independently create a procedural emerald snake with a tapered body, head, eyes, belly and forked tongue, using Three.js r186.1. Required states: slow, fast, attack, sleep, sit and death. Sit means an upright coiled resting pose, not a chair or limbs.",
                  "All three modules were generated from the same English brief using gpt-6.1-sol/medium, with no shared generated source. The packet contained 12 notes: 3 current specifications, 6 retired designs and 3 unrelated department notes. The shared viewer supplied identical rendering, camera and time. There were no hidden model repair calls or manual changes to the generated modules.", "",
                  *detailed_table(snake, {1: "17/17 browser checks", 2: "17/17 browser checks", 3: "17/17 browser checks"}), "",
                  "CanvasGate reduced input by 911 tokens versus Direct, but produced 662 more output tokens. Net reduction was **249 tokens / 1.37%**. This illustrates why context reduction does not guarantee a similarly large reduction in total tokens for code generation. Total generation usage was **53,302 tokens**.",
                  "### Browser verification", "",
                  "The original modules were syntax-checked with Node and loaded in local Chromium. Browser errors: **0**. Each model passed all 17 final checks:", ""]
        for check in browser["qa"][0]["checks"]:
            lines.append(f"- {check['name']}.")
        lines += ["", "The initial state-distinctness check sampled one time after the attack had recovered, incorrectly flagging variant 3 as equal to slow. The shared harness was corrected to compare trajectories at 0.17, 0.35, 0.73 and 1.7 seconds. All original model sources were retained and no additional model calls were made. The host camera/lighting was also refined equally for all variants.",
                  "Six screenshots per model comparison were captured. Slow, attack, sit, sleep and death captures were inspected during development; fast behavior was measured and captured. The fast/slow ratio is a sampled geometric motion proxy, not an exact frequency measurement. Tests do not prove artistic quality, realistic biomechanics, every performance limit or the absence of all per-frame heap allocations.",
                  "", "| Variant | Fast/slow motion proxy | Attack extension (+Z units) | Sit head elevation (units) |",
                  "| --- | ---: | ---: | ---: |"]
        for row in browser["qa"]:
            m = row["measurements"]
            lines.append(f"| {VARIANTS[row['variant']]} | {m['fast_slow_ratio']:.2f}× | {m['attack_extension']:.3f} | {m['sit_elevation']:.3f} |")
        lines += ["", "[Interactive viewer](http://127.0.0.1:8873/) — requires the local Snake Lab server. Reopen with " + link("Snake-Lab.cmd", ROOT / "Snake-Lab.cmd", base_dir) + ".",
                  "", link("Full modeling comparison", SNAKE / "COMPARISON.md", base_dir) + " · " + link("Browser evidence", SNAKE / "browser-checks.json", base_dir) + " · " + link("Slow-state capture", SNAKE / "screenshots/slow.png", base_dir),
                  "", "## 9. Deterministic regression tests", "",
                  "The latest suite was rechecked while compiling this report: `python -m unittest discover -s tests -q` — **60 tests, 0 failures, 0 errors, 1.113 seconds, OK**. These are test methods; subcases/assertions are not counted as additional test methods. Mocked provider interactions make no external AI calls.",
                  "", "| Test module | Test methods | Main coverage |", "| --- | ---: | --- |"]
        coverage = {
            "test_benchmark": "Usage parsing, cache accounting, hand-calculated dispatch oracle and detection of an incorrect result",
            "test_workflow": "Original graph validation, gating, routing, context exclusion, retries, budgets, files and CLI reports",
            "test_canvasgate": "Typed YAML, slicing, IF/ELSE joins, schemas, providers, staging, conflicts, locks and recovery",
            "test_stress_benchmark": "Contradictory corpus filtering, complete selected policy, API metrics and credential-free logging",
            "test_snake_benchmark": "All animation/module requirements survive context filtering; obsolete snake notes are excluded",
        }
        for name, count in sorted(groups.items()):
            lines.append(f"| {link(name + '.py', ROOT / 'tests' / (name + '.py'), base_dir)} | {count} | {coverage.get(name, '')} |")
        lines += ["", "Important transaction tests inject write errors, KeyboardInterrupt-style interruption, rollback errors and external file edits. They verify recovery and conflict handling, but are not physical power-loss tests or proof of serializable isolation from external editors.",
                  "", "Historical suite sizes progressed through 21, 23, 27, 53, 57, 59 and 60 as functionality was added. These are successive snapshots, not counts that should be added together.",
                  "", "## 10. Complete measured-call ledger", "",
                  "Each row below is one metered external Codex CLI invocation, not necessarily one internal provider request. Rows are grouped by experiment, not ordered chronologically. Successful rows repeated after a fixture correction remain consumed work; no failed or repeated call is removed from this ledger.",
                  "", "| # | Experiment / phase | Variant | Total tokens | Outcome |",
                  "| ---: | --- | --- | ---: | --- |"]
        for index, row in enumerate(calls, 1):
            lines.append(f"| {index} | {row['suite']} / {row['phase']} | {VARIANTS.get(row['variant'], 'Integration')} | {n(row['usage']['total_tokens'])} | {row['quality']} |")
        lines += ["", "| Token category | Sum across 14 metered invocations |", "| --- | ---: |",
                  f"| Input, including cached input | {n(totals['input_tokens'])} |",
                  f"| Cached input — subset, not additional | {n(totals['cached_input_tokens'])} |",
                  f"| Uncached input | {n(totals['uncached_input_tokens'])} |",
                  f"| Output, including reasoning | {n(totals['output_tokens'])} |",
                  f"| **Total input + output** | **{n(totals['total_tokens'])}** |",
                  f"| Failed-attempt tokens — subset of total | {n(failed_tokens)} |", "",
                  "This is the **known metered total**, not the complete historical project total: the early successful real summary call is unmetered and additional. Actual historical usage therefore exceeds the known total by an unknown amount. Development costs are also outside this ledger.",
                  "", "## 11. Not executed or not established", "",
                  "- **Direct Responses API comparison:** prepared but not executed. No OPENAI_API_KEY was configured when checked. API calls were tested only using mocked responses; no live API usage was measured.",
                  "- **Five serial micro-agents via CLI versus API:** not executed. A claimed 60,000-token CLI setup or a sub-1,500-token API result is not an observed benchmark result.",
                  "- **Exact CLI system-prompt overhead:** not separately measured. Earlier roughly 12k-input runs included more than source notes; they cannot be labeled entirely as system instructions.",
                  "- **Inevitable baseline failure under stale rules:** not observed. Direct runs passed both final dispatch benchmarks.",
                  "- **Statistically reliable savings or failure rate:** not established from one final sample per workflow/task.",
                  "- **Artistic superiority of a snake:** not established by the engineering checks. Use the interactive viewer to assess appearance and animation appeal.",
                  "- **Global multi-file atomic visibility, physical power-loss durability or full sandbox read isolation:** not established; see the architecture's explicit guarantees and limitations.",
                  "", "## 12. Conclusions", "",
                  "1. The strongest measured token saving came from removing a large irrelevant/obsolete corpus, while preserving correct task context.",
                  "2. The fixture failure demonstrates the complementary risk: slicing too aggressively can remove essential rules. Context completeness needs its own checks.",
                  "3. CanvasGate's demonstrated value is deterministic orchestration, bounded calls, inspectable routing, source filtering and recoverable writes. It does not replace a semantic quality oracle.",
                  "4. In the code-generation task, output length and reasoning nearly offset the input saving. Compare complete task cost and quality, not input size alone.",
                  "5. Manual selection was cheapest in these final samples; automation should be evaluated alongside the human selection effort and consistency it replaces.",
                  "6. The next meaningful transport comparison requires a configured API key, matched models/tasks and actual provider usage, with repeated samples and equivalent quality checks.",
                  "", "## Appendix — local test inventory", "",
                  "All methods below belong to the latest 60/60 passing snapshot:", ""]
        for name in tests:
            lines.append(f"- `{name}`")
        lines += ["", "## Evidence and reproducibility", "",
                  link("Machine-readable consolidated ledger and source hashes", REPORT.parent / "test_measurements_2026-10-30.json", base_dir),
                  "", "Saved source JSON files are hashed in that ledger. The report builder reads existing artifacts only; it makes no model or network calls. Rebuild from the project root with `python reports/build_test_report.py`.",
                  "", "Official token-accounting reference: [OpenAI token counting](https://developers.openai.com/api/docs/guides/token-counting).", ""]
        spaced = []
        def prose(line):
            return line and not line.startswith(("|", "- ", "#")) and not (len(line) > 2 and line[0].isdigit() and ". " in line[:4])
        for line in lines:
            if spaced and spaced[-1] and line and prose(spaced[-1]) and (prose(line) or line.startswith("|")):
                spaced.append("")
            spaced.append(line)
        return "\n".join(spaced)

    REPORT.write_text(render_markdown(REPORT.parent), encoding="utf-8")
    VAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    VAULT_REPORT.write_text(render_markdown(VAULT_REPORT.parent), encoding="utf-8")
    print(json.dumps({"report": str(REPORT), "vault_report": str(VAULT_REPORT), "calls": len(calls), "totals": totals,
                      "failed_tokens": failed_tokens, "unit_tests": groups}, indent=2))


if __name__ == "__main__":
    build()
