# Connect an agent to CanvasGate Studio

Open CanvasGate Studio from the Desktop or Start menu. Use **Open vault** to choose an Obsidian vault or start with the included **Demo Vault**. Keep the desktop app open while using MCP.

## Codex

Open **Agents → Codex → Copy setup**. Paste the generated `codex mcp add` command into PowerShell. Open a new Codex session or reconnect existing MCP servers.

## Antigravity

Open **Agents → Antigravity → Copy setup**. In Antigravity, open **MCP Servers** and its raw configuration. Merge the `canvasgate-studio` entry inside the existing `mcpServers` object, save, and refresh the MCP server list.

## Claude Code

Open **Agents → Claude Code → Copy setup**. Paste the generated `claude mcp add` command into PowerShell. Open a new Claude Code session and use `/mcp` to check the server.

## Read the connection status

- **Waiting for client** means Studio has yet to observe a session for that connector.
- **Bridge verified** means Studio tested the local MCP command, initialization, discovery, and a status call. It is a local diagnostic.
- **Connected** means Studio observed a recent MCP session after tool discovery. For direct HTTP clients, the indicator expires after a minute without activity. Client names are reported by the client. Reload MCP in the client if it was opened before Studio.

In your agent, ask **“Use CanvasGate MCP to check the workspace, list workflows, and validate Studio/Order review.canvas.”** If using your own vault, choose the workflow path it lists.

Ask to simulate when you want a preview in **History**. Simulation and replay use zero model tokens inside CanvasGate. Your agent client can still use its own model to decide which tools to call.

## Direct Streamable HTTP

For a local client that supports custom HTTP headers, point it to `http://127.0.0.1:<port>/mcp`. The running app writes the current port and bearer token to `%LOCALAPPDATA%\CanvasGateStudio\bridge.json`. Send the token as `Authorization: Bearer <token>` and keep it private. The app changes both when it reopens or switches vaults. Use the generated stdio commands above for stable client settings across restarts.

The built-in server binds to localhost. Connect only clients you trust with access to workflow metadata and run decisions from your current vault.
