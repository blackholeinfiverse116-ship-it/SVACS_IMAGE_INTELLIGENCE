"""
Task 3 - Confidence Refinement Engine

Refines raw upstream confidence using available maritime evidence:
knowledge base matches, dimensions, fleet history, lineage, AIS
correlation, and manual operator corroboration. The final confidence
represents SVACS maritime reasoning, not raw vision confidence alone.
"""
from .models import Observation, MaritimeReasoningResult, ConfidenceBreakdown


class ConfidenceRefinementEngine:

    KNOWLEDGE_BONUS = 0.15
    DIMENSION_BONUS = 0.05
    AIS_BONUS = 0.20
    MANUAL_PENALTY = -0.05
    UNVERIFIED_PENALTY = -0.10

    def refine(self, observation: Observation,
               reasoning: MaritimeReasoningResult) -> ConfidenceBreakdown:
        rationale = []
        base = observation.upstream_confidence
        rationale.append(f"Base (upstream) confidence: {base:.2f}")

        knowledge_adj = dimension_adj = ais_adj = manual_adj = 0.0

        if reasoning.evidence_signals.get("knowledge_verified"):
            knowledge_adj = self.KNOWLEDGE_BONUS
            rationale.append(f"+{knowledge_adj:.2f} knowledge base match confirmed vessel identity")
            if reasoning.evidence_signals.get("dimensions_m"):
                dimension_adj = self.DIMENSION_BONUS
                rationale.append(f"+{dimension_adj:.2f} vessel dimensions on record support classification")
        else:
            knowledge_adj = self.UNVERIFIED_PENALTY
            rationale.append(f"{knowledge_adj:.2f} no knowledge base corroboration found (unverified)")

        if observation.observation_source == "ais":
            ais_adj = self.AIS_BONUS
            rationale.append(f"+{ais_adj:.2f} AIS correlation available (high-trust source)")

        if observation.observation_source == "manual":
            manual_adj = self.MANUAL_PENALTY
            rationale.append(f"{manual_adj:.2f} manual operator report only (lower certainty than sensor fusion)")

        final = max(0.0, min(1.0, round(base + knowledge_adj + dimension_adj + ais_adj + manual_adj, 4)))
        rationale.append(f"Final SVACS maritime confidence: {final:.2f}")

        return ConfidenceBreakdown(
            vision_confidence=base,
            knowledge_adjustment=knowledge_adj,
            ais_adjustment=ais_adj,
            manual_adjustment=manual_adj,
            dimension_adjustment=dimension_adj,
            final_confidence=final,
            rationale=rationale,
        )