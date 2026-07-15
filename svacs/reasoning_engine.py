"""
Task 2 - Maritime Intelligence Reasoning Engine

Extends the vision/AIS/manual-derived observation with maritime domain
knowledge so SVACS output is evidence-backed, not a restatement of the
raw upstream label.

IMPORTANT: `evidence_signals["knowledge_verified"]` reflects strictly
whether an actual Jane's Fighting Ships / knowledge-base match (`kb_match`)
was found for the observed entity. It must NOT be inferred from whether a
candidate vessel name exists — AIS and manual observations always resolve
*some* candidate name from their own payload (MMSI-reported name / operator
-reported name), but that is a different, weaker signal than a confirmed
knowledge-base match, and is already scored separately by
svacs/confidence_engine.py via ais_adj / manual_adj. Conflating the two
previously caused manual/AIS observations to receive an undeserved
knowledge-base confidence bonus.
"""
from typing import List
from .models import Observation, MaritimeReasoningResult, KnowledgeMatch
from . import knowledge_base as kb


class MaritimeReasoningEngine:

    def reason(self, observation: Observation) -> MaritimeReasoningResult:
        narrative: List[str] = []
        knowledge_matches: List[KnowledgeMatch] = []
        candidate_vessel = None
        candidate_class = None
        evidence_signals = {}

        primary_entity = observation.entities[0] if observation.entities else None
        if primary_entity is None:
            narrative.append("No entities present in observation; reasoning skipped.")
            return MaritimeReasoningResult(
                candidate_vessel=None, candidate_class=None,
                reasoning_narrative=narrative, knowledge_matches=[],
                evidence_signals={"knowledge_verified": False},
            )

        narrative.append(
            f"Upstream layer classified the primary entity as '{primary_entity.name}' "
            f"({primary_entity.entity_type}) with raw confidence "
            f"{primary_entity.raw_confidence:.2f}."
        )

        # ------------------------------------------------------------------
        # Knowledge-base corroboration is determined ONLY by an actual
        # kb_match against Jane's Fighting Ships / fleet-history data. This
        # is the single source of truth for "knowledge_verified" — it must
        # not be conflated with fallback candidate naming below.
        # ------------------------------------------------------------------
        kb_match = None
        if primary_entity.ocr_text:
            kb_match = kb.lookup_all_ocr_candidates(primary_entity.ocr_text)
            if kb_match:
                narrative.append(
                    f"OCR text on hull/superstructure matched knowledge base entry "
                    f"'{kb_match['reference_key']}' (operator: {kb_match.get('operator')})."
                )
                knowledge_matches.append(KnowledgeMatch(
                    reference=kb_match["reference_key"],
                    matched_field="ocr_text",
                    match_strength=0.9,
                    detail=f"Vessel identity string '{kb_match['reference_key']}' found in observed OCR text.",
                ))
                candidate_vessel = kb_match["reference_key"]
                candidate_class = kb_match.get("class")

        knowledge_verified = kb_match is not None

        # ------------------------------------------------------------------
        # Source-specific candidate naming. This is a fallback identity
        # signal, independent of knowledge-base corroboration. Its strength
        # (or weakness) is scored separately in the confidence engine via
        # ais_adj / manual_adj, NOT via knowledge_adj.
        # ------------------------------------------------------------------
        if observation.observation_source == "ais":
            candidate_vessel = candidate_vessel or primary_entity.name
            candidate_class = candidate_class or primary_entity.entity_type
            narrative.append(
                f"AIS-derived observation: MMSI {primary_entity.metadata.get('mmsi')} "
                f"correlated directly to reported vessel identity."
            )
            evidence_signals["ais_mmsi"] = primary_entity.metadata.get("mmsi")

        if observation.observation_source == "manual":
            candidate_vessel = candidate_vessel or primary_entity.name
            candidate_class = candidate_class or primary_entity.entity_type
            narrative.append(
                "Manual operator report treated as corroborating, lower-confidence evidence."
            )

        if candidate_vessel is None:
            candidate_vessel = primary_entity.name
            candidate_class = primary_entity.entity_type
            narrative.append(
                "No maritime knowledge base match found; falling back to upstream "
                "classification. Flagged UNVERIFIED against Jane's Fighting Ships / "
                "fleet-history data."
            )

        if not knowledge_verified:
            narrative.append(
                "No knowledge base corroboration found for this candidate identity; "
                "confidence will reflect an unverified classification."
            )

        evidence_signals["knowledge_verified"] = knowledge_verified
        if knowledge_verified and kb_match:
            evidence_signals["dimensions_m"] = kb_match.get("dimensions_m")
            evidence_signals["fleet_history"] = kb_match.get("fleet_history")
            evidence_signals["lineage"] = kb_match.get("lineage")
            evidence_signals["role"] = kb_match.get("role")

        return MaritimeReasoningResult(
            candidate_vessel=candidate_vessel,
            candidate_class=candidate_class,
            reasoning_narrative=narrative,
            knowledge_matches=knowledge_matches,
            evidence_signals=evidence_signals,
        )