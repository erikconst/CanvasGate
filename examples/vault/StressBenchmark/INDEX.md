# Contradictory archive stress test

30 notes: 3 current dispatch inputs, 18 contradictory historical revisions, and 9 current departmental notes.

## Authoritative notes for manual selection

- [[Current-policy]]
- [[Current-fleet]]
- [[Current-orders]]

[[workflow.canvas|Open the YAML-filtered Canvas]]

[[Results/COMPARISON|Read the measured comparison]]

The full-context baseline receives the same rule about current dispatch sources as every other variant. A baseline PASS is a valid result. No outcome is selected or hidden.

Reproduce: `python -m canvasgate.stress_benchmark`. This makes three real CLI calls per repetition. Use `--prepare-only` for fixtures only. API transport requires `--transport api --model MODEL` and OPENAI_API_KEY configured outside the vault. Never put credentials in notes.
