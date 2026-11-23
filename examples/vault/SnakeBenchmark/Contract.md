---
title: Contract
status: current
domain: snake3d
---
# Contract

## SnakeInput

Excerpt authority: status=current; domain=snake3d.

### Exact ES module contract
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

