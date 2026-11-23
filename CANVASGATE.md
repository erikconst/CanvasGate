# CanvasGate 0.2 — implemented architecture

CanvasGate separates local deterministic control from stateless model execution, using Obsidian
Canvas as the editor. The Python package and previous CLI name remain `canvasgate`; an installed
`canvasgate` command is also available. Workflow examples and generated audit reports are in English.

## Run the new workflow

Requires Python 3.11+ and PyYAML 6 (a safe YAML parser; no agent framework or vector database).

```powershell
python -m pip install -e .
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --dry-run
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --backend mock --output-dir examples/vault/CanvasGate/Runs
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --backend codex --max-calls 3 --output-dir examples/vault/CanvasGate/Runs
```

Open `CanvasGate/Guide.md` inside the existing Obsidian vault. The project also includes
`CanvasGate-Simulate.cmd` and `CanvasGate-Run.cmd`. Mock mode simulates every agent even if a node
specifies `[model=codex]`; it uses zero model tokens and labels the audit as a simulation.

The parser selects the CanvasGate engine when it sees its new prefixes, inline predicate syntax,
or nonempty edge labels. Existing v0.1 graphs keep their previous semantics. Use
`--engine canvasgate` or `--engine legacy` to choose explicitly. The report records the engine.

## Components and runtime states

| Component | Responsibility |
| --- | --- |
| `canvasgate.py` | DSL parser, preflight checks, linear-time DAG scheduling, typed signals, payload routing and node traces |
| `markdown.py` | Safe typed YAML frontmatter and Markdown section extraction |
| `providers.py` | Per-node Codex/API selection, capability checks and shared usage accounting |
| `transactions.py` | In-memory staging, optimistic conflict checks, writer lock, journal, replace and rollback |
| `backends.py` | Stateless Codex CLI, Responses API without tools, and explicit mock mode |

Node states are `EXECUTED`, `SKIPPED`, or `FAILED`. A failure aborts the run and marks remaining
nodes SKIPPED. The report records each node's duration, attempts, token usage when available,
input preview, output and reason. Transaction states are `COMMITTED`, `NO_WRITES`, `PREVIEW`,
`ABORTED`, or `RECOVERY_REQUIRED`. The CLI exit codes remain 0 completed, 2 blocked, 1 error.

The graph is parsed and checked before the first model call: duplicate identifiers, dangling
edges, unknown nodes and schemas, invalid configuration, paths, arity and cycles are errors.
Visual groups are allowed but cannot be connected. There must be at least one WRITE or OUTPUT.
Sources have no incoming edges; processing nodes require explicit inputs. Nodes run sequentially
in topological order; this release does not run agents concurrently.

## Node language

Use ordinary Canvas text cards with these prefixes. JSON configuration is plain text, without fences.

| Node | Meaning |
| --- | --- |
| Native file node | Read a UTF-8 file inside the vault; Markdown frontmatter is parsed. Optional `subpath: "#Heading"` extracts a heading. |
| `INPUT: true` | A typed JSON constant; objects, arrays, numbers, null and quoted strings also work. Plain unquoted text is accepted. |
| `TEXT:` followed by text | Literal text source. Use TEXT explicitly if the content includes a colon that could be mistaken for an opcode. |
| `DATA:` followed by JSON | Legacy-compatible object containing exactly status (boolean), confidence (0–1), text (string). |
| `SLICE: SECTION:API` | Extract exactly one ATX heading (case-insensitive title), including its subheadings until the next heading of the same or higher level. Headings inside fenced code are ignored. Missing or duplicate matching headings fail. |
| `SLICE: YAML:limits.max` | Extract one typed frontmatter value; dotted paths select nested mapping keys. Missing values fail. |
| `SLICE: LINES:2-8` | Extract inclusive 1-based lines of the full incoming text, including frontmatter if present. Out-of-range intervals fail. |
| `GATE: AND`, `OR`, `NOT` | Logical operations on boolean signals. AND requires all declared inputs to be active and true; OR accepts any true active input. NOT has one input. |
| `GATE: REGEX:pattern` | Python regex search, or legacy JSON body `{"pattern":"..."}`. |
| `GATE: YAML_EQ:status=approved` | Compare a frontmatter key to a typed YAML value. Missing key evaluates false. Types must match, so true differs from quoted "true" and from 1. |
| `GATE: LEN_LT:2000` | Strictly fewer than 2000 Python characters. This is a character limit, not a line or token estimate. |
| `GATE: JSON_KEYS:host,port,tls` | Incoming text must parse as a JSON object containing the named top-level keys. |
| `GATE: WORDS` / `CONFIDENCE` | Existing JSON configuration for word count or minimum confidence. |
| `AGENT: instructions` | Independent model call, with optional bracket options below. `CODEX:` with a JSON configuration is also accepted in CanvasGate. |
| `JOIN: ANY` / `MERGE:` | Wait until all incoming dependencies resolve, then merge active payloads. Inactive branches do not deadlock it. |
| `JOIN: ALL` | Execute only if every incoming edge is active; otherwise SKIPPED. |
| `WRITE: APPEND:path.md` | Stage an exact append (no automatically inserted newlines). |
| `WRITE: OVERWRITE:path.md` | Stage replacement of the target's content. |
| `OUTPUT: Title` | Publish the accepted merged text in the run report. |
| `ABORT: Reason` | Explicitly abort and discard staged writes. |

Logical and content predicates other than AND/OR require one incoming edge. JOIN, WRITE, AGENT
and OUTPUT merge active inputs after all dependencies resolve. An active OUTPUT or WRITE is
enough to complete a run; inactive alternative terminals are expected in IF/ELSE graphs.

PyYAML SafeLoader is used with duplicate-key rejection. YAML aliases, anchors, custom objects,
non-JSON values such as unquoted timestamps, and non-string mapping keys are rejected. Quote dates
to treat them as strings. The frontmatter must start on the first line and have a closing delimiter.
SafeLoader follows its YAML scalar typing rules; use explicit quoting when string identity matters.
SECTION supports ATX headings (`#` through `######`), not Setext headings or Markdown block parsing.

## Signals, payloads and conditional edges

Every executed node emits a control signal independently of its text payload. Files and text emit
boolean true. INPUT emits its literal boolean or string signal; other JSON constants emit true.
DATA emits its explicit status. Predicates emit booleans while retaining the original payload.

| Edge label | Activation |
| --- | --- |
| Empty | Unconditional if the source executed, including a false INPUT signal |
| true, 1, yes, da, pass | Signal must be the boolean true |
| false, 0, no, nu, fail | Signal must be the boolean false |
| Any other label | Exact, case-sensitive equality with a string signal |

Boolean label aliases are case-insensitive and reserved. String "false" is not a boolean false.
Use explicit conditional edges or gates for approval; an unlabeled edge is not an implicit AND.

A false GATE with no outgoing false-label route is **critical** and aborts the entire run. Add a
false route when rejection is a normal branch. Its payload is intentionally available to that review
branch. A branch that was SKIPPED has no signal and cannot activate another branch through NOT.

Payloads are deduplicated by origin node ID when merged. A SLICE emits a new payload containing
only the selected fragment and drops the original note and metadata from subsequent model context.
An AGENT boundary emits only its validated result, not its input history. This avoids both accidental
reintroduction of sliced material and loss of the original text after a boolean gate.

## Agent configuration, providers and validation

```text
AGENT: [model=codex] [schema=result] [max_retries=2]
Write an English implementation plan using only the provided context.
```

Or use explicit JSON configuration:

```text
AGENT:
{"prompt":"Return a JSON configuration.","schema":"json","max_retries":2,"min_confidence":0.8,"max_words":100}
```

The outer response always has exactly `status`, `confidence`, and `text`, imposed by the model
adapter's JSON Schema and checked locally. Named schemas constrain `text`:

- `result`: string text and the standard envelope.
- `json`: text must parse as JSON.
- `code_only`: text must be non-empty, syntactically valid Python. The code is **not executed**.

These checks enforce structure, not truth or semantic correctness. `confidence` is the model's
self-assessment; it is not a calibrated probability. Tests or task-specific checks are still needed.

Model selection:

- No node model: use the CLI-selected default backend/model.
- `model=codex`: Codex CLI with the selected/default CLI model.
- `model=codex/MODEL`: Codex CLI with that exact model name.
- `model=openai/MODEL`: Responses API with that exact model name; requires OPENAI_API_KEY.
- An unprefixed model name uses the default provider. No model alias is silently upgraded.

`[max_tokens=N]` is supported only for API nodes and is capped by the selected API output budget.
Codex CLI cannot enforce it here, so specifying it on a real CLI node fails preflight. It is never
silently ignored or misrepresented as a guaranteed token limit. `--backend mock` overrides all
provider choices for safe simulation. Local Ollama routing remains a future extension.

All agents/retries share `--max-calls` (default 3). `max_retries=2` allows at most three attempts at
that node within the global budget. Invalid envelopes, failed content rules, status=false, invalid JSON
or Python syntax can trigger retries with validation messages. Transport/authentication errors stop
the node without automatic retry. A node does not stage writes until its result is accepted.
`--max-context-chars` applies before every agent call without truncation; `--timeout` bounds each call.

Codex runs independently in a temporary directory with ephemeral sessions, no user configuration,
no shell tools or web search, a read-only sandbox and structured output. These CLI settings do not
prove that every local read is impossible. The API backend has no tools or file access and receives
only the serialized context, instruction and validation feedback, with store=false and no history.

## Staging, commit and recovery guarantees

1. WRITE nodes prepare changes in RAM. Multiple changes to one path compose in node execution order.
2. On a critical gate or agent error, all staged changes are discarded. No target file is touched.
3. Before commit, source fingerprints are checked to reject stale context and target snapshots are
   checked to reject edits made after staging.
4. A vault-local OS file lock serializes cooperating CanvasGate writers. The lock is released by the
   OS if the process exits. It does not lock Obsidian or unrelated editors.
5. A journal records original hashes, desired hashes, target paths and original bytes before applying
   writes. Each file is replaced through a flushed temporary file and `os.replace`.
6. An ordinary commit failure triggers rollback. If rollback cannot finish, the run explicitly reports
   RECOVERY_REQUIRED. New writing workflows refuse to run while a journal is unresolved.
7. Recovery compares current file hashes against both old and staged content. An external edit is
   preserved and reported as a conflict rather than overwritten automatically.

**This is recoverable multi-file writing, not simultaneous atomic visibility across all files.**
Other programs can briefly see some new files and some old files. This is not a database transaction,
hostile-filesystem security boundary, or a guarantee against hardware/power failure. Source/target
checks are optimistic and cannot eliminate every race with a non-cooperating external editor.
Rollback restores file content and supported mode bits; newly created empty directories may remain.
Full Windows ACL/alternate-stream/extended-attribute preservation is not promised.

To run agents and inspect staging without changing target files:

```powershell
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --backend mock --no-commit
```

`--dry-run` performs only graph/configuration preflight and makes no model call or audit files.
`--no-commit` executes agents (unless mock), writes an audit, and discards staged mutations afterward.

To recover an interrupted transaction:

```powershell
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --recover RUN_ID
```

Recovery makes no model call. It restores incomplete transactions, is repeatable after successful
rollback, and refuses to undo committed transactions. A recovery conflict requires inspection of the
target file and journal before retrying; do not delete the journal to conceal a partial commit.
If journal metadata itself is unreadable, automatic recovery stops for manual inspection.

WRITE rejects absolute paths, parent traversal, paths resolving outside the vault, and application
metadata (`.git`, `.obsidian`, `.canvasgate`). Supported artifacts: md, txt, json, yaml, yml, py, csv, toml.
File sources may be other UTF-8 text files inside the vault, up to 10 MiB each. A graph is trusted local
configuration, including its Python regular expressions; no arbitrary regex timeout is guaranteed.

Use `--run-id UNIQUE_ID` for a known operation identity. Existing audit or transaction IDs are refused
before another model call, preventing an accidental replay with that ID. A new ID is a new operation:
APPEND is intentionally not deduplicated across different runs.

## Audit and real token usage

Internal audit: `.canvasgate/logs/<run-id>.json` and `.md`. Transaction journal and backups:
`.canvasgate/transactions/<run-id>/`. If a process dies before the final audit, the transaction manifest
is authoritative. The CLI exports a visible `RunReport.md`, `report.json`, and `results.md` to its
`--output-dir`; the supplied launchers place these under `CanvasGate/Runs/` in Obsidian.

The audit includes actual backend-reported input, cached input, output and total tokens across all
agent attempts/providers, plus source hashes. Cached input is a subset of input. Missing provider
usage remains null/unavailable, never a character-based estimate. Mock attempts report zero model
tokens and are labeled simulated. Token counts do not directly measure subscription quota or money.
`--events-dir PATH` retains raw CLI events and exact prompts for inspection. Journals and reports can
contain the supplied source content; runtime folders are ignored by Git.

## Verification and compatibility

```powershell
python -m unittest discover -s tests -v
```

Tests cover branch activation, dead-branch joins, typed YAML, code-fence-aware slicing, context
exclusion, shared model budgets, validation retries, transaction conflicts, failed commits, crash
recovery, external edits, writer locking, real usage parsing, and the previous workflow behavior.
The existing benchmark remains unchanged and its original measurements remain available.

The roadmap's automatic Canvas coloring and Ollama integration are not included in this core release.
Execution is manually started through CLI/launchers; no Obsidian community plugin is required.

## Contradictory archive and transport benchmarks

```powershell
python -m canvasgate.stress_benchmark --prepare-only
python -m canvasgate.stress_benchmark
python -m canvasgate.stress_benchmark --repetitions 3
```

This suite uses 30 English notes: three current dispatch inputs, eighteen superseded policy/fleet/order
snapshots with conflicting rules, and nine current notes from unrelated departments. The actual graph
requires both `status: current` and `domain: dispatch`, then slices the selected sections. The task and
source-authority instructions are identical for full context, manual selection and gated execution.
The exact-answer oracle is unchanged. A correct baseline is retained and reported, not treated as a
benchmark failure. Each repetition makes three real CLI calls; multiple samples cost more quota.

For a separate transport experiment, configure OPENAI_API_KEY locally and select an explicit API model:

```powershell
python -m canvasgate.stress_benchmark --transport api --model YOUR_API_MODEL
```

The API suite uses Responses without tools and explicitly requests medium reasoning. It records the
provider's actual usage, including reasoning separately as a subset of output, and saves request bodies
without authentication headers. The graph contains no CLI-specific model tags, so every variant uses
the chosen transport. Do not compare differing models as though they isolate transport overhead.

Each sample saves exact prompts/requests, provider events/responses, usage, oracle results and graph
traces under `StressBenchmark/Results/`. A corpus manifest contains source content and hashes.
The benchmark does not retry quality failures or hide unsuccessful samples. With one sample it is
a pilot, not a reliability estimate. Later repetitions rotate execution order to reduce order bias.

The roughly 12k input tokens seen in earlier CLI runs are not a separately metered system-prompt size.
Neither five times that value nor an API result below 1,500 total tokens is a measured guarantee. Direct
API calls avoid the CLI agent setup, but input serialization, schemas, output and reasoning still count.
Only matched tasks/models and real provider usage can establish an actual difference.
