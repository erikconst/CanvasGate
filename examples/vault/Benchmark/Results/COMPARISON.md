# Measured token comparison

English medium-complexity dispatch task: 14 orders, 3 trucks.

Model: `gpt-6.1-sol`. Reasoning effort: `medium`. One fresh session per invocation.

| Variant | Input | Cached input (subset) | Uncached input | Output | Total | Seconds | Completed tool calls | Exact result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Direct Codex — full packet | 13581 | 0 | 13581 | 410 | 13991 | 13.534 | 0 | PASS |
| Obsidian — manually selected notes | 12821 | 0 | 12821 | 433 | 13254 | 14.065 | 0 | PASS |
| Obsidian + CanvasGate — gated context | 13115 | 0 | 13115 | 379 | 13494 | 11.042 | 0 | PASS |

## Comparison with direct run

- Variant 2: +5.27% fewer total tokens than variant 1 (negative = more tokens).
- Variant 3: +3.55% fewer total tokens than variant 1 (negative = more tokens).

## Blocked preliminary attempt (included in experiment spend)

Actual execution order: 1 → 2 (blocked) → 3 → 2 (manual export fallback). The successful second variant was rerun after the third; previous answers were never supplied as input.
Automatic approval review rejected the initial second variant's attempts to read INDEX.md using Get-Content and type as `blocked by policy`. That session returned no dispatch result. Completed-tool counts do not include those rejected attempts.
The blocked attempt consumed **67,784 reported tokens**. Its full events and response are preserved in `02-blocked/`.
Successful samples plus the blocked attempt consumed **108,523 reported tokens** in total. The main table compares only successful, quality-checked samples; the blocked attempt is not evidence that Obsidian itself is expensive.

## Method and limits

- These are CLI-reported turn usage counters from raw `turn.completed` events, not character-based estimates.
- Total = input + output. Cached input is already included in input; it is not added again.
- Full run usage includes intermediate model/tool interactions. Output can include hidden reasoning; visible answer length is not a token count.
- Variant 1 receives all six source notes as a direct prompt. Variant 2 receives a manual export of the three notes selected using the Obsidian index, without Canvas gates or model file reads. Variant 3 uses the actual Canvas engine to gate out three irrelevant/superseded notes, then sends the same three authoritative notes as context without model file reads.
- Obsidian itself makes no model call. Savings come from context selection and avoided agent interactions; the app alone has no token-reduction mechanism.
- This compares three practical workflows, not an isolated causal effect of Obsidian. Input packaging and tool availability differ intentionally. Curating the index and Canvas required setup work.
- Exactly one sample per variant; no statistical claim. Execution order and cache reuse can affect counters, latency and billing. Cached tokens are reported separately; token totals are not monetary cost or subscription-quota percentages.
- Confidence 1.0 is not a quality measurement; quality PASS means the complete structured result matched the independent local oracle.
- Benchmark fixture preparation, this chat, and test-harness development are excluded. Runtime retries, if any, are included; each variant is limited to one external Codex invocation in this benchmark.
- All outputs are checked locally against an independent deterministic oracle for assignments, rejection reasons, loads and revenue. No model judge is used.
- Raw events, exact prompts, responses and measurement JSON are stored beside this report in 01/, 02/ and 03/. Earlier results are never included in the next variant's context.

## Expected result

```json
{
  "assignments": [
    {
      "order_id": "O01",
      "truck_id": "T1"
    },
    {
      "order_id": "O02",
      "truck_id": "T3"
    },
    {
      "order_id": "O03",
      "truck_id": "T2"
    },
    {
      "order_id": "O04",
      "truck_id": "T1"
    },
    {
      "order_id": "O06",
      "truck_id": "T2"
    },
    {
      "order_id": "O07",
      "truck_id": "T3"
    },
    {
      "order_id": "O08",
      "truck_id": "T1"
    }
  ],
  "rejected": [
    {
      "order_id": "O05",
      "reason": "capacity"
    },
    {
      "order_id": "O09",
      "reason": "capacity"
    },
    {
      "order_id": "O10",
      "reason": "unsupported_zone"
    },
    {
      "order_id": "O11",
      "reason": "unsupported_temperature"
    },
    {
      "order_id": "O12",
      "reason": "cancelled"
    },
    {
      "order_id": "O13",
      "reason": "on_hold"
    },
    {
      "order_id": "O14",
      "reason": "capacity"
    }
  ],
  "truck_loads": [
    {
      "truck_id": "T1",
      "weight_kg": 1000,
      "volume_m3": 6
    },
    {
      "truck_id": "T2",
      "weight_kg": 750,
      "volume_m3": 5
    },
    {
      "truck_id": "T3",
      "weight_kg": 600,
      "volume_m3": 4
    }
  ],
  "total_revenue": 1610
}
```

Official usage event documentation: https://developers.openai.com/codex/noninteractive
