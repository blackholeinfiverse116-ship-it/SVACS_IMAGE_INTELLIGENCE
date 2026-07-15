"""
SVACS Maritime Intelligence Runtime - Orchestrator

Single deterministic execution path:

Structured Intelligence
    -> Consumer (Task 1)
    -> Reasoning Engine (Task 2)
    -> Confidence Refinement (Task 3)
    -> Explainability Generator (Task 4)
    -> Bucket persistence (Task 5)
    -> Replay-ready record

Every image-derived, AIS-derived, and manual-operator observation flows
through this exact same sequence of stages — no parallel processing paths.
"""
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from .models import SVACSIntelligenceRecord, ObservationSource
from .consumer import StructuredIntelligenceConsumer
from .reasoning_engine import MaritimeReasoningEngine
from .confidence_engine import ConfidenceRefinementEngine
from .explainability import ExplainabilityGenerator
from .bucket_store import BucketStore, ReplayEngine


class SVACSRuntime:

    def __init__(self, bucket_store: Optional[BucketStore] = None):
        self.consumer = StructuredIntelligenceConsumer()
        self.reasoning_engine = MaritimeReasoningEngine()
        self.confidence_engine = ConfidenceRefinementEngine()
        self.explainability_generator = ExplainabilityGenerator()
        self.bucket_store = bucket_store or BucketStore()
        self.replay_engine = ReplayEngine(self.bucket_store)

    def process(self, payload: Dict[str, Any],
                observation_source: Optional[ObservationSource] = None) -> SVACSIntelligenceRecord:
        observation = self.consumer.consume(payload, observation_source=observation_source)
        reasoning = self.reasoning_engine.reason(observation)
        confidence = self.confidence_engine.refine(observation, reasoning)

        bucket_id = f"bucket_{uuid.uuid4().hex}"
        lineage_reference = reasoning.evidence_signals.get("lineage")
        explainable = self.explainability_generator.generate(
            observation, reasoning, confidence, lineage_reference=lineage_reference
        )

        record = SVACSIntelligenceRecord(
            trace_id=observation.trace_id,
            observation_id=observation.observation_id,
            bucket_id=bucket_id,
            created_at=datetime.utcnow().isoformat() + "Z",
            observation=observation,
            reasoning=reasoning,
            confidence=confidence,
            explainable=explainable,
            replay_safe=True,
        )

        self.bucket_store.put(record)
        return record

    def replay(self, trace_id: str) -> dict:
        return self.replay_engine.replay(trace_id)