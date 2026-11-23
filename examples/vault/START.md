# CanvasGate — start here

This vault is the visual interface for **Obsidian → local gates → Codex**.
All example tasks and benchmark notes are in English.

**CanvasGate Studio:** open `CanvasGate-Studio.cmd` in the project folder for the local graphical web app.
See [[Studio/Guide|Studio guide]] for contracts, snapshots, replay and recovery.

[[Reports/TEST_REPORT_2026-10-30|Read the consolidated report of all tests, measurements and failed attempts]].

## Open a workflow

- [[CanvasGate/Guide|CanvasGate architecture — start here]] — slicing, conditional routing, JOIN and recoverable writes.
- [[CanvasGate/workflow.canvas|CanvasGate workflow]] — English API planning with approval and review branches.
- [[workflow.canvas|Simple summary workflow]] — learn how the gates work.
- [[brief|Prototype brief]] — the source text for the simple workflow.
- [[Benchmark/INDEX|Medium-complexity English benchmark]] — dispatch 14 orders across 3 vehicles.
- [[Benchmark/workflow.canvas|Benchmark Canvas]] — current-source checks and exclusion gates.
- [[Benchmark/Results/COMPARISON|Measured token comparison]] — real usage and exact-answer checks.
- [[StressBenchmark/INDEX|Contradictory archive stress test]] — 30 notes, YAML filtering and unchanged quality checks.
- [[SnakeBenchmark/INDEX|Three.js snake modeling benchmark]] — three procedural models and six animation states.

## Run the simple example

1. Edit the brief and save (`Ctrl+S`).
2. Double-click **Simuleaza.cmd** in the project folder for a mock run with no tokens.
3. Open the newest `results.md` under `Rezultate/` in this vault.
4. Double-click **Ruleaza-Codex.cmd** for a real run, limited to three attempts in total.

The mock returns a fixed demonstration response; it does not actually summarize your brief.
Set the `permission` node's status to `false` and save to block the model call entirely.

## How token savings work

Obsidian organizes notes locally. Python evaluates gates without AI and passes only accepted
context to Codex. The whole vault and previous conversations are not automatically included.
Use short `TEXT:` excerpts instead of complete file notes when only a paragraph is relevant.
Opening Obsidian itself does not reduce tokens: context selection and avoided agent interactions do.

The Canvas editor does not start execution automatically. Run the launchers or CLI.
Feedback cycles are rejected; configure `max_retries` inside a CODEX node instead.
Connected Markdown notes are read in full, including frontmatter. Source notes are not rewritten.

## Reproduce the benchmark

From the project folder, run `python -m canvasgate.benchmark`.
This makes three real Codex calls and consumes account quota. It writes raw usage events,
prompts, model responses and a comparison under `Benchmark/Results/`.
Each successful result is checked against the same local exact-answer oracle.

Codex CLI uses a temporary directory and a read-only sandbox, but these do not guarantee that
all disk reads are impossible. An API backend without tools is also available; see the project README.
