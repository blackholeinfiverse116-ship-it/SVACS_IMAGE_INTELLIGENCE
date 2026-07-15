"""
SVACS Maritime Intelligence Runtime - Shared Data Models
Owner: Ankita (SVACS Convergence Sprint)

These models define the CANONICAL internal representation used by every
SVACS runtime stage. External producers (Samachar / Vision Runtime / AIS
feeds / manual operator entry) are normalized into these models by the
Structured Intelligence Consumer (see consumer.py). No downstream stage
talks directly to an upstream schema — this preserves a single runtime
path per Task 1's acceptance criteria.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

ObservationSource = Literal["image", "ais", "manual"]


class BoundingBox(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class RawEntity(BaseModel):
    """A single detected/observed candidate entity, already normalized
    from whichever upstream schema produced it."""
    entity_id: str
    name: str
    entity_type: str
    raw_confidence: float
    bounding_box: Optional[BoundingBox] = None
    ocr_text: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    """Canonical structured intelligence unit consumed by SVACS."""
    trace_id: str
    observation_id: str
    timestamp: str
    observation_source: ObservationSource
    upstream_source_type: str
    entities: List[RawEntity]
    upstream_confidence: float
    supporting_evidence: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1.0.0"


class KnowledgeMatch(BaseModel):
    reference: str
    matched_field: str
    match_strength: float
    detail: str


class MaritimeReasoningResult(BaseModel):
    candidate_vessel: Optional[str]
    candidate_class: Optional[str]
    reasoning_narrative: List[str]
    knowledge_matches: List[KnowledgeMatch]
    evidence_signals: Dict[str, Any]


class ConfidenceBreakdown(BaseModel):
    vision_confidence: float
    knowledge_adjustment: float
    ais_adjustment: float
    manual_adjustment: float
    dimension_adjustment: float
    final_confidence: float
    rationale: List[str]


class ExplainableIntelligence(BaseModel):
    trace_id: str
    observation_id: str
    candidate_vessel: Optional[str]
    candidate_class: Optional[str]
    confidence: float
    supporting_evidence: List[str]
    maritime_reasoning: List[str]
    knowledge_references: List[str]
    runtime_trace: List[str]
    lineage_reference: Optional[str] = None


class SVACSIntelligenceRecord(BaseModel):
    """Final persisted, replayable, dashboard/NICAI-facing record."""
    trace_id: str
    observation_id: str
    bucket_id: str
    created_at: str
    observation: Observation
    reasoning: MaritimeReasoningResult
    confidence: ConfidenceBreakdown
    explainable: ExplainableIntelligence
    replay_safe: bool = True