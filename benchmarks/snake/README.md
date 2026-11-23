# Snake Lab

Three independently generated Three.js snakes from one English modeling brief, compared using
identical rendering and playback. States: slow, fast, attack, sleep, sit and death. Sit is an upright
coiled rest, with no limbs or chair. The interface and task documents are in English.

## Open the existing results

Double-click `Snake-Lab.cmd` in the project root, or run from that root:

```powershell
python -m canvasgate.snake_preview --open
```

The viewer is at http://127.0.0.1:8873/. Leave its terminal/server running. If already running, the
launcher reuses it. The six state buttons control all three models together. Drag each viewport
to orbit, scroll to zoom, pause or scrub time, and reset all cameras to their shared initial view.
Sources, token totals and browser checks are available from the viewer. No external CDN is needed.

## Reproduce generation

```powershell
python -m canvasgate.snake_benchmark --prepare-only
python -m canvasgate.snake_benchmark
```

Preparation writes twelve Obsidian notes and a Canvas under `examples/vault/SnakeBenchmark`.
Generation makes three real independent Codex CLI calls with gpt-6.1-sol and medium reasoning.
It consumes account quota. Each model returns a complete ES module with the same createSnake
contract. Raw events, exact prompts, source code, usage and the input corpus are retained in
`runs/<run-id>/`; `latest.json` points the viewer to the newest result.

- Direct: all twelve notes, including six superseded designs and three unrelated departments.
- Obsidian selection: three current notes chosen manually.
- CanvasGate: the actual graph checks status=current and domain=snake3d, then slices SnakeInput.

The three original source modules are never manually changed to improve the comparison.
There are no hidden repair calls. Model output size and reasoning can outweigh input savings.
This is one sample per workflow, not a reliability or artistic-quality ranking.

## Rendering dependencies and verification

On another machine, first run `npm install` inside `benchmarks/snake`; the lockfile pins Three.js.
The preview command copies the required module/core/OrbitControls assets into the local vendor folder.

With Python Playwright and its Chromium installed, start the server, then run from the project root:

```powershell
python -m canvasgate.snake_verify
```

Verification checks JavaScript syntax, loads the originals in Chromium, tests all six states and
captures six screenshots. Checks include deterministic shuffled transitions, finite geometry,
stage scale, sampled motion, death stillness, attack extension, sit elevation, stable resource
counts and geometry/material disposal. State distinctness is measured across multiple times,
including the attack peak, so an attack's recovered pose is not mistaken for a missing state.
The geometric fast/slow activity ratio is a proxy, not an exact frequency measurement.

Results are written to the run's `COMPARISON.md`, `browser-checks.json`, `static-checks.json` and
`screenshots/`. A copy of the report is visible in Obsidian as `SnakeBenchmark/Results.md`.
Modeling style, anatomy, details and animation appeal still require visual inspection.
