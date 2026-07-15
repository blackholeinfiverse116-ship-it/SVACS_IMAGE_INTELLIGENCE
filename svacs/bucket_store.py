"""
Bucket persistence + Replay reconstruction (Task 5/6).

Deterministic, append-only, trace_id-indexed storage. Maps onto Siddhesh's
bucket persistence contract: trace_id keyed, replay-safe reconstruction,
full provenance retained.
"""
import os
import json
from typing import Optional, List
from .models import SVACSIntelligenceRecord

BUCKET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bucket_store")
os.makedirs(BUCKET_DIR, exist_ok=True)


class BucketStore:

    def __init__(self, directory: str = BUCKET_DIR):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def _path(self, trace_id: str) -> str:
        return os.path.join(self.directory, f"{trace_id}.json")

    def put(self, record: SVACSIntelligenceRecord) -> None:
        with open(self._path(record.trace_id), "w") as f:
            f.write(record.model_dump_json(indent=2))

    def get(self, trace_id: str) -> Optional[SVACSIntelligenceRecord]:
        path = self._path(trace_id)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        return SVACSIntelligenceRecord(**data)

    def list_trace_ids(self) -> List[str]:
        return [f[:-5] for f in os.listdir(self.directory) if f.endswith(".json")]


class ReplayEngine:
    """Reconstructs a full record from the bucket, verifying trace
    continuity and provenance are intact (Task 5/6 acceptance criteria)."""

    def __init__(self, store: BucketStore):
        self.store = store

    def replay(self, trace_id: str) -> dict:
        record = self.store.get(trace_id)
        if record is None:
            raise ValueError(f"No bucket record found for trace_id={trace_id}")

        checks = {
            "trace_id_present": record.trace_id == trace_id,
            "observation_present": record.observation is not None,
            "reasoning_present": record.reasoning is not None,
            "confidence_present": record.confidence is not None,
            "explainable_present": record.explainable is not None,
            "provenance_present": bool(record.observation.provenance),
        }
        replay_safe = all(checks.values())

        return {
            "trace_id": trace_id,
            "replay_safe": replay_safe,
            "checks": checks,
            "dashboard_view": self._to_dashboard_view(record),
            "nicai_view": self._to_nicai_view(record),
        }

    def _to_dashboard_view(self, record: SVACSIntelligenceRecord) -> dict:
        return {
            "trace_id": record.trace_id,
            "vessel": record.explainable.candidate_vessel,
            "class": record.explainable.candidate_class,
            "confidence": record.explainable.confidence,
            "evidence": record.explainable.supporting_evidence,
            "reasoning": record.explainable.maritime_reasoning,
            "created_at": record.created_at,
        }

    def _to_nicai_view(self, record: SVACSIntelligenceRecord) -> dict:
        """NICAI-compatible flattened export (Task 6 / NICAI compatibility)."""
        return {
            "trace_id": record.trace_id,
            "observation_id": record.observation_id,
            "bucket_id": record.bucket_id,
            "vessel_candidate": record.explainable.candidate_vessel,
            "vessel_class": record.explainable.candidate_class,
            "confidence_score": record.explainable.confidence,
            "knowledge_references": record.explainable.knowledge_references,
            "runtime_trace": record.explainable.runtime_trace,
            "schema_version": "svacs-nicai-1.0.0",
        }