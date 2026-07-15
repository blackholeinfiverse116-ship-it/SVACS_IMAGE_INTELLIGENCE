# SVACS Maritime Intelligence Runtime — Testing Packet (Final)

## Test Suites

| Suite | Owner scope | What it proves |
|---|---|---|
| `test_ingestion_standalone.py` | Samachar (unchanged, not ours) | Samachar's own ingestion contract |
| `test_svacs_runtime.py` | SVACS core | Deterministic execution, single pipeline, trace continuity, replay safety |
| `test_vessel_intelligence_engine.py` | Risk/validation wrapper | Wrapper delegates correctly, no duplicate reasoning, risk/validation rules |
| `test_svacs_integration_with_samachar.py` | End-to-end | Real Samachar output flows through SVACS with trace_id intact |

## How to Run (from project root)
```powershell
python -m unittest test_svacs_runtime.py -v
python -m unittest test_vessel_intelligence_engine.py -v
python -m unittest test_svacs_integration_with_samachar.py -v
python -m unittest test_ingestion_standalone.py -v
```

## Coverage Matrix

| Requirement | Test |
|---|---|
| Consume image/AIS/manual intelligence, single pipeline | `test_svacs_runtime.test_single_pipeline_convergence` |
| Evidence-backed reasoning, not raw vision restatement | `test_svacs_runtime.test_image_observation_knowledge_match_boosts_confidence` |
| Confidence reflects SVACS reasoning, not raw vision alone | `test_svacs_runtime.test_*_confidence*`, `test_vessel_intelligence_engine.test_unknown_vessel_scores_lower_than_known` |
| Operator-understandable explainability | Assertions on `explainable.*` / wrapper `explanation`/`evidence_chain` fields |
| trace_id continuity, replay-safe reconstruction | `test_svacs_runtime.test_trace_continuity_across_bucket_and_replay`, `test_svacs_integration_with_samachar.test_full_lifecycle_trace_continuity`, `test_vessel_intelligence_engine.test_is_thin_wrapper_preserves_trace_id` |
| Deterministic execution | `test_svacs_runtime.test_deterministic_execution` |
| No duplicate reasoning between wrapper and SVACS | `test_vessel_intelligence_engine.test_no_duplicate_reasoning_output_matches_svacs_directly` |
| Risk assessment (new, non-duplicated capability) | `test_vessel_intelligence_engine.test_risk_level_rules_directly`, `test_submarine_forces_critical_deny`, `test_restricted_zone_forces_critical_deny` |
| Validation gating | `test_vessel_intelligence_engine.test_validation_status_rules_directly` |
| End-to-end operational validation | `test_svacs_integration_with_samachar.py` |

## Expected Results
All suites pass with 0 failures/errors on a clean environment. Bucket
store directories under `test_bucket_store*` are created automatically and
may be deleted between runs for a clean state.