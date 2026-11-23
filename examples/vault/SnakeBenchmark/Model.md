---
title: Model
status: current
domain: snake3d
---
# Model

## SnakeInput

Excerpt authority: status=current; domain=snake3d.

### Visual model
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

