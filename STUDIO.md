# CanvasGate Studio

Version 0.4 includes a Windows desktop application and an MCP server. Start from [the desktop setup guide](desktop/README.md). The browser development launcher and workflow concepts below remain available.

A local graphical web application for the same `.canvas` workflows used in Obsidian. No Obsidian plugin, account or cloud hosting is required. The UI and demo task are in English.

## Start

From this project folder, install once:

```powershell
python -m pip install -e .
```

Double-click **CanvasGate-Studio.cmd**. It starts Python in the background and opens http://127.0.0.1:8874/. Starting it again reuses the existing local Studio server. Logs and the launched process ID are in `.studio/`. If a different application occupies the port, the launcher reports an error.

For a visible console, another port, or another existing vault:

```powershell
python -m canvasgate.web --vault examples/vault --port 8874 --open
```

Stop a console server with Ctrl+C. For a launcher-owned background server, inspect `.studio/server.pid` and stop that matching Python process in Task Manager. Do not run two Studio servers against the same vault.

## First simulation

1. Open **Studio/Order review** and click **Validate**.
2. Click **Run workflow**. Keep **Mock**, **Strict isolation**, and writes disabled.
3. Inspect the `plan` node's **Contract**, **Decision** and **Inputs** tabs. Inputs are the actual saved context and provenance, not a reconstruction from live notes.
4. Click **Replay**. Decision comparison should match, with no live model requests and no target writes.
5. Open **Run history** or download **Snapshot** for the saved graph, manifest, source bytes, node inputs/results and effect ledger.

Validation checks graph structure/configuration; runtime contracts check the actual context reaching a node. Simulation stages and discards target writes, but still saves run evidence and inspection notes. The bundled mock demonstrates orchestration; it does not assess a model's intelligence.

Drag nodes, pan/zoom, add or remove nodes, connect labeled edges, and edit node instructions or contract JSON in the inspector. Save before running. Import/export uses standard Canvas JSON. The source editor and workflow save reject stale expected hashes rather than silently overwriting external edits.

## P0: explicit context contracts

Configuration lives inside the Canvas JSON. `require_contracts` makes missing AGENT/WRITE contracts a configuration error. A contract may constrain both input and output:

```json
{
  "canvasgate": {
    "version": 3,
    "require_contracts": ["AGENT", "WRITE"],
    "permissions": {"read_dirs": ["Studio"], "write_dirs": ["Studio/Output"], "allow_cli": false},
    "contracts": {
      "plan": {
        "input": {
          "required_sources": [{"path": "Studio/Specification.md", "version": {"key": "revision", "equals": 3}, "role": "policy"}],
          "allowed_sources": ["Studio/Specification.md"],
          "required_text": ["Reject booleans as integers", "Reject duplicate SKUs", "Use integer cents"]
        },
        "output": {
          "required_fields": ["tasks", "tests", "risks"],
          "schema": {"type": "object", "required": ["tasks", "tests", "risks"]}
        }
      }
    }
  }
}
```

The executable demo additionally pins each required source's `sha256` to the actual 64-character digest and uses typed array schemas. **Pin current source hashes** explicitly updates hashes only; expected versions/roles stay unchanged. Inspect a source change before accepting a new pin.

Source identity comes from engine provenance, not model assertions. `required_text` checks the received slice, so a valid source hash alone cannot conceal a missing essential paragraph. `required_fields` uses dotted object paths in JSON context fragments. JSON Schema uses Draft 2020-12 and local references only. Failed input contracts stop before inference; failed output contracts reject the response and follow bounded retries.

Contracts establish declared requirements. They cannot infer essential requirements that nobody encoded. Older workflows remain compatible; enable mandatory contracts explicitly to harden them.

## P0: snapshots and reproducibility

Each run has `.canvasgate/runs/<run-id>/manifest.json`, a pinned graph, content-addressed source bytes, node checkpoints and external-call records. The manifest captures graph version/hash, engine source fingerprint, backend/model settings, permissions, actual source hashes and final report integrity. Tokens and outcomes appear per node when the provider reports usage; unavailable usage is not presented as zero.

Replay uses pinned source bytes and saved model responses. It never infers or commits target writes, and compares node states, signals, input/output hashes and active routes. Live source edits or deletion do not affect replay. A changed engine fingerprint refuses execution; retain the matching engine checkout/environment. Hashes detect accidental corruption, but are not signatures protecting against an attacker with access to the same OS account. A fresh model inference is a new experiment and may differ.

Use PowerShell quoting for actual paths:

```powershell
python -m canvasgate "examples/vault/Studio/Order review.canvas" --vault examples/vault --replay RUN_ID --output-dir examples/vault/Studio/CLI
python -m canvasgate "examples/vault/Studio/Order review.canvas" --vault examples/vault --resume RUN_ID --backend mock --output-dir examples/vault/Studio/CLI
```

Resume must use the original backend/model configuration, including timeout/output settings. The CLI's default mock response differs from Studio's structured demo mock; resume Studio runs in Studio. Offline replay needs no API key or CLI installation.

## P1: recovery and idempotency

Studio assigns operation keys to submissions. The engine/CLI accepts `--operation-key`; repeating the same key and request reuses the run, while changed requests are rejected. Each provider attempt is durably marked PENDING before invocation and COMPLETED with the exact saved response afterward. On restart, completed calls are reused. A PENDING/UNCERTAIN call blocks automatic repetition because the external provider may already have executed or charged it.

Studio offers explicit reconciliation: record the observed response envelope (`status`, `confidence`, `text`) or authorize another attempt. Reconciliation cannot race an active execution. Authorization may duplicate an external action or charge. **Resume** is a separate action after reconciliation. No generic shell, payment or external business-action API is exposed; a future external connector must pass supported provider idempotency keys or implement its own reconciliation. This is not a universal exactly-once guarantee.

Writes use staging, original-content checks, a recovery journal and atomic replacement per file. Resume recognizes an already committed journal and does not append twice after a crash. Recovery rolls back incomplete transactions and refuses committed ones. External editors can observe partial multi-file commits; this is not simultaneous atomic visibility across files.

## P1: security boundary

Workflow reads and writes have separate declared directory permissions. Empty arrays deny all. Parent traversal, symlinks, junctions, application metadata and recognized credential files are rejected. Known credential patterns and secret environment values are rejected before forwarding/persistence and redacted in diagnostics. This scanner cannot recognize every possible secret representation; use dedicated, non-secret workflow sources.

**Strict isolation is enabled in Studio by default and rejects host Codex CLI.** Mock/API execute no agent filesystem tools. Host CLI read-only mode, filtered environment and a short prompt do not provide OS process isolation. Disabling strict mode explicitly permits host CLI with this limitation. A future OS/container executor is required for safely containing arbitrary CLI commands; it is not implemented here.

The server binds loopback only. Host/Origin checks, an HttpOnly SameSite cookie and CSRF token protect mutations; CSP forbids remote scripts and eval. There is no credential input in the UI. Set `OPENAI_API_KEY` in the server environment for live API calls, then restart. Mock uses zero model tokens; live API/CLI calls use their normal provider billing. Limits include 2 MiB editor/request payloads, 500 nodes, 2,000 edges, 20 MiB snapshotted sources and at most 20 model attempts per Studio run.

## P2: explanations in Obsidian

Each Studio run exports `Studio/Runs/<run-id>/Inspect.canvas` and per-node Markdown evidence notes. They show reasons, sources, hashes, contracts, routing, retries and reported tokens. Inspection canvases cannot be executed. Original workflow layout/instructions remain editable separately. Run manifests and source blobs remain under hidden `.canvasgate/`.

## Verification

Run offline checks with `python -m unittest discover -s tests -q`. Browser QA is `python reports/studio_browser_qa.py` (requires Python Playwright and its Chromium). Evidence and limitations are in [Studio verification](reports/STUDIO_VERIFICATION_2026-10-30.md). Historical paid benchmark results remain in their original consolidated report; this feature work makes no live inference calls.
