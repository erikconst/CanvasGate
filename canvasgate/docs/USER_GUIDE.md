# CanvasGate Studio User Guide

CanvasGate Studio opens and executes Obsidian Canvas workflows from a local folder. The interface displays each workflow graph, node rules, context contracts, and run history.

## First run

1. Open **CanvasGate Studio** from the Desktop or Start menu.
2. In **Demo Vault**, select **Studio/Order review** from the workflows list.
3. Click **Validate** to check the graph structure and contract configuration.
4. Click **Run**. Choose **Mock**, keep **Strict isolation** enabled, and leave target writes disabled.
5. Select the `plan` node. Under **Decision** you can see why it ran and which rules it checked. Under **Inputs** you can inspect the exact context it received.
6. Click **Replay** to reproduce decisions from the saved snapshot. Check the comparison result under **Execution** or **History**.

Mock simulation uses zero model tokens inside CanvasGate. It saves the snapshot and inspection notes while leaving workflow output files unchanged.

## Use your own vault

1. Click **Open vault…** and select the root folder of your Obsidian vault (or any project folder).
2. Open an existing workflow or click **+** next to **Workflows** to create a new one.
3. Use **Add node** to add sources, gates, or other operations. Use **Connect** to draw edges, selecting nodes in source-then-target order.
4. Click **Fit view** to see the full graph. Click the zoom percentage to reset to 100% or use the zoom buttons.
5. Click **Save** before clicking **Validate** or **Run**. If Obsidian modified the file in the meantime, reload the workflow and review the changes before saving.

Use **Sources** to edit notes. When you intentionally modify a hash-pinned source, review the change and then click **Pin current source hashes** under **Contract**. This updates the hash only; expected revision and role values are edited separately in the contract.

## Inspect results

- **History** lists past runs. **Inspect** opens the graph and decisions for the selected run.
- **Snapshot** downloads a JSON bundle containing the graph, sources, and run evidence. Keep it local if it contains private notes.
- In Obsidian, open `Studio/Runs/<run-id>/Inspect.canvas` to view color-coded node states and explanatory notes.
- Use **Resume** for an interrupted run. If an external provider call was left uncertain, check the outcome with the provider first and reconcile the call in the UI. Authorizing another attempt may incur additional cost.

## Connect Codex, Antigravity, or Claude Code

1. Open **Agents** and keep CanvasGate Studio running.
2. Click **Test bridge** for your chosen client. **Bridge verified** confirms the local bridge responded and read the workspace status.
3. Click **Copy setup**. For Codex and Claude Code, run the copied command in PowerShell and restart the client session. For Antigravity, add the copied entry under `mcpServers` in your MCP configuration and refresh the server list.
4. In your client, ask the agent to confirm the workspace, list workflows, and validate `Studio/Order review.canvas` (or another listed path). **Connected** appears once Studio detects the session.

An MCP-connected agent can validate, simulate, and replay workflows. For live model calls or committing target writes, use the **Run** dialog and review the provider and write options.

## When a run stops

Open the run in **History**, select the first **Failed** node, and read **Decision**. If a Markdown heading is missing, check the heading name in the slice node and the actual text in **Inputs**. If a hash mismatches, inspect the source in **Sources** before updating the contract. After fixing the issue, start a new run to capture the updated sources.
