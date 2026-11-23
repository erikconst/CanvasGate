# Current dispatch policy
Status: CURRENT; version: 2.0; authoritative for this benchmark.

1. Reject status=cancelled with reason `cancelled` and status=hold with reason `on_hold`.
2. For active orders, identify trucks serving that order's zone. If none, reject `unsupported_zone`.
3. Within those trucks, filter by supported temperature. If none, reject `unsupported_temperature`.
4. Process the remaining active orders in ascending (priority, deadline_hour, order_id). Priority 1 is highest.
5. For each order, examine compatible trucks in ascending truck_id. Assign it to the FIRST truck for which
   adding its weight AND volume would not exceed the truck's remaining capacity. Equality is allowed.
6. Never split an order, move a previous assignment, or search for a better solution. If no truck fits, reject `capacity`.
7. Each truck has one departure; capacities are cumulative over this one batch. There are no reloads.
8. Sum revenue only for assigned orders. Sort the final output lists as requested in the task.

Use only this current policy, the current fleet, and the current orders. Other notes are background or obsolete.
