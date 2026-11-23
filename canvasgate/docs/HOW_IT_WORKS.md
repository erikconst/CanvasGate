# How CanvasGate Works

CanvasGate is the deterministic workflow engine. CanvasGate Studio is the Windows application that runs it and displays results. A workflow is an Obsidian `.canvas` file describing nodes, connections, and rules. Sources are files inside the vault, typically Markdown notes.

## Execution flow

1. Studio reads the saved graph and validates nodes, edges, and contracts. The engine topologically sorts the nodes. Any cycle invalidates the graph before execution.
2. The engine pins the graph and source bytes into a snapshot. Each node receives only the payload forwarded by active edges.
3. **FILE** and **SLICE** nodes select the relevant source or section. A **GATE** node evaluates a deterministic Python condition such as a YAML key check. Edge labels decide which branch continues.
4. Before an **AGENT** node runs, the input contract checks data provenance against allowed sources, SHA-256 hashes, role, and declared versions, plus any required JSON fields or text fragments. A failed rule stops the node before any provider call.
5. The provider returns a structured response. The engine validates its envelope and output contract. Bounded retries may run on validation failure, with each attempt recorded in run history.
6. **JOIN** merges branches, **OUTPUT** publishes results, and **WRITE** stages file mutations. In preview mode, staged writes are discarded at the end. With commit enabled, the engine checks for external edits and applies changes using a recovery journal.

In the demo workflow, the `approved` node checks `status: approved`, and `policy` slices the **Policy** section for `plan`. If that section is missing, the engine stops the branch before inference. Contracts can also catch a present section that is missing required clauses.

## Evidence, replay, and recovery

Under `.canvasgate/runs/<run-id>/`, the engine stores the graph, sources, configuration, per-node results, and the external-call ledger. Snapshots remain inspectable in **History** even if live sources change. Reports and color-coded Obsidian inspection canvases appear in `Studio/Runs/<run-id>/`.

**Replay** uses pinned sources and saved model responses. It compares node decisions, signals, and input/output hashes. Replay never modifies target files and requires a matching engine fingerprint. A fresh live inference may produce a different output.

**Resume** continues an interrupted run and reuses already recorded responses. An idempotency key identifies repeated submissions. If the process stopped during an external call, the external outcome may be uncertain and requires explicit reconciliation before retrying. File replacements are atomic per file, and the journal supports recovery across multi-file writes.

## Where tokens are used

Reading files, slicing sections, evaluating gates, checking contracts, mock runs, and replay all execute locally with zero model tokens. Live inference consumes tokens according to the selected provider. Studio displays reported provider usage, or marks unavailable usage as unavailable rather than zero. An MCP-connected client uses its own model tokens when deciding which tools to call.

## Desktop app and MCP bridge

The Windows window hosts the editor in WebView2 and launches the bundled Python engine listening on localhost only for the open vault. The same engine serves the `/mcp` endpoint. The stdio bridge commands for Codex, Antigravity, and Claude Code forward requests to that local endpoint using a per-session bearer token, allowing agents to list, validate, simulate, and inspect workflows in the active workspace.

The engine enforces allowed read/write directories and rejects paths escaping the vault, symlinks, and known credential files. Strict mode refuses host Codex CLI execution while keeping mock and API modes available. Running host CLI agents with OS-level isolation requires an external container or VM boundary.

## Code map

- `desktop/CanvasGate.cs` manages the native window, WebView2 host, vault picker, and Python process.
- `canvasgate/web.py` serves the local Studio API and manages the run queue.
- `canvasgate/canvasgate.py` executes the DAG; `contracts.py` and `security.py` enforce contracts and path boundaries.
- `canvasgate/snapshots.py` manages snapshots and the call ledger; `transactions.py` handles staged writes and recovery.
- `canvasgate/agent_bridge.py` provides the MCP tools, agent guide, and stdio bridge.
- `desktop/build.py` builds the Windows installer with the isolated Python runtime and bundled guides.
