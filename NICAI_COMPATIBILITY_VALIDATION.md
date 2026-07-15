# NICAI Compatibility Validation (Final)

`ReplayEngine._to_nicai_view()` (unchanged) produces:

```json
{
  "trace_id": "...",
  "observation_id": "...",
  "bucket_id": "...",
  "vessel_candidate": "...",
  "vessel_class": "...",
  "confidence_score": 0.0,
  "knowledge_references": [],
  "runtime_trace": [],
  "schema_version": "svacs-nicai-1.0.0"
}
```

The risk/validation layer (`risk_level`, `validation_status`,
`operator_action_required`) is additive and currently surfaced only via
the wrapper's own return dict and `svacs_service.py`'s
`/api/svacs/process` response — it does not modify the NICAI export
schema, so existing NICAI consumers are unaffected. If NICAI later needs
risk/validation fields, they can be added to `_to_nicai_view()` as a
backward-compatible schema version bump (e.g. `svacs-nicai-1.1.0`).

**Result:** PASS — verified via
`test_svacs_runtime.test_trace_continuity_across_bucket_and_replay`.