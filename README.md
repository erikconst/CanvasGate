# CanvasGate

**Deterministic Obsidian Canvas workflows, explicit context contracts, isolated model calls, and offline replay.**

**Obsidian Canvas → deterministic Python gates → isolated model call → validation → recoverable writes.**

No Obsidian community plugin required. Runs locally with Python 3.11+ (`PyYAML`, `jsonschema`).

---

## Desktop App & MCP (CanvasGate Studio 0.4)

- **Windows installer:** Download `CanvasGate-Studio-Setup.exe` from [GitHub Releases](https://github.com/erikconst/CanvasGate/releases) or build locally via [desktop/README.md](desktop/README.md).
- **Browser dev launcher:** Run `CanvasGate-Studio.cmd` (or `python -m canvasgate.web --vault examples/vault --open`).
- **MCP integration:** Open the **Agents** tab in Studio to connect **Codex**, **Antigravity**, or **Claude Code** ([MCP User Guide](canvasgate/MCP_USER_GUIDE.md) · [MCP Agent Guide](canvasgate/MCP_AGENT_GUIDE.md)).

## Quick Start (CLI, Zero Tokens)

```powershell
python -m pip install -e .

# Validate graph, contracts, and topological order
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --dry-run

# Simulate with mock backend (no tokens, no target writes)
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --backend mock --output-dir examples/vault/CanvasGate/Runs
```

Installed CLI entry points: `canvasgate`, `canvasgate-studio`, and `canvasgate-mcp`.

### Live Backends

- **OpenAI Responses API (no tools, `store: false`):**
  ```powershell
  python -m canvasgate examples/vault/workflow.canvas --backend api --model MODEL_NAME --max-output-tokens 1000
  ```
  Requires `OPENAI_API_KEY` in the process environment.
- **Codex CLI (`--ephemeral`, `--sandbox read-only`):**
  ```powershell
  python -m canvasgate examples/vault/workflow.canvas --backend codex --max-calls 3
  ```

## Key Features

- **Deterministic slicing & gates:** `SLICE` (`SECTION`, `YAML`, `LINES`), `GATE` (`YAML_EQ`, `JSON_KEYS`, `LEN_LT`, `REGEX`, `AND`, `OR`, `NOT`), `JOIN` (`ANY`/`ALL`), and labeled `true`/`false`/switch edges.
- **Fail-closed context contracts:** Pin `required_sources` (SHA-256, YAML version, role), `allowed_sources`, `required_text`, `required_fields`, and JSON Schema (Draft 2020-12).
- **Immutable snapshots & offline replay:** Every run saves `.canvasgate/runs/<run-id>/` for exact offline replay, resume, and reconciliation, plus `Inspect.canvas` for Obsidian.
- **Recoverable writes:** `WRITE` (`APPEND`/`OVERWRITE`) uses in-memory staging, external-edit conflict checks, a recovery journal, and per-file atomic replacement.

## Tests & Benchmarks

```powershell
python -m unittest discover -s tests -v
```

All 87 unit tests run offline with zero network or token usage.

- **Specifications:** [CANVASGATE.md](CANVASGATE.md) · [STUDIO.md](STUDIO.md)
- **Verification & Benchmarks:** [TEST_REPORT_2026-10-30.md](reports/TEST_REPORT_2026-10-30.md) · [STUDIO_VERIFICATION_2026-10-30.md](reports/STUDIO_VERIFICATION_2026-10-30.md) · [3D Snake Benchmark](benchmarks/snake/README.md)

## License

MIT — see [LICENSE](LICENSE).
