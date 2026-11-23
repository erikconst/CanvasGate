# Contradictory archive — measured results

Model: `gpt-6.1-sol`; transport: `cli`; reasoning: `medium`.

Corpus: 30 notes; 45,945 source characters. These character counts are not token estimates.

| Sample | Variant | Input | Cached input | Output | Reasoning (subset) | Total | Seconds | Oracle |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | Full contradictory packet | 27190 | 0 | 444 | 152 | 27634 | 11.827 | PASS |
| 1 | Manually selected Obsidian notes | 13767 | 0 | 380 | 88 | 14147 | 9.571 | PASS |
| 1 | CanvasGate YAML gates + slicing | 13429 | 0 | 223 | 157 | 13652 | 12.033 | FAIL |

## Summary

- Variant 1: 1/1 PASS; median total 27634.
- Variant 2: 1/1 PASS; median total 14147.
- Variant 3: 0/1 PASS; median total 13652.
- Observed mean token reduction, gated versus full: 50.60%.
- Reported experiment tokens across all attempts: 55,433.

## Method and limits

- All variants have the identical task and source-authority rule. Same model, medium reasoning, one fresh session and at most one model attempt per sample. All successes and failures are retained.
- The corpus contains six historical fleet/policy/order snapshots with conflicting temperatures, capacities, cancellation states and greedy policies. Nine other departments have current status but the wrong domain. Three authoritative notes are interleaved using a fixed seed.
- Variant 1 gets all notes; variant 2 gets a manually curated three-note packet; variant 3 executes the actual CanvasGate graph, requiring status=current AND domain=dispatch, then extracts DispatchInput sections. Rejected branches are consumed locally and cannot enter the agent context.
- The oracle is unchanged from the original benchmark: exact assignments, rejection reasons, loads and revenue. It is not a model judge. Model confidence is not used as a quality score.
- Cached input is already inside input. Reasoning tokens are already inside output. Do not add either subset to total again. Totals do not directly represent money or subscription quota.
- Baseline PASS does not disprove deterministic filtering; baseline FAIL is not guaranteed. Larger excluded context is expected to increase token savings even when both answers are correct.
- With one repetition this is a pilot, not evidence of a reliable failure rate. --repetitions can collect more samples. Sample order is rotated on later repetitions; model output remains stochastic.
- This isolates context filtering with the transport fixed. It does not measure CLI-versus-API overhead. API transport is a separate experiment requiring a configured key and explicit model. No sub-1,500-token claim is made without usage measurements.
- No credential was found for direct API access in the initial environment. The API suite is runnable when OPENAI_API_KEY is configured; it is not silently substituted with a CLI call.
- Raw prompts/events, provider usage, outputs, corpus manifest and full graph traces are retained beside this report. Fixture preparation, this chat and development are excluded from the counters.

Official token accounting: https://developers.openai.com/api/docs/guides/token-counting
