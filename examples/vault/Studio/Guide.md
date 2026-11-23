# CanvasGate Studio

Open **CanvasGate-Studio.cmd** from the project folder, or run:

```powershell
python -m canvasgate.web --vault examples/vault --open
```

The local application is at http://127.0.0.1:8874/. Start with [[Studio/Order review.canvas|Order review]] and choose **Mock** with target writes disabled.

The inspector shows node instructions, explicit context contracts, decisions and saved inputs. Run history contains immutable source/graph snapshots, replay, resume and snapshot downloads. Replay reuses saved model responses and makes no live model calls or target writes.

Each execution creates `Studio/Runs/<run-id>/Inspect.canvas` with Markdown evidence notes. These inspection canvases are read-only evidence and cannot be executed.

Strict mode rejects host Codex CLI because read-only mode is not an OS sandbox. Use mock/API with strict mode. Incomplete external calls require explicit reconciliation before retry; a fresh model call is not guaranteed to reproduce an earlier answer.

Full configuration and recovery instructions: `STUDIO.md` in the project root.
