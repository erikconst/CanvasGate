---
title: Current orders
status: current
domain: dispatch
revision: 20
---
# Current orders

## DispatchInput

Excerpt authority (YAML):
```yaml
status: current
domain: dispatch
revision: 20
```

[
  {
    "order_id": "O01",
    "priority": 1,
    "deadline_hour": 9,
    "zone": "east",
    "temperature": "chilled",
    "weight_kg": 700,
    "volume_m3": 4,
    "revenue": 500,
    "status": "active"
  },
  {
    "order_id": "O02",
    "priority": 1,
    "deadline_hour": 9,
    "zone": "west",
    "temperature": "chilled",
    "weight_kg": 450,
    "volume_m3": 3,
    "revenue": 350,
    "status": "active"
  },
  {
    "order_id": "O03",
    "priority": 1,
    "deadline_hour": 10,
    "zone": "east",
    "temperature": "ambient",
    "weight_kg": 500,
    "volume_m3": 3,
    "revenue": 220,
    "status": "active"
  },
  {
    "order_id": "O04",
    "priority": 2,
    "deadline_hour": 10,
    "zone": "west",
    "temperature": "ambient",
    "weight_kg": 250,
    "volume_m3": 1,
    "revenue": 180,
    "status": "active"
  },
  {
    "order_id": "O05",
    "priority": 2,
    "deadline_hour": 11,
    "zone": "east",
    "temperature": "chilled",
    "weight_kg": 200,
    "volume_m3": 1,
    "revenue": 160,
    "status": "active"
  },
  {
    "order_id": "O06",
    "priority": 2,
    "deadline_hour": 11,
    "zone": "east",
    "temperature": "ambient",
    "weight_kg": 250,
    "volume_m3": 2,
    "revenue": 140,
    "status": "active"
  },
  {
    "order_id": "O07",
    "priority": 2,
    "deadline_hour": 12,
    "zone": "west",
    "temperature": "chilled",
    "weight_kg": 150,
    "volume_m3": 1,
    "revenue": 130,
    "status": "active"
  },
  {
    "order_id": "O08",
    "priority": 3,
    "deadline_hour": 12,
    "zone": "east",
    "temperature": "ambient",
    "weight_kg": 50,
    "volume_m3": 1,
    "revenue": 90,
    "status": "active"
  },
  {
    "order_id": "O09",
    "priority": 3,
    "deadline_hour": 13,
    "zone": "east",
    "temperature": "ambient",
    "weight_kg": 10,
    "volume_m3": 1,
    "revenue": 30,
    "status": "active"
  },
  {
    "order_id": "O10",
    "priority": 1,
    "deadline_hour": 8,
    "zone": "north",
    "temperature": "ambient",
    "weight_kg": 100,
    "volume_m3": 1,
    "revenue": 100,
    "status": "active"
  },
  {
    "order_id": "O11",
    "priority": 1,
    "deadline_hour": 8,
    "zone": "east",
    "temperature": "frozen",
    "weight_kg": 100,
    "volume_m3": 1,
    "revenue": 100,
    "status": "active"
  },
  {
    "order_id": "O12",
    "priority": 1,
    "deadline_hour": 8,
    "zone": "east",
    "temperature": "ambient",
    "weight_kg": 100,
    "volume_m3": 1,
    "revenue": 100,
    "status": "cancelled"
  },
  {
    "order_id": "O13",
    "priority": 1,
    "deadline_hour": 8,
    "zone": "west",
    "temperature": "ambient",
    "weight_kg": 100,
    "volume_m3": 1,
    "revenue": 100,
    "status": "hold"
  },
  {
    "order_id": "O14",
    "priority": 2,
    "deadline_hour": 10,
    "zone": "west",
    "temperature": "ambient",
    "weight_kg": 1100,
    "volume_m3": 1,
    "revenue": 800,
    "status": "active"
  }
]
