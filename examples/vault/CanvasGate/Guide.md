# CanvasGate — start here

[[workflow.canvas|Open this workflow]] and [[Specification|its English specification]].

The approved path checks YAML frontmatter, extracts only the API section, verifies its length,
asks Codex for an implementation plan, and stages a Markdown output. The unapproved path asks
for review instead. JOIN waits for dependency resolution and merges only the active branch.

## Run it

From the project folder:

- Double-click **CanvasGate-Simulate.cmd** for a fixed mock response with zero model tokens.
- Double-click **CanvasGate-Run.cmd** for a real Codex run, limited to three model attempts.

Both launchers use the new CanvasGate engine automatically. The mock checks wiring and writes
a demonstration string; it does not perform the planning task. Save changes in Obsidian before running.

The accepted result appears in [[Output/Implementation-plan|Output/Implementation-plan.md]].
Each run also creates a visible `Runs/<run-id>/RunReport.md` and JSON report. Internal journals and
backups live under `.canvasgate/` in the vault and are ignored by Git.

## Try the branches

Change `status: approved` to `status: draft` in [[Specification]]. The implementation branch is
skipped, and the review branch runs. Restore `approved` to use the sliced implementation path.
The YAML value is typed: `reviewed: true` is a boolean; `reviewed: "true"` is a string.

To test a critical gate without spending tokens, lower `GATE: LEN_LT:2000` to `GATE: LEN_LT:1`.
The run aborts before the agent, and the existing output file stays unchanged. Restore `2000` afterward.

## Transaction behavior

WRITE stages changes in memory. Only a completed, valid run commits them. If a later node fails,
all staged changes are discarded. Commit uses a writer lock, original-file checks, backups and
atomic replacement of each file. A normal mid-commit failure triggers rollback. Interrupted commits
can be recovered from the journal with the CLI's `--recover RUN_ID` option.

Multiple files are not simultaneously atomic: another program can briefly observe a partial commit.
Recovery will stop rather than overwrite an external edit. Treat the JSON transaction manifest as
the authoritative state if the process was interrupted before its final audit report.

## Context and model controls

Use SLICE before AGENT to limit context. A slice replaces the original full-note payload; excluded
sections are not forwarded. A false edge explicitly authorizes the rejected input to reach its review
branch. An unlabeled edge is unconditional, so use a gate or a `true` edge for approval checks.

Each agent call is independent. All agents and retries share `--max-calls`. `[schema=code_only]`
checks Python syntax without executing the output; `[schema=json]` checks JSON syntax. The outer
response always has status, confidence and text. Syntax validation does not prove correctness.
`[max_tokens=N]` is enforced only by an API node; Codex CLI nodes reject that option before calling
any model. Codex CLI read-only mode does not guarantee isolation from all local file reads.

See the project's `CANVASGATE.md` for the complete implemented language and recovery commands.
