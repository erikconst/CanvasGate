# Contradictory archive — measured results

Model: `gpt-6.1-sol`; transport: `cli`; reasoning: `medium`.

Corpus: 30 notes; 48,571 source characters. These character counts are not token estimates.

| Sample | Variant | Input | Cached input | Output | Reasoning (subset) | Total | Seconds | Oracle |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | Full contradictory packet | 28076 | 0 | 423 | 131 | 28499 | 11.079 | PASS |
| 1 | Manually selected Obsidian notes | 13304 | 0 | 385 | 93 | 13689 | 9.222 | PASS |
| 1 | CanvasGate YAML gates + slicing | 13776 | 0 | 381 | 87 | 14157 | 8.108 | PASS |

## Summary

- Variant 1: 1/1 PASS; median total 28499.
- Variant 2: 1/1 PASS; median total 13689.
- Variant 3: 1/1 PASS; median total 14157.
- Observed mean token reduction, gated versus full: 50.32%.
- Reported experiment tokens across all attempts: 56,345.

## Method and limits

- All variants have the identical task and source-authority rule. Same model, medium reasoning, one fresh session and at most one model attempt per sample. All successes and failures are retained.
- The corpus contains six historical fleet/policy/order snapshots with conflicting temperatures, capacities, cancellation states and greedy policies. Nine other departments have current status but the wrong domain. Three authoritative notes are interleaved using a fixed seed.
- Variant 1 gets all notes; variant 2 gets a manually curated three-note packet; variant 3 executes the actual CanvasGate graph, requiring status=current AND domain=dispatch, then extracts DispatchInput sections. Rejected branches are consumed locally and cannot enter the agent context.
- Each excerpt retains the authority fields required by the shared task. A minimum-word gate rejects an empty selected section before any model call. Imported headings are nested beneath DispatchInput.
- The oracle is unchanged from the original benchmark: exact assignments, rejection reasons, loads and revenue. It is not a model judge. Model confidence is not used as a quality score.
- Cached input is already inside input. Reasoning tokens are already inside output. Do not add either subset to total again. Totals do not directly represent money or subscription quota.
- Baseline PASS does not disprove deterministic filtering; baseline FAIL is not guaranteed. Larger excluded context is expected to increase token savings even when both answers are correct.
- With one repetition this is a pilot, not evidence of a reliable failure rate. --repetitions can collect more samples. Sample order is rotated on later repetitions; model output remains stochastic.
- This isolates context filtering with the transport fixed. It does not measure CLI-versus-API overhead. API transport is a separate experiment requiring a configured key and explicit model. No sub-1,500-token claim is made without usage measurements.
- No credential was found for direct API access in the initial environment. The API suite is runnable when OPENAI_API_KEY is configured; it is not silently substituted with a CLI call.
- Raw prompts/events, provider usage, outputs, corpus manifest and full graph traces are retained beside this report. Fixture preparation, this chat and development are excluded from the counters.

Official token accounting: https://developers.openai.com/api/docs/guides/token-counting

## Earlier attempts retained

Earlier run folders: 20261029T160003Z-7a07214f.
Earlier attempts consumed 55,433 reported tokens; all stress-test attempts including this run consumed 111,778.
The initial 20261029T160003Z-7a07214f pilot had a fixture defect: an imported # policy heading terminated the selected ## section. Variant 3 received no dispatch rules and returned status=false. That failed attempt's 13,652 tokens and all other pilot counters remain in its original folder. The corpus was corrected and all three variants rerun; earlier answers were not supplied to models.
