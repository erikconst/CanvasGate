---
revision: 3
role: policy
status: approved
---
# Order validation

## Policy

POLICY_ID: order-v3

Validate a pure Python order function. Do not mutate input.
Reject booleans as integers. Reject duplicate SKUs.
Use integer cents, never floating point.
Every order has customer_id and 1-100 items. Each item has sku, quantity 1-50, and unit_price_cents 0-1000000.
Return valid, errors and total_cents. Invalid totals are null.

## Background
Marketing ideas and visual branding do not affect this policy.
