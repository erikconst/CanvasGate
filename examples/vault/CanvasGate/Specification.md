---
title: Order validation service
status: approved
reviewed: true
limits:
  max_items: 100
---
# Background

The business plans to refresh its website and commission a new logo.
These marketing details are unrelated to the API implementation.

## API

Design a pure Python function `validate_order(order)` that accepts a dictionary.
An order must have a non-empty string `customer_id`, and an `items` list containing
between 1 and 100 entries. Every item needs a non-empty string `sku`, an integer
`quantity` from 1 to 50 (booleans must be rejected), and an integer `unit_price_cents`
from 0 to 1,000,000. Duplicate SKUs are invalid.

The result must contain `valid`, `errors`, and `total_cents`. Errors must identify the
field or item index. For invalid orders, `total_cents` is null. For valid orders it is
the sum of quantity times unit price. The input must not be mutated. Do not use a database,
network calls or floating-point arithmetic. Include boundary cases in the test plan.

## Unrelated future work

Payment processing, invoicing, user authentication and mobile applications are outside
this task. They must not be added to the implementation plan.
