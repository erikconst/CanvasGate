# Three.js snake comparison

Run: `20261030T072558Z-f2a184cd`. Three.js r186. Same English brief, model gpt-6.1-sol and medium reasoning.

Required animations: slow, fast, attack, sleep, sit (upright coiled rest), death.

| Variant | Input | Cached input | Output | Total | Generation seconds | Browser checks |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Codex direct — complete packet | 13824 | 0 | 4294 | 18118 | 101.251 | 17/17 |
| Obsidian — selected notes | 12425 | 0 | 4890 | 17315 | 151.063 | 17/17 |
| CanvasGate + Obsidian — gated slices | 12913 | 0 | 4956 | 17869 | 87.745 | 17/17 |

CanvasGate versus direct: 1.37% fewer total tokens (negative means more).
Total reported generation tokens: 53,302.

## Scope

- Three independently generated source modules. They share only the host renderer, lighting, camera, time and test harness.
- Variant 1 received all 12 notes; variant 2 received three manually selected current notes; variant 3 used the actual CanvasGate YAML gates and section slicer to select the three current snake3d notes.
- All model outputs, exact prompts, real CLI usage events and measurements are retained. One generation invocation per variant; no hidden model repairs or manual source fixes are included.
- The browser checks measure module integration, deterministic poses, resource stability and selected animation properties. They do not prove artistic quality, exact temporal frequency, realistic biomechanics, all performance limits or full absence of per-frame heap allocations.
- Fast/slow activity is a sampled world/geometry motion proxy, not a direct frequency measurement. Named head positions are used for attack/sit checks.
- State distinctness compares trajectories at t=0.17, 0.35, 0.73 and 1.7, including the attack peak. An earlier single-instant check falsely flagged a recovered attack as equal to slow; the harness was corrected for all three original modules, without model edits or additional model calls.
- One sample per approach is not a reliability estimate. Context packaging can influence model implementation choices and output lengths.
- Total = input + output; cached input is a subset of input. Output includes generated JavaScript and reasoning. Development, this chat, dependency setup and deterministic verification are excluded.

## Browser checks

### Codex direct — complete packet

- PASS — Six declared states
- PASS — Required factory contract
- PASS — Named head and body
- PASS — Renderable model
- PASS — Finite geometry in all six states
- PASS — Model fits common stage scale
- PASS — Vertex budget
- PASS — Deterministic state transitions: Same time/state after shuffled calls
- PASS — Six distinct animation trajectories: Includes strike peak and recovery; a recovered attack may share a slow pose at one instant
- PASS — Slow and fast animate
- PASS — Fast motion exceeds slow: Observed motion ratio 2.76×; geometric proxy, not direct frequency measurement
- PASS — Sleep is quieter than slow
- PASS — Death becomes static
- PASS — Forward attack lunge
- PASS — Sit raises the head
- PASS — Stable mesh and resource counts
- PASS — Owned resources disposed

Measurements:

```json
{
  "slow_motion": 0.003880774442182428,
  "fast_motion": 0.010698990094619438,
  "sleep_motion": 3.0252239621611095e-05,
  "fast_slow_ratio": 2.756921396493906,
  "attack_extension": 0.7623777756727201,
  "sit_elevation": 0.9632534949063052
}
```

### Obsidian — selected notes

- PASS — Six declared states
- PASS — Required factory contract
- PASS — Named head and body
- PASS — Renderable model
- PASS — Finite geometry in all six states
- PASS — Model fits common stage scale
- PASS — Vertex budget
- PASS — Deterministic state transitions: Same time/state after shuffled calls
- PASS — Six distinct animation trajectories: Includes strike peak and recovery; a recovered attack may share a slow pose at one instant
- PASS — Slow and fast animate
- PASS — Fast motion exceeds slow: Observed motion ratio 2.76×; geometric proxy, not direct frequency measurement
- PASS — Sleep is quieter than slow
- PASS — Death becomes static
- PASS — Forward attack lunge
- PASS — Sit raises the head
- PASS — Stable mesh and resource counts
- PASS — Owned resources disposed

Measurements:

```json
{
  "slow_motion": 0.002823152267861071,
  "fast_motion": 0.007792829966668523,
  "sleep_motion": 2.269948786177282e-05,
  "fast_slow_ratio": 2.7603293153481485,
  "attack_extension": 0.8600001335144043,
  "sit_elevation": 0.910285010933876
}
```

### CanvasGate + Obsidian — gated slices

- PASS — Six declared states
- PASS — Required factory contract
- PASS — Named head and body
- PASS — Renderable model
- PASS — Finite geometry in all six states
- PASS — Model fits common stage scale
- PASS — Vertex budget
- PASS — Deterministic state transitions: Same time/state after shuffled calls
- PASS — Six distinct animation trajectories: Includes strike peak and recovery; a recovered attack may share a slow pose at one instant
- PASS — Slow and fast animate
- PASS — Fast motion exceeds slow: Observed motion ratio 2.79×; geometric proxy, not direct frequency measurement
- PASS — Sleep is quieter than slow
- PASS — Death becomes static
- PASS — Forward attack lunge
- PASS — Sit raises the head
- PASS — Stable mesh and resource counts
- PASS — Owned resources disposed

Measurements:

```json
{
  "slow_motion": 0.0025063383032051917,
  "fast_motion": 0.006991715460148124,
  "sleep_motion": 3.143452104933529e-05,
  "fast_slow_ratio": 2.789613617286572,
  "attack_extension": 0.8599999999999999,
  "sit_elevation": 0.968333392373253
}
```

## Browser errors

```json
[]
```

## Visual captures

- screenshots/slow.png
- screenshots/fast.png
- screenshots/attack.png
- screenshots/sleep.png
- screenshots/sit.png
- screenshots/death.png

The host opens at http://127.0.0.1:8873/ when python -m canvasgate.snake_preview is running.
