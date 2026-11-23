# CanvasGate Studio 0.3 — implementation and verification

Date: 2026-10-30. This report covers the new contracts, reproducibility, recovery, security, observability and graphical application work. The [earlier consolidated report](TEST_REPORT_2026-10-30.md) retains the historical paid benchmarks and its original 60-test snapshot. No historical token measurements were rerun or replaced.

## Delivered behavior

| Priority | Implementation | Verification |
| --- | --- | --- |
| P0 — complete context | Mandatory per-node contracts; engine-derived provenance; allowed/required sources; pinned SHA-256, version and role; required fields/literals; input/output JSON Schema | Missing essential slices, wrong versions/hashes, unauthorized sources and missing fields fail closed; input failures precede model calls |
| P0 — reproducibility | Pinned graph/source bytes, graph version, model/run settings, runtime and engine hashes; actual node inputs/results; saved call responses | Offline replay survives live source/graph deletion, compares deterministic decisions, uses no model calls or target writes; altered snapshots rejected |
| P1 — recovery | Operation keys; durable PENDING/COMPLETED/UNCERTAIN call ledger; reconciliation; per-run locks; commit-journal recognition | Real child-process exits during external calls and after commit; no blind retry and no duplicate append on resume |
| P1 — security | Read/write directory permissions; metadata/credential exclusions; symlink/junction checks; secret rejection/redaction; strict mode refuses host CLI; loopback HTTP protections | Directory boundaries, secrets, strict CLI refusal, Host/Origin/session/CSRF checks and private-path rejection |
| P2 — explanations | Decision reasons, routing, retries, source hashes, real inputs and reported usage in UI; per-node Markdown and inspection Canvas exports | Browser inspector and snapshot APIs; generated `Inspect.canvas` checked |
| P3 — graphical application | English local web UI with graph/source editors, validation, simulation/live provider selection, history, snapshot download, replay/resume and reconciliation | Chromium interaction and screenshots; launcher starts and reuses one background server |

## Automated regression suite

Final command: `python -m unittest discover -s tests -q`.

**81 test methods passed; 0 failures; 0 errors; 12.168 seconds.** All provider interactions in this verification were mock/local. Test methods and browser assertions are separate counts.

- Original regression suite: 60 methods, preserving workflow, transaction and benchmark behavior.
- Contracts/snapshots/security/crash suite: 12 methods in [test_snapshots_contracts.py](../tests/test_snapshots_contracts.py).
- HTTP/application suite: 9 methods in [test_web.py](../tests/test_web.py).

Recorded output: [unittest.txt](studio-qa/unittest.txt).

The new HTTP tests cover authentication, CSRF, hostile Host/Origin, CSP without eval, credential/metadata/traversal paths, optimistic source/graph edits, graph validation, explicit pin changes, operation-key reuse and request mismatch, replay, snapshot bundles, incomplete-context failure, strict CLI refusal, reconciliation locking, and CLI replay without live API configuration.

The crash tests use actual child processes and `os._exit`, rather than just caught exceptions. These are process-failure tests; they do not simulate physical power loss or a storage device losing acknowledged writes.

## Browser verification

Repeatable command: `python reports/studio_browser_qa.py`. It creates a disposable vault and server, runs Chromium, and closes its owned browser/server afterward. The delivered application server is separately started by the launcher.

**11 browser checks passed, with no JavaScript errors:** eight-node graph rendering, validation, pointer drag/save, mock simulation, actual-input inspector, replay decision equality, zero replay external calls, run history, incomplete-context blocking before AI, mobile horizontal containment and no JavaScript errors.

Structured evidence: [checks.json](studio-qa/checks.json). It includes original, replay and failure reports. Temporary vault paths in that evidence identify test fixtures which have been cleaned up.

Screenshots were rendered and visually inspected:

- [Workflow editor](studio-qa/editor.png)
- [Successful run and actual context/provenance](studio-qa/execution.png)
- [Replay](studio-qa/replay.png)
- [Run history](studio-qa/history.png)
- [Missing-policy-heading failure](studio-qa/contract-failure.png)
- [Mobile layout](studio-qa/mobile.png)

The heading test changes `## Policy` to another heading while keeping the original contract. Execution stops at slicing, makes zero external calls, and preserves the failure snapshot. The separate core contract test catches an incomplete slice before any model invocation even when ordinary length checks would be insufficient.

## Issues found and fixed during verification

1. Concurrent UI polling could briefly block Windows atomic manifest replacement. A bounded retry now retries only the file replacement, not the inference or business operation.
2. Early rejection of HTTP POST requests with unread bytes could reset the Windows socket before the browser received its error. Requests consume a size-bounded body before authentication/origin rejection.
3. CLI replay constructed a live backend unnecessarily. It now works offline even if `--backend api` is supplied without model/key configuration.
4. Reconciliation could race a still-running provider call. It now acquires the run execution lock and reloads the manifest before changing effect state.
5. The graph viewport's minimum height could clip lower nodes. The bounded desktop viewport and resize fitting now show the graph correctly.
6. Engine fingerprints now include imported deterministic engine code and Python/PyYAML/jsonschema runtime versions. Restarting Studio after an engine edit is required; the running process keeps its loaded-engine identity.
7. Windows port binding uses exclusive ownership to prevent multiple listeners sharing Studio's port. The launcher was checked twice and reused the same server process.

## Practical limits

- There is **no OS/container sandbox for host Codex CLI**. Strict mode refuses it. Disabling strict mode permits the host process with that limitation. Prompt/context restriction is not process isolation.
- Completed saved responses support exact response reuse. A new model inference need not reproduce the original output.
- External calls with uncertain outcomes need explicit reconciliation. Generic exactly-once effects are not promised; future action connectors must implement provider idempotency or explicit reconciliation. The app exposes no arbitrary shell/business-action endpoint.
- Hash verification detects corruption; it is not authenticated protection against an attacker with the same OS account. Snapshots contain actual task context and should be treated as local confidential data.
- Per-file replacements are atomic; a group of files is recoverable, not simultaneously visible as one atomic update to external editors.
- Secret detection covers known patterns and environment values; it is not proof that all possible sensitive text can be recognized.
- Contracts enforce what is declared. They cannot discover omitted essential business requirements automatically.
- Live API/CLI inference was not tested during this enhancement. These checks establish orchestration and failure behavior, not new claims about model quality or token savings.

## Launch and use

Open [CanvasGate-Studio.cmd](../CanvasGate-Studio.cmd), then http://127.0.0.1:8874/. Start with **Mock**, strict mode enabled and target writes disabled. Full instructions: [STUDIO.md](../STUDIO.md).
