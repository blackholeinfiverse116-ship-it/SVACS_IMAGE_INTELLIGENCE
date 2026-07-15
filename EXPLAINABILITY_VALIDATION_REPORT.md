# Explainability Validation Report (Final)

**Method:** Inspected the combined output of `SVACSRuntime.process()` and
`intelligence.vessel_intelligence_engine.process_intelligence()` for each
observation source (image/AIS/manual).

| Field | Source | Present | Human-readable |
|---|---|---|---|
| candidate_vessel / vessel_candidate | svacs.explainability | ✅ | ✅ |
| candidate_class / vessel_class | svacs.explainability | ✅ | ✅ |
| confidence / confidence_score | svacs.confidence_engine | ✅ | ✅ |
| supporting_evidence / evidence_chain | svacs.explainability | ✅ | ✅ |
| maritime_reasoning / explanation | svacs.explainability | ✅ | ✅ |
| knowledge_references | svacs.explainability | ✅ | ✅ |
| runtime_trace | svacs.explainability | ✅ | ✅ |
| lineage_reference | svacs.reasoning_engine | ✅ (nullable) | ✅ |
| risk_level | intelligence wrapper (new) | ✅ | ✅ |
| validation_status | intelligence wrapper (new) | ✅ | ✅ |
| operator_action_required | intelligence wrapper (new) | ✅ | ✅ |

**Result:** PASS — an operator reading only the wrapper's returned dict
can determine what was identified, why, how confident SVACS is, and
whether it requires action, without inspecting source code.