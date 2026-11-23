"""Check the generated modules in a real local Chromium browser and capture six states."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from .benchmark import write_json
from .snake_benchmark import FIXTURE, OUTPUT, STATES


def write_report(directory, manifest, qa, browser_errors):
    rows = {result["variant"]: result for result in qa}
    labels = {1: "Codex direct — complete packet", 2: "Obsidian — selected notes", 3: "CanvasGate + Obsidian — gated slices"}
    lines = ["# Three.js snake comparison", "", f"Run: `{manifest['run']}`. Three.js r186. Same English brief, model gpt-6.1-sol and medium reasoning.", "",
             "Required animations: slow, fast, attack, sleep, sit (upright coiled rest), death.", "",
             "| Variant | Input | Cached input | Output | Total | Generation seconds | Browser checks |",
             "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for metric in manifest["models"]:
        usage = metric["usage"] or {}
        result = rows[metric["variant"]]
        values = [str(usage.get(key, "unavailable")) for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")]
        lines.append(f"| {labels[metric['variant']]} | " + " | ".join(values) + f" | {metric['elapsed_seconds']} | {result['passed_count']}/{result['check_count']} |")
    totals = [(m.get("usage") or {}).get("total_tokens") for m in manifest["models"]]
    if all(type(value) is int for value in totals):
        lines += ["", f"CanvasGate versus direct: {100*(1-totals[2]/totals[0]):.2f}% fewer total tokens (negative means more).",
                  f"Total reported generation tokens: {sum(totals):,}."]
    lines += ["", "## Scope", "",
              "- Three independently generated source modules. They share only the host renderer, lighting, camera, time and test harness.",
              "- Variant 1 received all 12 notes; variant 2 received three manually selected current notes; variant 3 used the actual CanvasGate YAML gates and section slicer to select the three current snake3d notes.",
              "- All model outputs, exact prompts, real CLI usage events and measurements are retained. One generation invocation per variant; no hidden model repairs or manual source fixes are included.",
              "- The browser checks measure module integration, deterministic poses, resource stability and selected animation properties. They do not prove artistic quality, exact temporal frequency, realistic biomechanics, all performance limits or full absence of per-frame heap allocations.",
              "- Fast/slow activity is a sampled world/geometry motion proxy, not a direct frequency measurement. Named head positions are used for attack/sit checks.",
              "- State distinctness compares trajectories at t=0.17, 0.35, 0.73 and 1.7, including the attack peak. An earlier single-instant check falsely flagged a recovered attack as equal to slow; the harness was corrected for all three original modules, without model edits or additional model calls.",
              "- One sample per approach is not a reliability estimate. Context packaging can influence model implementation choices and output lengths.",
              "- Total = input + output; cached input is a subset of input. Output includes generated JavaScript and reasoning. Development, this chat, dependency setup and deterministic verification are excluded.",
              "", "## Browser checks", ""]
    for metric in manifest["models"]:
        result = rows[metric["variant"]]
        lines += [f"### {labels[metric['variant']]}", ""]
        for check in result["checks"]:
            lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} — {check['name']}" + (f": {check['detail']}" if check.get('detail') else ""))
        lines += ["", "Measurements:", "", "```json", json.dumps(result.get("measurements", {}), indent=2), "```", ""]
    lines += ["## Browser errors", "", "```json", json.dumps(browser_errors, indent=2), "```", "",
              "## Visual captures", "", *[f"- screenshots/{state}.png" for state in STATES], "",
              "The host opens at http://127.0.0.1:8873/ when python -m canvasgate.snake_preview is running.", ""]
    (directory / "COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")
    (FIXTURE / "Results.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8873/")
    args = parser.parse_args()
    manifest = json.loads((OUTPUT / "latest.json").read_text(encoding="utf-8"))
    directory = OUTPUT / "runs" / manifest["run"]
    static = []
    node = shutil.which("node")
    for metric in manifest["models"]:
        source = directory / f"{metric['variant']:02d}/snake.mjs"
        if not source.is_file():
            static.append({"variant": metric["variant"], "syntax_ok": False, "reason": "No source generated"})
            continue
        result = subprocess.run([node, "--check", str(source)], capture_output=True, text=True, check=False)
        code = source.read_text(encoding="utf-8")
        forbidden = re.findall(r"\b(?:fetch|XMLHttpRequest|WebSocket|eval|setTimeout|setInterval)\s*\(|\bMath\.random\s*\(|\bimport\s*(?:\(|[^\s])", code)
        static.append({"variant": metric["variant"], "syntax_ok": result.returncode == 0,
                       "syntax_error": result.stderr, "forbidden_patterns": forbidden})
    write_json(directory / "static-checks.json", static)
    if any(result.get("forbidden_patterns") for result in static):
        raise SystemExit("Review the flagged source patterns before browser execution.")
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1540, "height": 1120}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle", timeout=60000)
        page.wait_for_function("window.snakeLab?.ready === true", timeout=60000)
        errors.extend(page.evaluate("window.snakeLab.errors"))
        page.evaluate("window.snakeLab.setPlaying(false)")
        qa = page.evaluate("window.snakeLab.testModels()")
        for metric in manifest["models"]:
            if not any(row["variant"] == metric["variant"] for row in qa):
                qa.append({"variant": metric["variant"], "passed": False, "passed_count": 0, "check_count": 1,
                           "checks": [{"name": "Model loaded", "passed": False, "detail": str(metric.get("generation_error") or errors)}], "measurements": {}})
        qa.sort(key=lambda row: row["variant"])
        manifest["qa"] = qa
        write_json(OUTPUT / "latest.json", manifest)
        page.reload(wait_until="networkidle")
        page.wait_for_function("window.snakeLab?.ready === true")
        page.evaluate("window.snakeLab.setPlaying(false)")
        captures = directory / "screenshots"
        captures.mkdir(exist_ok=True)
        for state in STATES:
            moment = 0.35 if state == "attack" else (2.0 if state == "death" else 0.73)
            page.evaluate("([state,time])=>{window.snakeLab.setState(state);window.snakeLab.setTime(time);}", [state, moment])
            page.screenshot(path=str(captures / f"{state}.png"), full_page=True)
        errors.extend(page.evaluate("window.snakeLab.errors"))
        browser.close()
    write_json(directory / "browser-checks.json", {"qa": qa, "errors": errors})
    write_report(directory, manifest, qa, errors)
    for row in qa:
        print(f"Variant {row['variant']}: {row['passed_count']}/{row['check_count']} checks", flush=True)
        for check in row["checks"]:
            if not check["passed"]:
                print(f"  FAIL: {check['name']} {check.get('detail', '')}", flush=True)
    print(f"Report: {directory / 'COMPARISON.md'}", flush=True)
    return 0 if all(row["passed"] for row in qa) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
