---
title: Current fleet
status: current
domain: dispatch
revision: 20
---
# Current fleet

## DispatchInput

Excerpt authority (YAML):
```yaml
status: current
domain: dispatch
revision: 20
```

[
  {
    "truck_id": "T1",
    "weight_kg": 1000,
    "volume_m3": 6,
    "zones": [
      "east",
      "west"
    ],
    "temperatures": [
      "ambient",
      "chilled"
    ]
  },
  {
    "truck_id": "T2",
    "weight_kg": 800,
    "volume_m3": 5,
    "zones": [
      "east"
    ],
    "temperatures": [
      "ambient"
    ]
  },
  {
    "truck_id": "T3",
    "weight_kg": 600,
    "volume_m3": 4,
    "zones": [
      "west"
    ],
    "temperatures": [
      "ambient",
      "chilled"
    ]
  }
]
