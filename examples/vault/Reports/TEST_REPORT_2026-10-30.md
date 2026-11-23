# Consolidated test report — CanvasGate

**Reporting date:** 30 October 2026. **Test period:** 29–30 October 2026.

**Scope:** every saved benchmark, integration run, failed attempt, local test suite and browser check performed in this project so far.

## 1. Executive findings

- The final dispatch and modeling comparisons each produced valid results for all three approaches. No experiment demonstrated an inevitable baseline failure from contradictory notes.
- Deterministic filtering saved the most tokens when the excluded corpus was large: **50.32%** against the full 30-note packet. The small dispatch and Three.js examples saved **3.55%** and **1.37%** respectively.
- Manual note selection used fewer tokens than CanvasGate in all three final comparisons. CanvasGate automated selection, conditional routing and validation; the results do not establish a token advantage over careful manual selection.
- All three generated snakes passed **17/17 engineering checks** after a shared test-harness correction. This is not an artistic-quality ranking.
- The saved measurement ledger contains **14 metered external Codex CLI invocations** and **285,873 reported tokens**, including **81,436** from two unsuccessful task attempts. One earlier successful real invocation has no saved token usage and is additional to this total. An external invocation can contain several internal provider requests; that internal request count was not measured separately.
- The current deterministic regression suite passed **60/60 tests**. Direct API benchmarking has not been executed; claims about sub-1,500-token API results remain unverified.

## 2. Accounting and comparison method

The three workflows are: **Direct** (full supplied packet), **Obsidian selection** (manually curated current notes exported into the prompt), and **CanvasGate** (local graph selects context before the model call). Obsidian itself does not make or reduce model calls.

All final comparisons used independent Codex CLI sessions, `gpt-6.1-sol`, and medium reasoning. The initial unmetered smoke test used the CLI default model, whose identity was not preserved. No previous model answer was included in a later comparison's input.

Token usage comes from saved provider/CLI counters. **Total = input + output.** Cached input is already included in input; reasoning is already included in output. Missing usage is unknown, never estimated from characters or treated as zero. Counters include model-side setup/instructions/schema overhead and any internal interactions reported by the CLI.

The totals exclude development, fixture preparation, dependency installation, deterministic Python tests, browser verification and visual inspection. They are neither a final invoice nor a measurement of subscription-quota percentage. Cache effects mean equal gross token totals would not necessarily have equal monetary cost.

Each final workflow has one measured sample per task. Differences in generated code, reasoning and stochastic model behavior can outweigh small input savings. These are practical workflow comparisons, not isolated causal or statistical estimates of Obsidian's effect.

## 3. Final comparison at a glance

| Test | Direct total | Obsidian selection | CanvasGate total | CanvasGate vs direct | Final quality |
| --- | ---: | ---: | ---: | ---: | --- |
| Dispatch, 6 notes | 13,991 | 13,254 | 13,494 | 3.55% fewer | 3/3 exact PASS |
| Dispatch, 30 notes | 28,499 | 13,689 | 14,157 | 50.32% fewer | 3/3 exact PASS |
| Three.js snake | 18,118 | 17,315 | 17,869 | 1.37% fewer | 17/17 browser checks each |

## 4. Test A — initial MVP smoke runs

The first local example summarized a Markdown brief after checking word limits, approval and confidence. A mock run verified wiring with no model tokens. One real Codex call completed successfully before usage instrumentation was added.

| Run | Outcome | Real model calls | Saved usage |
| --- | --- | ---: | --- |
| Initial mock | completed | 0 (simulated) | 0 model tokens |
| Initial real summary | completed | 1 | **Unavailable** |

The initial brief was Romanian; later tasks, notes, benchmark interfaces and generated artifacts were switched to English. The early real run must not be assigned an invented token count.

Initial real report (`runs/20261029T150149Z-bbd43db138/report.json`)

There are **4 saved successful mock runs** in total: the initial smoke, two Obsidian-vault wiring runs, and the CanvasGate simulation. Each used one simulated agent attempt and zero external model calls/tokens. Unit-test mock calls are separate and also make no external model requests.

- runs/20261029T150131Z-9d114a6206/report.json (`runs/20261029T150131Z-9d114a6206/report.json`): completed, 1 simulated attempt.
- examples/vault/CanvasGate/Runs/20261029T154407Z-2a45908bf3/report.json (`examples/vault/CanvasGate/Runs/20261029T154407Z-2a45908bf3/report.json`): completed, 1 simulated attempt.
- examples/vault/Rezultate/20261029T150937Z-26d5572b56/report.json (`examples/vault/Rezultate/20261029T150937Z-26d5572b56/report.json`): completed, 1 simulated attempt.
- examples/vault/Rezultate/20261029T151151Z-80124da020/report.json (`examples/vault/Rezultate/20261029T151151Z-80124da020/report.json`): completed, 1 simulated attempt.

## 5. Test B — medium-complexity dispatch, 6 notes

**Task:** assign 14 orders to 3 trucks with priority/deadline ordering, zone and temperature compatibility, cumulative weight/volume capacities, cancellation/hold rejection and exact revenue totals. Three authoritative notes and three excluded background/historical notes were available.

**Quality oracle:** exact assignments, rejection reasons, per-truck loads and revenue. Final results matched seven assignments, seven rejections, loads T1=1,000 kg/6 m³, T2=750 kg/5 m³, T3=600 kg/4 m³, and revenue 1,610.

| Variant | Input | Cached input* | Output | Reasoning* | Total | Seconds | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Direct | 13,581 | 0 | 410 | 118 | **13,991** | 13.534 | PASS |
| Obsidian selection | 12,821 | 0 | 433 | 141 | **13,254** | 14.065 | PASS |
| CanvasGate | 13,115 | 0 | 379 | 85 | **13,494** | 11.042 | PASS |

**Failed preliminary attempt:** the original second workflow asked the agent to read INDEX.md. Automatic approval review rejected both read attempts (`Get-Content` and `type`) as `blocked by policy`. The session returned no dispatch result and consumed **67,784 tokens**, including 45,568 cached input tokens. The zero completed-tool count does not mean there were no rejected attempts.

The organized variant was repeated by supplying manually selected notes directly. Actual order was Direct → organized read attempt (blocked) → gated → manual organized retry. The blocked attempt is excluded from the successful comparison table but included in experiment spend.

**Successful samples:** 40,739 tokens. **Whole experiment including the blocked attempt:** 108,523 tokens.

[Detailed comparison](../Benchmark/Results/20261029T151949Z/COMPARISON.md) · [Blocked attempt evidence](../Benchmark/Results/20261029T151949Z/02-blocked/events/call-001.stderr.txt)

## 6. Test C — contradictory archive, 30 notes

**Corpus:** 3 current dispatch notes, 18 superseded fleet/policy/order snapshots, and 9 current departmental notes from unrelated domains. Historical snapshots contradicted current temperature support, capacities, order states and dispatch rules. The corrected corpus contained 48,571 characters; this is a size description, not a token estimate.

All variants received the same authority rule: `status=current` AND `domain=dispatch`. CanvasGate evaluated those checks locally, excluded 27 notes, sliced the three accepted sections and made one model call. The dispatch oracle was unchanged.
### Initial fixture round — retained, not counted as a clean final comparison

| Variant | Input | Cached input* | Output | Reasoning* | Total | Seconds | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Direct | 27,190 | 0 | 444 | 152 | **27,634** | 11.827 | PASS |
| Obsidian selection | 13,767 | 0 | 380 | 88 | **14,147** | 9.571 | PASS |
| CanvasGate | 13,429 | 0 | 223 | 157 | **13,652** | 12.033 | FAIL |

The gated run failed because a `#` heading imported inside `## DispatchInput` ended the selected section. The agent received no dispatch policy and returned status=false. This was a fixture/context starvation defect, not evidence that the baseline was better at the underlying dispatch logic.

The fixture was corrected by nesting headings and retaining authority fields in excerpts. A minimum-word gate now rejects an empty selected section before a model call. All three variants were repeated on the corrected corpus; earlier answers were not included in their inputs.
### Corrected fixture — final comparison

| Variant | Input | Cached input* | Output | Reasoning* | Total | Seconds | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Direct | 28,076 | 0 | 423 | 131 | **28,499** | 11.079 | PASS |
| Obsidian selection | 13,304 | 0 | 385 | 93 | **13,689** | 9.222 | PASS |
| CanvasGate | 13,776 | 0 | 381 | 87 | **14,157** | 8.108 | PASS |

CanvasGate used **50.32% fewer** total tokens than full context. Baseline reasoning was 131 tokens versus 87 for CanvasGate, not a demonstrated doubling. All three matched the oracle; no context-induced baseline quality failure was observed in this sample.

**Initial round:** 55,433 tokens. **Corrected round:** 56,345 tokens. **Both rounds:** 111,778 tokens.

[Initial round](../StressBenchmark/Results/20261029T160003Z-7a07214f/COMPARISON.md) · [Corrected comparison](../StressBenchmark/Results/20261029T160336Z-5ecee342/COMPARISON.md)

## 7. Test D — CanvasGate architecture integration

The architectural example used YAML approval, a SECTION slice, a character limit, separate implementation/review branches, JOIN, staging and a final Markdown write. The mock execution committed a clearly simulated result. A real execution produced an English implementation plan for a pure Python order-validation function.

The real plan covered container and field validation, booleans versus integers, duplicate SKUs, integer totals, non-mutation and boundary cases. This was an integration smoke test and a manual plan inspection, not an exhaustive correctness proof of generated application code.

| Variant | Input | Cached input* | Output | Reasoning* | Total | Seconds | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CanvasGate integration | 11,961 | 11,264 | 309 | 0 | **12,270** | 15.097 | COMMITTED |

Real outcome: **COMMITTED**, one accepted output file. Mock outcome: **COMMITTED**, zero model tokens. Source fingerprints and traces were saved. Recovery guarantees are per-file replacement with journaling/rollback, not simultaneous atomic visibility across multiple files.

Real integration audit (`examples/vault/CanvasGate/Runs/20261029T154433Z-e138a36597/RunReport.md`) · [Architecture and recovery guarantees](../../../CANVASGATE.md)

## 8. Test E — Three.js snake modeling and animation

**Task:** independently create a procedural emerald snake with a tapered body, head, eyes, belly and forked tongue, using Three.js r186.1. Required states: slow, fast, attack, sleep, sit and death. Sit means an upright coiled resting pose, not a chair or limbs.

All three modules were generated from the same English brief using gpt-6.1-sol/medium, with no shared generated source. The packet contained 12 notes: 3 current specifications, 6 retired designs and 3 unrelated department notes. The shared viewer supplied identical rendering, camera and time. There were no hidden model repair calls or manual changes to the generated modules.

| Variant | Input | Cached input* | Output | Reasoning* | Total | Seconds | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Direct | 13,824 | 0 | 4,294 | 1,002 | **18,118** | 101.251 | 17/17 browser checks |
| Obsidian selection | 12,425 | 0 | 4,890 | 1,410 | **17,315** | 151.063 | 17/17 browser checks |
| CanvasGate | 12,913 | 0 | 4,956 | 1,379 | **17,869** | 87.745 | 17/17 browser checks |

CanvasGate reduced input by 911 tokens versus Direct, but produced 662 more output tokens. Net reduction was **249 tokens / 1.37%**. This illustrates why context reduction does not guarantee a similarly large reduction in total tokens for code generation. Total generation usage was **53,302 tokens**.
### Browser verification

The original modules were syntax-checked with Node and loaded in local Chromium. Browser errors: **0**. Each model passed all 17 final checks:

- Six declared states.
- Required factory contract.
- Named head and body.
- Renderable model.
- Finite geometry in all six states.
- Model fits common stage scale.
- Vertex budget.
- Deterministic state transitions.
- Six distinct animation trajectories.
- Slow and fast animate.
- Fast motion exceeds slow.
- Sleep is quieter than slow.
- Death becomes static.
- Forward attack lunge.
- Sit raises the head.
- Stable mesh and resource counts.
- Owned resources disposed.

The initial state-distinctness check sampled one time after the attack had recovered, incorrectly flagging variant 3 as equal to slow. The shared harness was corrected to compare trajectories at 0.17, 0.35, 0.73 and 1.7 seconds. All original model sources were retained and no additional model calls were made. The host camera/lighting was also refined equally for all variants.

Six screenshots per model comparison were captured. Slow, attack, sit, sleep and death captures were inspected during development; fast behavior was measured and captured. The fast/slow ratio is a sampled geometric motion proxy, not an exact frequency measurement. Tests do not prove artistic quality, realistic biomechanics, every performance limit or the absence of all per-frame heap allocations.

| Variant | Fast/slow motion proxy | Attack extension (+Z units) | Sit head elevation (units) |
| --- | ---: | ---: | ---: |
| Direct | 2.76× | 0.762 | 0.963 |
| Obsidian selection | 2.76× | 0.860 | 0.910 |
| CanvasGate | 2.79× | 0.860 | 0.968 |

[Interactive viewer](http://127.0.0.1:8873/) — requires the local Snake Lab server. Reopen with [Snake-Lab.cmd](../../../Snake-Lab.cmd).

Full modeling comparison (`benchmarks/snake/runs/20261030T072558Z-f2a184cd/COMPARISON.md`) · Browser evidence (`benchmarks/snake/runs/20261030T072558Z-f2a184cd/browser-checks.json`) · Slow-state capture (`benchmarks/snake/runs/20261030T072558Z-f2a184cd/screenshots/slow.png`)

## 9. Deterministic regression tests

The latest suite was rechecked while compiling this report: `python -m unittest discover -s tests -q` — **60 tests, 0 failures, 0 errors, 1.113 seconds, OK**. These are test methods; subcases/assertions are not counted as additional test methods. Mocked provider interactions make no external AI calls.

| Test module | Test methods | Main coverage |
| --- | ---: | --- |
| [test_benchmark.py](../../../tests/test_benchmark.py) | 4 | Usage parsing, cache accounting, hand-calculated dispatch oracle and detection of an incorrect result |
| [test_canvasgate.py](../../../tests/test_canvasgate.py) | 30 | Typed YAML, slicing, IF/ELSE joins, schemas, providers, staging, conflicts, locks and recovery |
| [test_snake_benchmark.py](../../../tests/test_snake_benchmark.py) | 1 | All animation/module requirements survive context filtering; obsolete snake notes are excluded |
| [test_stress_benchmark.py](../../../tests/test_stress_benchmark.py) | 2 | Contradictory corpus filtering, complete selected policy, API metrics and credential-free logging |
| [test_workflow.py](../../../tests/test_workflow.py) | 23 | Original graph validation, gating, routing, context exclusion, retries, budgets, files and CLI reports |

Important transaction tests inject write errors, KeyboardInterrupt-style interruption, rollback errors and external file edits. They verify recovery and conflict handling, but are not physical power-loss tests or proof of serializable isolation from external editors.

Historical suite sizes progressed through 21, 23, 27, 53, 57, 59 and 60 as functionality was added. These are successive snapshots, not counts that should be added together.

## 10. Complete measured-call ledger

Each row below is one metered external Codex CLI invocation, not necessarily one internal provider request. Rows are grouped by experiment, not ordered chronologically. Successful rows repeated after a fixture correction remain consumed work; no failed or repeated call is removed from this ledger.

| # | Experiment / phase | Variant | Total tokens | Outcome |
| ---: | --- | --- | ---: | --- |
| 1 | Dispatch: 6 notes / final | Direct | 13,991 | PASS |
| 2 | Dispatch: 6 notes / final | Obsidian selection | 13,254 | PASS |
| 3 | Dispatch: 6 notes / final | CanvasGate | 13,494 | PASS |
| 4 | Dispatch: 6 notes / blocked preliminary attempt | Obsidian selection | 67,784 | FAIL |
| 5 | Dispatch: 30 notes / initial fixture | Direct | 27,634 | PASS |
| 6 | Dispatch: 30 notes / initial fixture | Obsidian selection | 14,147 | PASS |
| 7 | Dispatch: 30 notes / initial fixture | CanvasGate | 13,652 | FAIL |
| 8 | Dispatch: 30 notes / corrected fixture | Direct | 28,499 | PASS |
| 9 | Dispatch: 30 notes / corrected fixture | Obsidian selection | 13,689 | PASS |
| 10 | Dispatch: 30 notes / corrected fixture | CanvasGate | 14,157 | PASS |
| 11 | CanvasGate integration / real smoke test | Integration | 12,270 | COMMITTED |
| 12 | Three.js snake / final | Direct | 18,118 | ENGINEERING PASS |
| 13 | Three.js snake / final | Obsidian selection | 17,315 | ENGINEERING PASS |
| 14 | Three.js snake / final | CanvasGate | 17,869 | ENGINEERING PASS |

| Token category | Sum across 14 metered invocations |
| --- | ---: |
| Input, including cached input | 267,730 |
| Cached input — subset, not additional | 56,832 |
| Uncached input | 210,898 |
| Output, including reasoning | 18,143 |
| **Total input + output** | **285,873** |
| Failed-attempt tokens — subset of total | 81,436 |

This is the **known metered total**, not the complete historical project total: the early successful real summary call is unmetered and additional. Actual historical usage therefore exceeds the known total by an unknown amount. Development costs are also outside this ledger.

## 11. Not executed or not established

- **Direct Responses API comparison:** prepared but not executed. No OPENAI_API_KEY was configured when checked. API calls were tested only using mocked responses; no live API usage was measured.
- **Five serial micro-agents via CLI versus API:** not executed. A claimed 60,000-token CLI setup or a sub-1,500-token API result is not an observed benchmark result.
- **Exact CLI system-prompt overhead:** not separately measured. Earlier roughly 12k-input runs included more than source notes; they cannot be labeled entirely as system instructions.
- **Inevitable baseline failure under stale rules:** not observed. Direct runs passed both final dispatch benchmarks.
- **Statistically reliable savings or failure rate:** not established from one final sample per workflow/task.
- **Artistic superiority of a snake:** not established by the engineering checks. Use the interactive viewer to assess appearance and animation appeal.
- **Global multi-file atomic visibility, physical power-loss durability or full sandbox read isolation:** not established; see the architecture's explicit guarantees and limitations.

## 12. Conclusions

1. The strongest measured token saving came from removing a large irrelevant/obsolete corpus, while preserving correct task context.
2. The fixture failure demonstrates the complementary risk: slicing too aggressively can remove essential rules. Context completeness needs its own checks.
3. CanvasGate's demonstrated value is deterministic orchestration, bounded calls, inspectable routing, source filtering and recoverable writes. It does not replace a semantic quality oracle.
4. In the code-generation task, output length and reasoning nearly offset the input saving. Compare complete task cost and quality, not input size alone.
5. Manual selection was cheapest in these final samples; automation should be evaluated alongside the human selection effort and consistency it replaces.
6. The next meaningful transport comparison requires a configured API key, matched models/tasks and actual provider usage, with repeated samples and equivalent quality checks.

## Appendix — local test inventory

All methods below belong to the latest 60/60 passing snapshot:

- `test_benchmark.MeasurementTests.test_missing_usage_is_unavailable_not_zero`
- `test_benchmark.MeasurementTests.test_oracle_matches_hand_calculated_dispatch`
- `test_benchmark.MeasurementTests.test_quality_check_detects_wrong_load_even_with_confidence_one`
- `test_benchmark.MeasurementTests.test_usage_events_are_recorded_and_cache_is_not_double_counted`
- `test_canvasgate.CanvasGateTests.test_backend_capabilities_checked_before_any_calls`
- `test_canvasgate.CanvasGateTests.test_cli_dry_run_and_transactional_preview`
- `test_canvasgate.CanvasGateTests.test_code_only_validates_python_syntax_before_forwarding`
- `test_canvasgate.CanvasGateTests.test_context_limit_and_transport_failure_stop_without_retry`
- `test_canvasgate.CanvasGateTests.test_critical_false_gate_discards_previously_staged_write`
- `test_canvasgate.CanvasGateTests.test_exact_switch_labels_are_case_sensitive`
- `test_canvasgate.CanvasGateTests.test_factory_preserves_legacy_graphs`
- `test_canvasgate.CanvasGateTests.test_false_yaml_route_preserves_payload_for_review`
- `test_canvasgate.CanvasGateTests.test_if_else_join_executes_only_active_branch`
- `test_canvasgate.CanvasGateTests.test_invalid_graphs_and_paths_are_preflight_errors`
- `test_canvasgate.CanvasGateTests.test_join_all_requires_all_branches_any_does_not`
- `test_canvasgate.CanvasGateTests.test_lines_and_yaml_typed_slices`
- `test_canvasgate.CanvasGateTests.test_missing_slice_never_calls_agent`
- `test_canvasgate.CanvasGateTests.test_preview_and_duplicate_run_id_do_not_append_twice`
- `test_canvasgate.CanvasGateTests.test_recovery_required_is_reported_when_rollback_also_fails`
- `test_canvasgate.CanvasGateTests.test_retry_budget_and_json_validation`
- `test_canvasgate.CanvasGateTests.test_shared_budget_prevents_second_agent`
- `test_canvasgate.CanvasGateTests.test_source_edit_during_agent_prevents_stale_commit`
- `test_canvasgate.CanvasGateTests.test_yaml_section_boundary_does_not_send_unrelated_context`
- `test_canvasgate.MarkdownTests.test_section_skips_fenced_code_headings_and_ambiguity`
- `test_canvasgate.MarkdownTests.test_typed_yaml_and_duplicate_keys`
- `test_canvasgate.ProviderTests.test_router_aggregates_codex_and_api_usage_without_network`
- `test_canvasgate.TransactionTests.test_committed_transaction_cannot_be_crash_rolled_back`
- `test_canvasgate.TransactionTests.test_crash_recovery_restores_partial_commit_and_is_repeatable`
- `test_canvasgate.TransactionTests.test_lock_serializes_writers`
- `test_canvasgate.TransactionTests.test_mid_commit_os_error_restores_both_originals`
- `test_canvasgate.TransactionTests.test_new_file_removed_when_later_write_fails`
- `test_canvasgate.TransactionTests.test_recovery_does_not_overwrite_external_edit`
- `test_canvasgate.TransactionTests.test_staging_conflict_never_overwrites_external_edit`
- `test_canvasgate.TransactionTests.test_staging_is_memory_only_and_combines_mutations_in_order`
- `test_snake_benchmark.SnakeBenchmarkTests.test_gates_preserve_all_animation_and_contract_requirements`
- `test_stress_benchmark.StressBenchmarkTests.test_api_retains_real_usage_reasoning_and_never_logs_credentials`
- `test_stress_benchmark.StressBenchmarkTests.test_corpus_contains_actual_conflicts_and_typed_filtering_removes_them`
- `test_workflow.BackendTests.test_api_incomplete_response_is_failure`
- `test_workflow.BackendTests.test_api_sends_no_tools_history_or_vault_access`
- `test_workflow.BackendTests.test_cli_argv_uses_stdin_and_separate_temporary_cwd`
- `test_workflow.WorkflowTests.test_cli_dry_run_and_report`
- `test_workflow.WorkflowTests.test_closed_gate_makes_zero_calls`
- `test_workflow.WorkflowTests.test_context_limit_blocks_before_call`
- `test_workflow.WorkflowTests.test_cycle_rejected_before_execution`
- `test_workflow.WorkflowTests.test_example_canvas`
- `test_workflow.WorkflowTests.test_file_vault_boundary`
- `test_workflow.WorkflowTests.test_gate_checks_and_not`
- `test_workflow.WorkflowTests.test_global_budget_is_shared_by_distinct_model_nodes`
- `test_workflow.WorkflowTests.test_global_budget_overrides_retries`
- `test_workflow.WorkflowTests.test_invalid_config_is_preflight_error`
- `test_workflow.WorkflowTests.test_invalid_edges_and_duplicate_ids`
- `test_workflow.WorkflowTests.test_markdown_file_source`
- `test_workflow.WorkflowTests.test_not_cannot_revive_skipped_branch`
- `test_workflow.WorkflowTests.test_retry_exhaustion_never_publishes_failed_output`
- `test_workflow.WorkflowTests.test_retry_has_feedback_and_stops_at_valid_response`
- `test_workflow.WorkflowTests.test_routing_does_not_increase_confidence`
- `test_workflow.WorkflowTests.test_schema_rejects_nan_bool_confidence_and_extras`
- `test_workflow.WorkflowTests.test_success_forwards_only_selected_context`
- `test_workflow.WorkflowTests.test_transport_error_is_not_retried`
- `test_workflow.WorkflowTests.test_zero_budget_never_calls_model`

## Evidence and reproducibility

[Machine-readable consolidated ledger and source hashes](../../../reports/test_measurements_2026-10-30.json)

Saved source JSON files are hashed in that ledger. The report builder reads existing artifacts only; it makes no model or network calls. Rebuild from the project root with `python reports/build_test_report.py`.

Official token-accounting reference: [OpenAI token counting](https://developers.openai.com/api/docs/guides/token-counting).
