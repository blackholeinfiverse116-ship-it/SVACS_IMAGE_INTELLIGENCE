"""
Task 4 - Explainable Intelligence Generator

Produces an operator-friendly explanation. An operator should be able to
understand why a classification was produced without reading source code.
"""
from typing import List, Optional
from .models import Observation, MaritimeReasoningResult, ConfidenceBreakdown, ExplainableIntelligence


class ExplainabilityGenerator:

    def generate(self, observation: Observation, reasoning: MaritimeReasoningResult,
                 confidence: ConfidenceBreakdown,
                 lineage_reference: Optional[str] = None) -> ExplainableIntelligence:

        supporting_evidence: List[str] = []
        if observation.entities:
            e = observation.entities[0]
            supporting_evidence.append(f"Primary detected entity: {e.name} ({e.entity_type})")
            if e.ocr_text:
                supporting_evidence.append(f"OCR text observed: {', '.join(e.ocr_text)}")
            if e.bounding_box:
                supporting_evidence.append("Bounding box captured for spatial reference")
        supporting_evidence.append(f"Observation source: {observation.observation_source}")

        knowledge_refs = [m.reference for m in reasoning.knowledge_matches] or [
            "No confirmed knowledge base reference"
        ]

        runtime_trace = [
            f"trace_id={observation.trace_id}",
            f"observation_id={observation.observation_id}",
            "stage=StructuredIntelligenceConsumer:complete",
            "stage=MaritimeReasoningEngine:complete",
            "stage=ConfidenceRefinementEngine:complete",
            "stage=ExplainabilityGenerator:complete",
        ]

        return ExplainableIntelligence(
            trace_id=observation.trace_id,
            observation_id=observation.observation_id,
            candidate_vessel=reasoning.candidate_vessel,
            candidate_class=reasoning.candidate_class,
            confidence=confidence.final_confidence,
            supporting_evidence=supporting_evidence,
            maritime_reasoning=reasoning.reasoning_narrative,
            knowledge_references=knowledge_refs,
            runtime_trace=runtime_trace,
            lineage_reference=lineage_reference,
        )