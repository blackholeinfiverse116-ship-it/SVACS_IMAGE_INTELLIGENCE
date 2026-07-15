#!/usr/bin/env python3
"""
intelligence/vessel_intelligence_engine.py

SVACS Maritime Intelligence Runtime — Operational Risk & Validation Layer.

Position in the pipeline:
    Image -> Samachar -> Vision Runtime -> Structured Intelligence
      -> svacs.runtime.SVACSRuntime
           (Structured Intelligence Consumer   -- Task 1)
           (Maritime Intelligence Reasoning     -- Task 2)
           (Confidence Refinement               -- Task 3)
           (Explainable Intelligence            -- Task 4)
           (Bucket persistence                  -- Task 5)
      -> [THIS MODULE: risk assessment + validation gating]
      -> Replay -> Dashboard -> NICAI

This module is a thin wrapper around svacs.runtime.SVACSRuntime.process().
It performs no consumption, classification, confidence blending, or
explanation generation of its own — all of that is delegated to svacs/.
It adds only operational risk assessment and validation gating, which has
no equivalent anywhere in svacs/.

Dependency note: this file depends on the `svacs` package (and therefore,
transitively, on `pydantic`). It is not standard-library only.
"""

from typing import Any, Dict, List, Optional

from svacs.runtime import SVACSRuntime
from svacs.models import SVACSIntelligenceRecord, ObservationSource

RESTRICTED_ZONES: List[str] = []

UNKNOWN_THRESHOLD = 0.3
LOW_CONFIDENCE_UPPER = 0.6
HIGH_RISK_CONFIDENCE = 0.4

_default_runtime: Optional[SVACSRuntime] = None


def _get_runtime() -> SVACSRuntime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = SVACSRuntime()
    return _default_runtime


def determine_risk_level(vessel_class: Optional[str], confidence: float,
                          zone_id: Optional[str] = None,
                          restricted_zones: Optional[List[str]] = None) -> str:
    """
    CRITICAL: submarine-class candidate OR vessel located in a restricted zone
    HIGH:     no candidate class resolved OR confidence below 0.4
    MEDIUM:   patrol-type candidate OR confidence in [0.4, 0.6]
    LOW:      otherwise, confidence above 0.6
    """
    zones = restricted_zones if restricted_zones is not None else RESTRICTED_ZONES
    vc = (vessel_class or "").lower()

    if "submarine" in vc or (zone_id and zone_id in zones):
        return "CRITICAL"
    if not vessel_class or confidence < HIGH_RISK_CONFIDENCE:
        return "HIGH"
    if "patrol" in vc or (HIGH_RISK_CONFIDENCE <= confidence <= LOW_CONFIDENCE_UPPER):
        return "MEDIUM"
    if confidence > LOW_CONFIDENCE_UPPER:
        return "LOW"
    return "MEDIUM"


def determine_validation_status(confidence: float, risk_level: str) -> str:
    """
    DENY:  confidence below 0.3 OR risk is CRITICAL
    FLAG:  confidence in [0.3, 0.6] OR risk is HIGH
    ALLOW: confidence above 0.6 AND risk is LOW or MEDIUM
    """
    if confidence < UNKNOWN_THRESHOLD or risk_level == "CRITICAL":
        return "DENY"
    if (UNKNOWN_THRESHOLD <= confidence <= LOW_CONFIDENCE_UPPER) or risk_level == "HIGH":
        return "FLAG"
    if confidence > LOW_CONFIDENCE_UPPER and risk_level in ("LOW", "MEDIUM"):
        return "ALLOW"
    return "FLAG"


def process_intelligence(intel: Dict[str, Any],
                          observation_source: Optional[ObservationSource] = None,
                          runtime: Optional[SVACSRuntime] = None,
                          restricted_zones: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Delegates consumption, reasoning, confidence refinement,
    explainability, and bucket persistence entirely to
    SVACSRuntime.process(). Adds only risk assessment and validation
    gating on top of the resulting SVACSIntelligenceRecord.

    Args:
        intel: structured intelligence payload exactly as produced by
            Samachar (image observation), an AIS feed, or manual operator
            entry — the same shapes accepted by
            svacs.consumer.StructuredIntelligenceConsumer.consume().
        observation_source: "image" | "ais" | "manual", or None to let
            the consumer auto-detect the shape.
        runtime: optional injected SVACSRuntime (primarily for tests);
            defaults to a shared module-level instance.
        restricted_zones: optional override of the restricted-zone list
            used for CRITICAL risk determination.

    Returns:
        dict: trace_id, observation_id, bucket_id, vessel_class,
            vessel_candidate, confidence_score, risk_level,
            validation_status, operator_action_required, explanation,
            evidence_chain, knowledge_references, lineage_reference,
            timestamp_utc.
    """
    rt = runtime or _get_runtime()

    record: SVACSIntelligenceRecord = rt.process(intel, observation_source=observation_source)

    zone_id = None
    if isinstance(intel.get("metadata"), dict):
        zone_id = intel["metadata"].get("zone_id")
    zone_id = zone_id or intel.get("zone_id")

    vessel_class = record.explainable.candidate_class
    confidence = record.explainable.confidence

    risk_level = determine_risk_level(vessel_class, confidence, zone_id,
                                       restricted_zones=restricted_zones)
    validation_status = determine_validation_status(confidence, risk_level)
    operator_action_required = validation_status in ("FLAG", "DENY")

    evidence_chain = list(record.explainable.supporting_evidence)
    evidence_chain.append(f"source_type:{record.observation.observation_source}")

    return {
        "trace_id": record.trace_id,
        "observation_id": record.observation_id,
        "bucket_id": record.bucket_id,
        "vessel_class": vessel_class or "unknown",
        "vessel_candidate": record.explainable.candidate_vessel,
        "confidence_score": confidence,
        "risk_level": risk_level,
        "validation_status": validation_status,
        "operator_action_required": operator_action_required,
        "explanation": " ".join(record.explainable.maritime_reasoning),
        "evidence_chain": evidence_chain,
        "knowledge_references": record.explainable.knowledge_references,
        "lineage_reference": record.explainable.lineage_reference,
        "timestamp_utc": record.created_at,
    }


if __name__ == "__main__":
    import json
    from svacs.bucket_store import BucketStore

    _test_runtime = SVACSRuntime(bucket_store=BucketStore(directory="./test_bucket_store_vie"))

    def _print_result(title, result):
        print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
        print(json.dumps(result, indent=2))
        return result

    samachar_intel = {
        "trace_id": "trace_test_image_001",
        "observation_id": "obs_test_image_001",
        "timestamp": "2026-07-14T00:00:00Z",
        "source_type": "mobile",
        "detected_entities": [{
            "entity_id": "ent_001",
            "name": "Merchant Ship",
            "type": "vessel",
            "confidence": 0.55,
            "bounding_box": {"xmin": 73.7, "ymin": 300.8, "xmax": 747.2, "ymax": 529.1},
            "metadata": {}
        }],
        "confidence": 0.55,
        "supporting_evidence": {
            "image_url": "http://localhost:8005/data/uploads/x.jpg",
            "ocr_text": "\"BALEARIA",
            "metadata": {}
        },
        "processing_metadata": {"processed_by": "Samachar Ingestion Companion Service v1.0.0"},
        "schema_version": "1.0.0",
    }
    r1 = _print_result(
        "TEST 1: Real Samachar image intelligence, known vessel OCR match",
        process_intelligence(samachar_intel, observation_source="image", runtime=_test_runtime),
    )
    assert r1["trace_id"] == samachar_intel["trace_id"]
    assert r1["vessel_candidate"] == "BALEARIA"
    assert r1["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert r1["validation_status"] in ("ALLOW", "FLAG", "DENY")

    samachar_intel_unknown = dict(samachar_intel)
    samachar_intel_unknown["trace_id"] = "trace_test_image_002"
    samachar_intel_unknown["observation_id"] = "obs_test_image_002"
    samachar_intel_unknown["supporting_evidence"] = {
        "image_url": "http://localhost:8005/data/uploads/y.jpg",
        "ocr_text": "UNRECOGNIZED_TEXT_123",
        "metadata": {},
    }
    r2 = _print_result(
        "TEST 2: Real Samachar image intelligence, no knowledge base match",
        process_intelligence(samachar_intel_unknown, observation_source="image", runtime=_test_runtime),
    )
    assert r2["confidence_score"] < r1["confidence_score"], "unverified vessel must score lower than verified"

    ais_intel = {
        "trace_id": "trace_test_ais_001",
        "observation_id": "obs_test_ais_001",
        "mmsi": "123456789",
        "vessel_name": "MAERSK ESSEX",
        "ais_type": "container_ship",
        "signal_quality": 0.9,
        "speed_knots": 18.2,
        "heading": 270,
        "lat": 15.4,
        "lon": 88.2,
    }
    r3 = _print_result(
        "TEST 3: AIS-derived intelligence",
        process_intelligence(ais_intel, observation_source="ais", runtime=_test_runtime),
    )
    assert r3["trace_id"] == ais_intel["trace_id"]
    assert r3["vessel_candidate"] == "MAERSK ESSEX"

    manual_intel_submarine = {
        "trace_id": "trace_test_manual_001",
        "observation_id": "obs_test_manual_001",
        "intelligence_type": "manual",
        "operator_id": "op_42",
        "reported_vessel_name": "Unidentified Contact",
        "reported_type": "submarine",
        "operator_confidence": 0.9,
        "notes": "Periscope-like feature observed at range.",
    }
    r4 = _print_result(
        "TEST 4: Manual report of submarine -> CRITICAL/DENY",
        process_intelligence(manual_intel_submarine, observation_source="manual", runtime=_test_runtime),
    )
    assert r4["risk_level"] == "CRITICAL"
    assert r4["validation_status"] == "DENY"
    assert r4["operator_action_required"] is True

    ais_intel_zone = dict(ais_intel)
    ais_intel_zone["trace_id"] = "trace_test_ais_zone_001"
    ais_intel_zone["observation_id"] = "obs_test_ais_zone_001"
    ais_intel_zone["metadata"] = {"zone_id": "ZONE_ALPHA_RESTRICTED"}
    r5 = _print_result(
        "TEST 5: Restricted zone override -> CRITICAL/DENY",
        process_intelligence(
            ais_intel_zone, observation_source="ais", runtime=_test_runtime,
            restricted_zones=["ZONE_ALPHA_RESTRICTED"],
        ),
    )
    assert r5["risk_level"] == "CRITICAL"
    assert r5["validation_status"] == "DENY"

    assert r1["observation_id"] == samachar_intel["observation_id"]
    assert r3["observation_id"] == ais_intel["observation_id"]

    print("\nAll self-tests passed.")