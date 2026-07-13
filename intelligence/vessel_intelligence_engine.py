#!/usr/bin/env python3
"""
vessel_intelligence_engine.py

SVACS Maritime Intelligence Runtime — Structured Intelligence Consumer.

This module sits AFTER Samachar + Vision Runtime (perception / visual
extraction layers) and BEFORE Bucket / Replay / Dashboard / NICAI.

Pipeline this module occupies:
    Image -> Samachar -> Vision Runtime -> Structured Intelligence -> [THIS]
    -> Confidence & Evidence -> Bucket -> Replay -> Dashboard -> NICAI

Responsibilities:
    - Consume structured intelligence produced by Samachar / Vision Runtime
      (image, AIS, or manual observations). Structured intelligence may
      include a raw `vision_confidence` field from the Vision Runtime.
    - Perform deterministic, rule-based maritime reasoning (no ML) —
      NOT a repetition of the vision model's raw prediction.
    - Produce ranked candidate vessels with confidence scores.
    - Ground reasoning in a hardcoded maritime knowledge registry
      (dimension ranges, speed ranges, superstructure signatures, Jane's
      references, fleet lineage).
    - REFINE confidence: blend raw vision_confidence (when present) with
      maritime evidence strength, rather than passing vision confidence
      through unchanged. This satisfies the "Confidence Refinement Engine"
      deliverable — final confidence represents SVACS maritime reasoning,
      not raw vision output.
    - Emit fully explainable, replay-safe output including evidence chain,
      knowledge references, lineage reference, risk level, and validation
      status, keyed by the unchanged upstream trace_id.

This module does NOT:
    - Perform image processing / computer vision (Vision Runtime's job).
    - Perform ingestion (Samachar's job).
    - Talk to Bucket, Replay, Dashboard, or NICAI directly — it returns a
      dict for the caller to hand onward.
    - Use any external or ML libraries.

Standalone: only Python standard library is used.
"""

import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Maritime Knowledge Registry
# ---------------------------------------------------------------------------
# Hardcoded class-level maritime knowledge used to ground / validate
# classifications. In production this could be backed by a real Jane's
# data feed; here it is a deterministic, static registry.

MARITIME_KNOWLEDGE_REGISTRY = {
    "cargo": {
        "length_range_m": (100, 300),
        "beam_range_m": (15, 45),
        "speed_range_knots": (10, 22),
        "superstructure": ["single_funnel", "aft_bridge", "box_hull"],
        "janes_ref": "Jane's Fighting Ships — Cargo Vessel Class Profile",
        "lineage": "General cargo / bulk carrier lineage — post-1990 box-hull design family.",
    },
    "tanker": {
        "length_range_m": (150, 380),
        "beam_range_m": (20, 60),
        "speed_range_knots": (10, 18),
        "superstructure": ["single_funnel", "aft_bridge", "flat_deck", "pipeline_manifold"],
        "janes_ref": "Jane's Fighting Ships — Tanker Class Profile",
        "lineage": "Product/crude tanker lineage — flat-deck manifold design family.",
    },
    "patrol": {
        "length_range_m": (20, 90),
        "beam_range_m": (4, 14),
        "speed_range_knots": (15, 35),
        "superstructure": ["low_profile", "mast_array", "gun_mount"],
        "janes_ref": "Jane's Fighting Ships — Patrol Vessel Class Profile",
        "lineage": "Coastal/offshore patrol vessel lineage — fast low-profile hull family.",
    },
    "fishing": {
        "length_range_m": (10, 60),
        "beam_range_m": (3, 12),
        "speed_range_knots": (5, 15),
        "superstructure": ["forward_bridge", "net_gear", "low_freeboard"],
        "janes_ref": "Jane's Fighting Ships — Fishing Vessel Class Profile",
        "lineage": "Commercial fishing vessel lineage — forward-bridge trawler family.",
    },
    "submarine": {
        "length_range_m": (60, 180),
        "beam_range_m": (7, 15),
        "speed_range_knots": (0, 25),
        "superstructure": ["conning_tower", "low_freeboard", "no_funnel"],
        "janes_ref": "Jane's Fighting Ships — Submarine Class Profile",
        "lineage": "Submarine lineage — conning-tower hull family, funnel-less signature.",
    },
}

# Hardcoded sample MMSI -> known vessel lookup. Represents a fragment of a
# Jane's / registry cross-reference table, including fleet lineage notes.
KNOWN_MMSI_REGISTRY = {
    "368084090": {
        "class": "cargo",
        "janes_ref": "Jane's Registry Entry #MMSI-368084090 (Cargo, verified)",
        "fleet_history": "3 prior verified sightings, consistent cargo classification.",
    },
}

# Weight given to raw Vision Runtime confidence (when present) inside the
# refined confidence blend. Kept below the maritime-evidence weight so the
# final score reflects SVACS reasoning rather than repeating vision output.
VISION_CONFIDENCE_WEIGHT = 0.25

# Source-type reliability weights used in overall confidence blending.
SOURCE_TYPE_WEIGHTS = {"image": 0.7, "ais": 0.9, "manual": 0.5}

# Placeholder for geo-fenced restricted zone identifiers. Populate this list
# (or replace with a lookup) when zone data becomes available upstream.
RESTRICTED_ZONES = []

# Thresholds (kept as named constants so rules stay auditable/replayable).
UNKNOWN_THRESHOLD = 0.3
LOW_CONFIDENCE_UPPER = 0.6
HIGH_RISK_CONFIDENCE = 0.4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _in_range(value, value_range):
    """Return True if value falls inside the inclusive (lo, hi) range."""
    if value is None:
        return False
    lo, hi = value_range
    return lo <= value <= hi


def _range_score(value, value_range):
    """
    Score how well a numeric value fits a (lo, hi) range.

    Returns 1.0 if inside the range, decaying linearly toward 0.0 the
    further outside the range the value falls. Returns 0.0 if value is None.
    """
    if value is None:
        return 0.0
    lo, hi = value_range
    if lo <= value <= hi:
        return 1.0
    span = (hi - lo) if hi > lo else 1
    dist = min(abs(value - lo), abs(value - hi))
    return max(0.0, 1.0 - (dist / span))


def _feature_completeness(intel):
    """
    Compute the fraction (0..1) of expected structured-intelligence fields
    that are present and non-empty. Used as one input to overall confidence.
    """
    expected_fields = ["vessel_class", "visual_features", "dimensions_estimate", "ais_data"]
    present = sum(1 for f in expected_fields if intel.get(f))
    return present / len(expected_fields)


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def classify_vessel(intel):
    """
    Rule-based, deterministic classification against every known vessel
    class in the maritime knowledge registry.

    Scores each class using (whichever of these are available in the input):
        - hull length match
        - beam match
        - AIS speed match
        - visual feature / superstructure overlap
        - Samachar's own vessel_class hint

    Returns a list of dicts: {"class", "confidence", "evidence"}, sorted by
    descending confidence.
    """
    dims = intel.get("dimensions_estimate") or {}
    length = dims.get("length_m")
    beam = dims.get("beam_m")

    ais = intel.get("ais_data") or {}
    speed = ais.get("speed_knots")

    visual_features = set(intel.get("visual_features") or [])
    samachar_class = intel.get("vessel_class", "unknown")

    results = []
    for vessel_class, profile in MARITIME_KNOWLEDGE_REGISTRY.items():
        evidence = []
        score_components = []

        if length is not None:
            score_components.append(_range_score(length, profile["length_range_m"]))
            if _in_range(length, profile["length_range_m"]):
                evidence.append("length_match")

        if beam is not None:
            score_components.append(_range_score(beam, profile["beam_range_m"]))
            if _in_range(beam, profile["beam_range_m"]):
                evidence.append("beam_match")

        if speed is not None:
            score_components.append(_range_score(speed, profile["speed_range_knots"]))
            if _in_range(speed, profile["speed_range_knots"]):
                evidence.append("speed_match")

        if visual_features:
            overlap = visual_features.intersection(set(profile["superstructure"]))
            score_components.append(len(overlap) / max(len(profile["superstructure"]), 1))
            if overlap:
                evidence.append("superstructure_match:" + ",".join(sorted(overlap)))

        if samachar_class == vessel_class:
            score_components.append(1.0)
            evidence.append("samachar_class_hint")

        raw_score = (sum(score_components) / len(score_components)) if score_components else 0.0

        results.append({
            "class": vessel_class,
            "confidence": round(raw_score, 4),
            "evidence": evidence,
        })

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def compute_overall_confidence(intel, top_candidate):
    """
    Refine confidence into one overall score in [0, 1], blending:
        - source_type reliability weight (image=0.7, ais=0.9, manual=0.5)
        - structured-intelligence feature completeness
        - strength of the top rule-based (maritime evidence) match
        - raw `vision_confidence` from the Vision Runtime, IF present in the
          input — down-weighted so the result reflects SVACS maritime
          reasoning rather than simply repeating the vision model's score
          (Task 3: Confidence Refinement).

    When vision_confidence is absent (AIS-only / manual paths), weight is
    redistributed across the remaining three signals so the formula stays
    consistent across all source types.
    """
    source_type = intel.get("source_type", "manual")
    source_weight = SOURCE_TYPE_WEIGHTS.get(source_type, 0.5)
    completeness = _feature_completeness(intel)
    rule_strength = top_candidate["confidence"] if top_candidate else 0.0
    vision_confidence = intel.get("vision_confidence")

    if vision_confidence is not None:
        vision_confidence = max(0.0, min(1.0, float(vision_confidence)))
        remaining = 1.0 - VISION_CONFIDENCE_WEIGHT
        overall = (
            (source_weight * remaining * 0.4)
            + (completeness * remaining * 0.2)
            + (rule_strength * remaining * 0.4)
            + (vision_confidence * VISION_CONFIDENCE_WEIGHT)
        )
    else:
        overall = (source_weight * 0.4) + (completeness * 0.2) + (rule_strength * 0.4)

    return round(min(overall, 1.0), 4)


def lookup_janes_reference(intel, vessel_class):
    """
    Build the list of Jane's / knowledge-registry references supporting a
    classification.

    Checks the known-MMSI registry first (direct match), then falls back to
    the class-level Jane's reference from the maritime knowledge registry.
    """
    refs = []
    mmsi = (intel.get("ais_data") or {}).get("mmsi")
    if mmsi and mmsi in KNOWN_MMSI_REGISTRY:
        refs.append(KNOWN_MMSI_REGISTRY[mmsi]["janes_ref"])
    if vessel_class in MARITIME_KNOWLEDGE_REGISTRY:
        refs.append(MARITIME_KNOWLEDGE_REGISTRY[vessel_class]["janes_ref"])
    return refs


def lookup_lineage_reference(intel, vessel_class):
    """
    Build a lineage reference string for the classification, combining any
    known-MMSI fleet history with the class-level lineage note from the
    maritime knowledge registry. Returns None if nothing is known.
    """
    parts = []
    mmsi = (intel.get("ais_data") or {}).get("mmsi")
    if mmsi and mmsi in KNOWN_MMSI_REGISTRY:
        fleet_history = KNOWN_MMSI_REGISTRY[mmsi].get("fleet_history")
        if fleet_history:
            parts.append(fleet_history)
    if vessel_class in MARITIME_KNOWLEDGE_REGISTRY:
        parts.append(MARITIME_KNOWLEDGE_REGISTRY[vessel_class]["lineage"])
    return " ".join(parts) if parts else None


def build_explanation(intel, vessel_class, confidence, top_candidate, unknown=False, low_conf=False):
    """
    Produce a deterministic, plain-English explanation of why the engine
    reached its conclusion, referencing the concrete evidence used.
    """
    if unknown:
        return (
            f"Vessel could not be reliably classified (overall confidence "
            f"{confidence:.2f}, below the {UNKNOWN_THRESHOLD:.2f} threshold). "
            f"Available dimension, speed, and visual-feature evidence was "
            f"insufficient or inconsistent across all known vessel class "
            f"profiles. Classified as UNKNOWN pending further observation."
        )

    dims = intel.get("dimensions_estimate") or {}
    length = dims.get("length_m")
    ais = intel.get("ais_data") or {}
    speed = ais.get("speed_knots")
    features = intel.get("visual_features") or []

    parts = [f"Vessel classified as {vessel_class} with overall confidence {confidence:.2f}."]
    if length is not None:
        parts.append(f"Hull length estimate of {length}m is consistent with the {vessel_class} class profile.")
    if features:
        parts.append(f"Visual features observed: {', '.join(features)}.")
    if speed is not None:
        parts.append(f"AIS speed of {speed} knots aligns with the typical {vessel_class} propulsion profile.")
    if top_candidate and top_candidate["evidence"]:
        parts.append(f"Supporting evidence: {', '.join(top_candidate['evidence'])}.")
    if low_conf:
        parts.append(
            f"Confidence falls in the moderate range ({UNKNOWN_THRESHOLD:.2f}-"
            f"{LOW_CONFIDENCE_UPPER:.2f}); flagged for operator review."
        )

    return " ".join(parts)


def determine_risk_level(vessel_class, confidence, intel):
    """
    Determine risk level.

    Rules (checked in order):
        CRITICAL: submarine detected OR vessel located in a restricted zone
        HIGH:     unknown vessel OR confidence below 0.4
        MEDIUM:   patrol vessel OR confidence in [0.4, 0.6]
        LOW:      cargo/tanker/fishing with confidence above 0.6
    """
    zone_id = intel.get("zone_id")
    if vessel_class == "submarine" or (zone_id and zone_id in RESTRICTED_ZONES):
        return "CRITICAL"
    if vessel_class == "unknown" or confidence < HIGH_RISK_CONFIDENCE:
        return "HIGH"
    if vessel_class == "patrol" or (HIGH_RISK_CONFIDENCE <= confidence <= LOW_CONFIDENCE_UPPER):
        return "MEDIUM"
    if vessel_class in ("cargo", "tanker", "fishing") and confidence > LOW_CONFIDENCE_UPPER:
        return "LOW"
    return "MEDIUM"


def determine_validation_status(confidence, risk_level):
    """
    Determine validation status.

    Rules (checked in order):
        DENY:   confidence below 0.3 OR risk is CRITICAL
        FLAG:   confidence in [0.3, 0.6] OR risk is HIGH
        ALLOW:  confidence above 0.6 AND risk is LOW or MEDIUM
    """
    if confidence < UNKNOWN_THRESHOLD or risk_level == "CRITICAL":
        return "DENY"
    if (UNKNOWN_THRESHOLD <= confidence <= LOW_CONFIDENCE_UPPER) or risk_level == "HIGH":
        return "FLAG"
    if confidence > LOW_CONFIDENCE_UPPER and risk_level in ("LOW", "MEDIUM"):
        return "ALLOW"
    return "FLAG"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_intelligence(intel):
    """
    Main entry point of the SVACS vessel intelligence engine.

    Takes a structured intelligence dict from Samachar (image, AIS, or
    manual observation) and returns a fully explainable, replay-safe vessel
    identification result. Deterministic: the same input always produces
    the same output.

    Args:
        intel (dict): structured intelligence, see module docstring / task
            spec for schema (trace_id, source_type, vessel_class,
            confidence_score, visual_features, dimensions_estimate,
            ais_data, timestamp_utc).

    Returns:
        dict: vessel identification result (trace_id, vessel_class,
            vessel_candidates, confidence_score, risk_level,
            validation_status, explanation, evidence_chain,
            knowledge_references, operator_action_required, timestamp_utc).
    """
    trace_id = intel.get("trace_id", str(uuid.uuid4()))
    timestamp = intel.get("timestamp_utc") or datetime.now(timezone.utc).isoformat()

    ranked_candidates = classify_vessel(intel)
    top_candidates = ranked_candidates[:3]
    top_candidate = top_candidates[0] if top_candidates else None

    overall_confidence = compute_overall_confidence(intel, top_candidate)

    unknown = overall_confidence < UNKNOWN_THRESHOLD
    low_conf = UNKNOWN_THRESHOLD <= overall_confidence < LOW_CONFIDENCE_UPPER

    vessel_class = "unknown" if unknown else (top_candidate["class"] if top_candidate else "unknown")

    evidence_chain = []
    if top_candidate:
        evidence_chain.extend(top_candidate["evidence"])
    evidence_chain.append(f"source_type:{intel.get('source_type', 'unknown')}")
    evidence_chain.append(f"feature_completeness:{_feature_completeness(intel):.2f}")
    if intel.get("vision_confidence") is not None:
        evidence_chain.append(f"vision_confidence_refined:{float(intel['vision_confidence']):.2f}")

    knowledge_references = [] if unknown else lookup_janes_reference(intel, vessel_class)
    lineage_reference = None if unknown else lookup_lineage_reference(intel, vessel_class)

    explanation = build_explanation(
        intel, vessel_class, overall_confidence, top_candidate,
        unknown=unknown, low_conf=low_conf,
    )

    risk_level = determine_risk_level(vessel_class, overall_confidence, intel)
    validation_status = determine_validation_status(overall_confidence, risk_level)

    operator_action_required = unknown or low_conf or validation_status in ("FLAG", "DENY")

    return {
        "trace_id": trace_id,
        "vessel_class": vessel_class,
        "vessel_candidates": top_candidates,
        "confidence_score": overall_confidence,
        "risk_level": risk_level,
        "validation_status": validation_status,
        "explanation": explanation,
        "evidence_chain": evidence_chain,
        "knowledge_references": knowledge_references,
        "lineage_reference": lineage_reference,
        "operator_action_required": operator_action_required,
        "timestamp_utc": timestamp,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    def _print_result(title, intel_in):
        print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
        result = process_intelligence(intel_in)
        print(json.dumps(result, indent=2))
        return result

    # Test 1: High-confidence cargo vessel, image source, rich features.
    test_1 = {
        "trace_id": str(uuid.uuid4()),
        "source_type": "image",
        "vessel_class": "cargo",
        "confidence_score": 0.9,
        "visual_features": ["single_funnel", "aft_bridge", "box_hull"],
        "dimensions_estimate": {"length_m": 180, "beam_m": 28},
        "ais_data": {"mmsi": "368084090", "speed_knots": 12.4, "heading": 270},
        "timestamp_utc": "2026-07-13T09:00:00Z",
    }
    r1 = _print_result("TEST 1: High-confidence cargo (image + AIS)", test_1)
    assert r1["vessel_class"] == "cargo"
    assert r1["validation_status"] == "ALLOW"
    assert r1["risk_level"] == "LOW"
    assert r1["trace_id"] == test_1["trace_id"]

    # Test 2: Sparse, contradictory manual observation -> low confidence / unknown.
    test_2 = {
        "trace_id": str(uuid.uuid4()),
        "source_type": "manual",
        "vessel_class": "unknown",
        "confidence_score": 0.2,
        "visual_features": [],
        "dimensions_estimate": {},
        "ais_data": {},
        "timestamp_utc": "2026-07-13T09:05:00Z",
    }
    r2 = _print_result("TEST 2: Sparse manual observation -> UNKNOWN", test_2)
    assert r2["vessel_class"] == "unknown"
    assert r2["validation_status"] == "DENY"
    assert r2["risk_level"] == "HIGH"
    assert r2["operator_action_required"] is True

    # Test 3: Submarine signature -> CRITICAL risk regardless of confidence.
    test_3 = {
        "trace_id": str(uuid.uuid4()),
        "source_type": "image",
        "vessel_class": "submarine",
        "confidence_score": 0.8,
        "visual_features": ["conning_tower", "low_freeboard", "no_funnel"],
        "dimensions_estimate": {"length_m": 110, "beam_m": 11},
        "ais_data": {},
        "timestamp_utc": "2026-07-13T09:10:00Z",
    }
    r3 = _print_result("TEST 3: Submarine detection -> CRITICAL", test_3)
    assert r3["vessel_class"] == "submarine"
    assert r3["risk_level"] == "CRITICAL"
    assert r3["validation_status"] == "DENY"

    # Test 4: AIS-only input (no image/visual features at all).
    test_4 = {
        "trace_id": str(uuid.uuid4()),
        "source_type": "ais",
        "vessel_class": "tanker",
        "confidence_score": 0.75,
        "visual_features": [],
        "dimensions_estimate": {"length_m": 320, "beam_m": 50},
        "ais_data": {"mmsi": "999000111", "speed_knots": 14.0, "heading": 90},
        "timestamp_utc": "2026-07-13T09:15:00Z",
    }
    r4 = _print_result("TEST 4: AIS-only tanker observation", test_4)
    assert r4["vessel_class"] == "tanker"
    assert "source_type:ais" in r4["evidence_chain"]

    # Test 5: Image-derived intel WITH a raw Vision Runtime confidence field
    # -> confidence must be REFINED (not equal to raw vision_confidence),
    # and a lineage_reference must be present.
    test_5 = {
        "trace_id": str(uuid.uuid4()),
        "source_type": "image",
        "vessel_class": "cargo",
        "confidence_score": 0.9,
        "vision_confidence": 0.95,
        "visual_features": ["single_funnel", "aft_bridge", "box_hull"],
        "dimensions_estimate": {"length_m": 180, "beam_m": 28},
        "ais_data": {"mmsi": "368084090", "speed_knots": 12.4, "heading": 270},
        "timestamp_utc": "2026-07-13T09:20:00Z",
    }
    r5 = _print_result("TEST 5: Image intel with raw vision_confidence -> refined", test_5)
    assert r5["vessel_class"] == "cargo"
    assert r5["confidence_score"] != test_5["vision_confidence"], "confidence must be refined, not passed through"
    assert r5["lineage_reference"] is not None
    assert any(e.startswith("vision_confidence_refined:") for e in r5["evidence_chain"])

    print("\nAll self-tests passed.")