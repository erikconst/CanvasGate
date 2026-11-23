---
title: Dispatch fleet revision 2
status: superseded
domain: dispatch
revision: 2
---
# Dispatch fleet revision 2

## DispatchInput

Excerpt authority (YAML):
```yaml
status: superseded
domain: dispatch
revision: 2
```

ARCHIVE_ONLY
[
  {
    "truck_id": "T1",
    "weight_kg": 1700,
    "volume_m3": 12,
    "zones": [
      "east",
      "west",
      "north"
    ],
    "temperatures": [
      "ambient",
      "chilled",
      "frozen"
    ]
  },
  {
    "truck_id": "T2",
    "weight_kg": 800,
    "volume_m3": 5,
    "zones": [
      "east",
      "west"
    ],
    "temperatures": [
      "ambient"
    ]
  },
  {
    "truck_id": "T3",
    "weight_kg": 1000,
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
