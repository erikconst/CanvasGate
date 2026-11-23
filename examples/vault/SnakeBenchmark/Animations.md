---
title: Animations
status: current
domain: snake3d
---
# Animations

## SnakeInput

Excerpt authority: status=current; domain=snake3d.

### Six required animation states
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

