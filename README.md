# CanvasGate

**Deterministic Obsidian Canvas workflows, explicit context contracts, isolated model calls, and offline replay.**

**CanvasGate Studio 0.4** installs as a native Windows desktop app via `CanvasGate-Studio-Setup.exe` (from GitHub Releases or built locally via [desktop/README.md](desktop/README.md)).
Open **CanvasGate Studio** from the Desktop or Start menu and use the **Agents** tab to connect **Codex**, **Antigravity**, and **Claude Code** via MCP.
[MCP User Guide](canvasgate/MCP_USER_GUIDE.md) · [MCP Agent Guide](canvasgate/MCP_AGENT_GUIDE.md).

`CanvasGate-Studio.cmd` remains available as the local browser development launcher.
The graphical editor supports context contracts, immutable snapshots, offline replay, resume/reconciliation, and per-node decision inspection. By default, runs use the local `mock` backend with zero tokens and target writes disabled.

- Studio guide: [STUDIO.md](STUDIO.md) · Studio verification: [STUDIO_VERIFICATION_2026-10-30.md](reports/STUDIO_VERIFICATION_2026-10-30.md)
- Consolidated benchmark & test report: [TEST_REPORT_2026-10-30.md](reports/TEST_REPORT_2026-10-30.md)

Local execution pipeline: **Obsidian Canvas → deterministic Python gates → isolated model call → validation → recoverable writes**.
Requires Python 3.11+ (`PyYAML` and `jsonschema`); no Obsidian community plugin is needed.

## CanvasGate Architecture

- **3D benchmark:** `examples/vault/SnakeBenchmark/` and `benchmarks/snake/`. Open `Snake-Lab.cmd` for the interactive comparison of three procedural snakes across six animation states. Details: [benchmarks/snake/README.md](benchmarks/snake/README.md).
- **CanvasGate engine:** `INPUT`, `SLICE` (`SECTION`/`YAML`/`LINES`), `GATE` (`YAML_EQ`/`JSON_KEYS`/`LEN_LT`/`REGEX`/`AND`/`OR`/`NOT`), `AGENT`, labeled `true`/`false`/switch edges, `JOIN`, in-memory staging, commit journaling, and crash recovery. Full specification and limits: [CANVASGATE.md](CANVASGATE.md).

```powershell
python -m pip install -e .
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --backend mock --output-dir examples/vault/CanvasGate/Runs
```

In Obsidian, open `CanvasGate/Guide.md`. Convenience launchers: `CanvasGate-Simulate.cmd` and `CanvasGate-Run.cmd`.
Legacy v0.1 graphs remain compatible.

## Using with Obsidian

Open `examples/vault` as an existing Obsidian vault and start with `START.md`.
From the project root, you can run `Simuleaza.cmd` (mock, zero tokens) or `Ruleaza-Codex.cmd` (live Codex CLI, max 3 calls). Reports are written under `examples/vault/Rezultate/`, viewable directly inside Obsidian.

## Quick Start (Zero Tokens)

```powershell
python -m canvasgate examples/vault/workflow.canvas --dry-run
python -m canvasgate examples/vault/workflow.canvas
```

- `--dry-run` validates the graph and prints the topological execution plan without reading note contents or calling any model.
- Running without `--backend` executes the workflow with the `mock` backend (no network calls) and writes `report.json` and `results.md` into a unique subfolder under `runs/`. `OUTPUT` node names are report section titles, not file paths.

Open `examples/vault/workflow.canvas` in Obsidian, change `status` in the `permission` node to `false`, save, and run again: the model node is blocked with **zero calls**.

## Live Execution via Codex CLI

Install a recent Codex CLI release and authenticate with `codex login`:

```powershell
python -m canvasgate examples/vault/workflow.canvas --backend codex --max-calls 3
```

Specify `--model MODEL_NAME` if desired; otherwise the CLI default model is used.
The adapter starts an isolated subprocess using stdin, `--ephemeral`, `--output-schema`, `read-only` sandbox, a separate temporary directory, no user config, no project docs, no web search, and `features.shell_tool=false`.

**Isolation note:** a temporary directory and `read-only` mode are not a hard OS-level read-isolation boundary. To guarantee the executor receives only serialized context, use the tool-free `api` backend or run the CLI inside a container/VM.

## Live Execution via OpenAI Responses API (No Tools)

Set `OPENAI_API_KEY` in the process environment (never inside Canvas files or the repository) and choose a Structured Outputs-compatible model:

```powershell
python -m canvasgate examples/vault/workflow.canvas --backend api --model MODEL_NAME --max-output-tokens 1000
```

Only the node prompt, accepted context, and validation feedback are sent, with `store: false`, no tools, and no conversation history. The JSON schema is enforced via `text.format` and revalidated locally. Refusals and incomplete responses block the node.

## Canvas Node Convention (v0.1 Legacy & Core)

Edges are directed `fromNode → toNode`; colors are visual only. JSON configuration starts on the line after the node prefix (plain text, no Markdown fences).

| First line | Node body / behavior |
| --- | --- |
| `TEXT:` | Literal text with `status=true`. A text node without a prefix is also literal text. |
| `DATA:` | `{"status":true,"confidence":0.9,"text":"..."}` — all fields required. |
| `GATE: AND` | No body. All inputs must be `true`. |
| `GATE: OR` | No body. At least one input must be `true`; forwards only accepted branches. |
| `GATE: NOT` | No body. Single input; inverts `status` without forwarding rejected content. |
| `GATE: REGEX` | `{"pattern":"(?i)approved"}` — single input, Python regex search. |
| `GATE: WORDS` | `{"min_words":4,"max_words":60}` — single input, whitespace-delimited words. |
| `GATE: CONFIDENCE` | `{"min_confidence":0.8}` — single input. |
| `CODEX:` | JSON with `prompt`, optional `max_retries`, `min_confidence`, `min_words`, `max_words`, `pattern`. |
| `OUTPUT: Name` | No body. Collects accepted text into the Markdown report. |

File nodes may reference only `.md` files inside the vault (paths relative to `--vault`). Groups are visual only and cannot be edge endpoints. At least one `OUTPUT` (or `WRITE` in CanvasGate mode) is required.

## Budgets & Exit Codes

- `--max-calls 3`: global attempt cap across all nodes and retries.
- `max_retries: 2`: up to 3 attempts on that node within the global budget.
- `--timeout 120`: per-call timeout in seconds.
- `--max-context-chars 16000`: serialized JSON context cap checked before every call (blocks without truncation).
- Exit codes: `0` completed, `2` workflow blocked by conditions, `1` error.

## Tests & Benchmarks

### Token Benchmarks

- **30-note contradictory archive:** `python -m canvasgate.stress_benchmark` (results in `examples/vault/StressBenchmark/Results/`). Supports `--transport api --model MODEL_NAME`.
- **6-note dispatch task:** `python -m canvasgate.benchmark` (three variants: full context, manual Obsidian selection, CanvasGate; `--prepare-only` creates fixtures without model calls).

### Local Test Suite

```powershell
python -m unittest discover -s tests -v
```

All unit tests run offline with zero network calls and zero token usage. Install in editable mode with `python -m pip install -e .` to use `canvasgate`, `canvasgate`, `canvasgate-studio`, and `canvasgate-mcp` commands.

## License

MIT — see [LICENSE](LICENSE).
