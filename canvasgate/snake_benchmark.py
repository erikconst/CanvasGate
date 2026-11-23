"""Generate three independent procedural Three.js snakes and preserve real usage.

python -m canvasgate.snake_benchmark --prepare-only
python -m canvasgate.snake_benchmark
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .backends import CodexBackend, WorkflowError, validate_response
from .benchmark import MODEL, VAULT, write_json
from .canvasgate import CanvasGateWorkflow


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks/snake"
FIXTURE = VAULT / "SnakeBenchmark"
STATES = ["slow", "fast", "attack", "sleep", "sit", "death"]
CURRENT = ["Model.md", "Animations.md", "Contract.md"]
TASK = (
    "Create a polished, cohesive procedural 3D snake in JavaScript for Three.js r186. "
    "Use only the current snake3d specification and honor its module contract and all six animation states. "
    "Current notes have YAML status=current and domain=snake3d; selected excerpts repeat those authority fields. "
    "Superseded rules and other domains are irrelevant. Return outer JSON with status, confidence, text. "
    "The text must be the COMPLETE JavaScript ES module source, without Markdown fences or explanations. "
    "No imports: the renderer passes THREE to createSnake. No file changes, tools, network, DOM, timers or random calls. "
    "One independent implementation; do not refer to another variant. Keep the source compact, preferably under 300 lines."
)

SPECS = {
    "Model.md": """### Visual model
Create a recognizable, attractive stylized emerald viper with a continuous-looking, smoothly tapered
body, a pointed tail, a broad rounded triangular head, two golden eyes with dark pupils, a pale lime
belly and a visible forked tongue during attack. Add an economical dorsal scale/chevron pattern.
No external textures or assets. Model only the snake: no stage, floor, lights, camera or renderer.
The shared viewer supplies a dark studio, soft lighting, shadows and perspective camera.
The snake faces positive Z, its head is at the positive-Z end. Ground is y=0. Keep its root at the origin.
Use units: total body length roughly 5, maximum thickness 0.32, rest head center at y about 0.4.
The full model must fit inside x/z [-4,4] and y [-0.1,3]. Use smooth overlapping tapered segments
or a continuous deforming tube; avoid a visible chain of disconnected beads. At least 24 body sections
if segmented. Keep below 100,000 total vertices. Name the head object 'snake-head' and a body mesh or
body container 'snake-body'. Eyes must be visually closed or covered in sleep and death.
Use reusable geometries/materials. Do not allocate objects, meshes, materials, curves or geometries in update.
""",
    "Animations.md": """### Six required animation states
Use deterministic absolute time, not accumulated frame deltas. Calling update(t,state) in any order
must produce the same pose for the same t and state, including after changing between states.
Reset every modified transform, opacity, visibility and deformation as needed on each update.

- slow: relaxed continuous serpentine locomotion, a traveling lateral wave, subtle head motion.
- fast: clearly faster traveling wave, at least twice the slow temporal frequency with comparable amplitude.
- attack: a repeating 2-second strike. At t=0 the head is at its ready position; it lunges at least 0.5 units
  along +Z near t=0.35, mouth/tongue visible, and recovers before t=1.2. Coil/bracing is welcome.
- sleep: a compact horizontal coil on the floor, closed eyes, almost still except very subtle breathing.
- sit: a stable resting coil with the head raised at least 0.5 units above its sleeping head height.
  This is a snake's upright rest, with no legs or chair. Tiny idle motion is optional.
- death: a short collapse to a clearly distinct low, limp pose. Once t>=1.5, the pose is completely static
  and the eyes are closed. Do not make dead snakes continue undulating or breathing.

All six states must be visually distinct. Continuous loops are only slow, fast, sleep and idle sit;
attack repeats every two seconds. An invalid state can default safely to slow.
""",
    "Contract.md": """### Exact ES module contract
Export exactly the public names needed by this host:

export const states = ['slow','fast','attack','sleep','sit','death'];
export function createSnake(THREE) {
  // Build and own all geometry/material resources once here.
  const root = new THREE.Group();
  function update(timeSeconds, state) { /* deterministic absolute pose; reset transforms */ }
  function dispose() { /* dispose all unique geometries and materials owned by this snake */ }
  return { root, update, dispose };
}

The host calls update(absoluteTimeSeconds, state) every frame and attaches root to its scene.
Do not import THREE. Do not create a WebGLRenderer, scene, camera, lights or animation loop.
Do not access document/window, fetch, WebSocket, eval, dynamic imports, Math.random, Date, setTimeout,
setInterval, or filesystem APIs. Use only THREE, pure JavaScript, Math and local closure state.
No additional dependencies. Avoid deprecated Three.js APIs. Every material/geometry you create must
be released in dispose(), including reusable objects no longer attached to root. One shared viewer
renders all three variants with identical framing. Tests sample poses in shuffled state/time order,
check finite world-space points, distinct poses, slow/fast motion, death stillness, attack extension,
head elevation in sit, stable resource counts and geometry/material disposal. These are engineering
checks, not proof of artistic quality. Use mesh.castShadow=true and receiveShadow=true where useful.
""",
}


def note(title, status, domain, content):
    return (f"---\ntitle: {title}\nstatus: {status}\ndomain: {domain}\n---\n# {title}\n\n"
            f"## SnakeInput\n\nExcerpt authority: status={status}; domain={domain}.\n\n{content}\n")


def prepare():
    FIXTURE.mkdir(parents=True, exist_ok=True)
    notes = {name: note(name[:-3], "current", "snake3d", text) for name, text in SPECS.items()}
    historical = [
        ("Old-gltf.md", "A previous proposal loaded a remote glTF snake and compressed textures. It did not support procedural geometry or offline rendering."),
        ("Old-animation.md", "The old prototype supported only idle, walk and run. It accumulated dt, used Math.random per frame and restarted a timer on each state change."),
        ("Old-api.md", "The retired host expected buildSnake(scene), imported THREE from a CDN and created a private renderer inside each model module."),
        ("Old-sit.md", "The abandoned mascot design had four small legs and sat on a chair. It faced negative X and was 25 units long."),
        ("Old-death.md", "An old demo displayed a red snake for death but kept the walking wave running indefinitely. Sleep used wide-open eyes."),
        ("Old-materials.md", "The retired art test used a flat magenta wireframe with no belly, eyes, scales or tongue. The review asked for one large cylinder."),
    ]
    for name, content in historical:
        notes[name] = note(name[:-3], "superseded", "snake3d", content)
    for domain in ("marketing", "finance", "events"):
        notes[f"{domain.title()}.md"] = note(domain.title(), "current", domain,
            f"The {domain} team tracks milestones, budgets, stakeholders and review meetings. This note does not change the snake model or renderer contract.")
    for name, content in notes.items():
        (FIXTURE / name).write_text(content, encoding="utf-8")
    nodes, edges = [], []

    def text(key, value, x, y, width=320, height=150):
        nodes.append(dict(id=key, type="text", text=value, x=x, y=y, width=width, height=height))

    def edge(source, target, label=""):
        edges.append(dict(id=f"e{len(edges)}", fromNode=source, fromSide="right", toNode=target, toSide="left", label=label))

    for i, name in enumerate(notes):
        key, y = f"source-{i:02d}", i * 220
        nodes.append(dict(id=key, type="file", file="SnakeBenchmark/" + name, x=0, y=y, width=320, height=170))
        text(key + "-status", "GATE: YAML_EQ:status=current", 420, y)
        text(key + "-domain", "GATE: YAML_EQ:domain=snake3d", 840, y)
        text(key + "-slice", "SLICE: SECTION:SnakeInput", 1260, y)
        edge(key, key + "-status")
        edge(key + "-status", key + "-domain", "true")
        edge(key + "-status", "excluded", "false")
        edge(key + "-domain", key + "-slice", "true")
        edge(key + "-domain", "excluded", "false")
        edge(key + "-slice", "selected")
    text("excluded", "JOIN: ANY", 1700, len(notes) * 220)
    text("selected", "JOIN: ANY", 1700, 0)
    text("model", "AGENT:\n" + json.dumps({"prompt": TASK, "max_retries": 0}), 2120, 0, 500, 400)
    text("output", "OUTPUT: Procedural snake module", 2740, 0)
    edge("selected", "model")
    edge("model", "output")
    write_json(FIXTURE / "workflow.canvas", {"nodes": nodes, "edges": edges})
    (FIXTURE / "INDEX.md").write_text(
        "# Three.js snake benchmark\n\nCompare three independent implementations of one English brief.\n\n"
        "Required states: slow, fast, attack, sleep, sit (upright coiled rest), death.\n\n"
        "## Current notes\n" + "\n".join(f"- [[{name[:-3]}]]" for name in CURRENT)
        + "\n\n[[workflow.canvas|Open the gated context selection]]\n\n[[Results|Read measured results]]\n\n"
        "The browser viewer uses identical lighting, camera and time for all three models. Automated checks are not an artistic-quality oracle.\n",
        encoding="utf-8")
    return notes


def run_variant(number, notes, directory, timeout):
    stage = directory / f"{number:02d}"
    stage.mkdir()
    backend = CodexBackend(MODEL, timeout, "medium", stage / "events")
    error, response, report = None, None, None
    try:
        if number < 3:
            context = {name: {"status": True, "confidence": 1, "text": text}
                       for name, text in notes.items() if number == 1 or name in CURRENT}
            response = backend.generate(TASK, context, [])
        else:
            report = CanvasGateWorkflow(FIXTURE / "workflow.canvas", VAULT).run(backend, max_calls=1, max_context_chars=24000)
            write_json(stage / "workflow-report.json", report)
            result = report["nodes"]["model"]
            response = {key: result[key] for key in ("status", "confidence", "text")}
            if report["outcome"] != "completed":
                raise WorkflowError(report["abort_reason"])
        validate_response(response)
        if not response["status"]:
            raise WorkflowError("Model returned status=false.")
        source = response["text"].strip()
        if source.startswith("```"):
            raise WorkflowError("Module was fenced instead of raw JavaScript.")
        (stage / "snake.mjs").write_text(source + "\n", encoding="utf-8")
    except WorkflowError as exc:
        error = str(exc)
    write_json(stage / "response.json", response)
    metrics = {"variant": number, "model": MODEL, "usage": backend.token_usage(), "generation_error": error,
               "elapsed_seconds": round(sum(run.get("elapsed_seconds") or 0 for run in backend.runs), 3), "attempts": len(backend.runs)}
    if report:
        metrics["selected_sources"] = sum(n["state"] == "EXECUTED" for key, n in report["nodes"].items() if key.endswith("-slice"))
    write_json(stage / "measurement.json", metrics)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error("Timeout must be 1–900 seconds.")
    notes = prepare()
    if args.prepare_only:
        print(FIXTURE / "workflow.canvas")
        return 0
    directory = OUTPUT / "runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    directory.mkdir(parents=True)
    write_json(directory / "corpus.json", [{"name": name, "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text} for name, text in notes.items()])
    write_json(directory / "configuration.json", {"model": MODEL, "reasoning_effort": "medium", "task": TASK, "states": STATES})
    results = []
    for number in (1, 2, 3):
        print(f"Generating snake {number}/3 ({MODEL}, medium)...", flush=True)
        result = run_variant(number, notes, directory, args.timeout)
        results.append(result)
        write_json(directory / "measurements.json", results)
        print(json.dumps(result), flush=True)
    manifest = {"run": directory.name, "states": STATES, "models": results, "generated_at": datetime.now(timezone.utc).isoformat()}
    write_json(OUTPUT / "latest.json", manifest)
    print(f"Generated modules: {directory}", flush=True)
    return 0 if all(r["generation_error"] is None for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
