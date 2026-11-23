# CanvasGate Studio for Windows

Run `CanvasGate-Studio-Setup.exe` (from GitHub Releases or built locally into `dist/`) on Windows x64. Setup installs per user and creates shortcuts on the Desktop and in Start. The package includes Python and the CanvasGate engine. The native window uses the Microsoft Edge WebView2 Runtime installed on Windows. Setup is unsigned.

Open **CanvasGate Studio** and use **Open vault** to select an existing Obsidian vault. The app starts with a separate Demo Vault. The installer preserves user data across upgrades and uninstall.

Open **Help & guides** to read or download the [user guide](../canvasgate/docs/USER_GUIDE.md) and the [project walkthrough](../canvasgate/docs/HOW_IT_WORKS.md).

The **Agents** tab has a connection card for Codex, Antigravity and Claude Code. Use **Test bridge** to check transport and **Copy setup** to connect each client. The embedded MCP server supports local Streamable HTTP and stable stdio commands that forward to the currently open desktop app.

- [Instructions for users](../canvasgate/MCP_USER_GUIDE.md)
- [Instructions for agents](../canvasgate/MCP_AGENT_GUIDE.md)

## Build locally

Use Windows x64 with the .NET Framework 4.8 compiler, traditional x64 CPython 3.14 and the project dependencies plus Pillow. Download the official Microsoft.Web.WebView2 NuGet package version `1.0.2903.40`. Build from the repository root.

```powershell
python -m pip install -e . pillow
python desktop/build.py path/to/Microsoft.Web.WebView2.1.0.2903.40.nupkg
```

The build checks the SDK SHA-256 and writes `dist/CanvasGate-Studio-Setup.exe`. Preserve the matching engine version when reproducing a prior snapshot.
