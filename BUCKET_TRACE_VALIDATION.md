# Bucket Trace Validation (Final)

- Bucket persistence remains trace_id-keyed (`{trace_id}.json`),
  append-only, owned entirely by `svacs/bucket_store.py`.
- The risk/validation wrapper (`intelligence/vessel_intelligence_engine.py`)
  does not write to the bucket itself — it reads the already-persisted
  `SVACSIntelligenceRecord` returned by `SVACSRuntime.process()`, so there
  is exactly one write path into the bucket, preventing duplicate or
  conflicting records for the same trace_id.
- Provenance (`observation.provenance`) is persisted and validated
  non-empty on replay (`provenance_present` check).
- `BucketStore.list_trace_ids()` remains available for audit.

**Result:** PASS.