---
title: Dispatch policy revision 5
status: superseded
domain: dispatch
revision: 5
---
# Dispatch policy revision 5

## DispatchInput

Excerpt authority (YAML):
```yaml
status: superseded
domain: dispatch
revision: 5
```

ARCHIVE_ONLY: historical dispatch policy snapshot.

Priority is evaluated by revenue descending, then order_id. Orders may be split across trucks. Each truck may reload for a second departure and may use its full capacity again after reloading. The north zone is served by T1, and T1 accepts frozen freight. Held orders may ship if revenue is positive. There is no duplicate-SKU or cancellation check in this historical plan.

#### Historical operating procedure
Dispatchers first total the full order book and place high-value east-zone orders on T1. Frozen orders use the same vehicle as chilled orders under the equipment assumptions in this revision. North-zone orders take precedence over west-zone orders with equal revenue. A vehicle returning from its first trip can be loaded again. Revenue is recognized for each partial shipment rather than for the entire accepted order. Warehouse staff reserve oversize loads for the second trip when needed. The fleet and order snapshots from this revision contain the corresponding historical assumptions.

