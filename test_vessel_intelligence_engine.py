import unittest

from svacs.runtime import SVACSRuntime
from svacs.bucket_store import BucketStore
from intelligence.vessel_intelligence_engine import (
    process_intelligence,
    determine_risk_level,
    determine_validation_status,
)


def samachar_image_payload(trace_id, ocr_text):
    return {
        "trace_id": trace_id,
        "observation_id": f"obs_{trace_id}",
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
            "ocr_text": ocr_text,
            "metadata": {}
        },
        "processing_metadata": {"processed_by": "Samachar Ingestion Companion Service v1.0.0"},
        "schema_version": "1.0.0",
    }


def ais_payload(trace_id, vessel_name="MAERSK ESSEX"):
    return {
        "trace_id": trace_id,
        "observation_id": f"obs_{trace_id}",
        "mmsi": "123456789",
        "vessel_name": vessel_name,
        "ais_type": "container_ship",
        "signal_quality": 0.9,
        "speed_knots": 18.2,
        "heading": 270,
        "lat": 15.4,
        "lon": 88.2,
    }


def manual_payload(trace_id, reported_type="fishing_vessel"):
    return {
        "trace_id": trace_id,
        "observation_id": f"obs_{trace_id}",
        "intelligence_type": "manual",
        "operator_id": "op_42",
        "reported_vessel_name": "Unidentified Contact",
        "reported_type": reported_type,
        "operator_confidence": 0.6,
        "notes": "Visual sighting, no photo captured.",
    }


class TestVesselIntelligenceEngine(unittest.TestCase):

    def setUp(self):
        self.runtime = SVACSRuntime(bucket_store=BucketStore(directory="./test_bucket_store_wrapper"))

    def test_is_thin_wrapper_preserves_trace_id(self):
        result = process_intelligence(
            samachar_image_payload("trace_wrap_001", "\"BALEARIA"),
            observation_source="image", runtime=self.runtime,
        )
        self.assertEqual(result["trace_id"], "trace_wrap_001")
        self.assertEqual(result["observation_id"], "obs_trace_wrap_001")

    def test_known_vessel_ocr_match(self):
        result = process_intelligence(
            samachar_image_payload("trace_wrap_002", "\"BALEARIA"),
            observation_source="image", runtime=self.runtime,
        )
        self.assertEqual(result["vessel_candidate"], "BALEARIA")

    def test_unknown_vessel_scores_lower_than_known(self):
        known = process_intelligence(
            samachar_image_payload("trace_wrap_003", "\"BALEARIA"),
            observation_source="image", runtime=self.runtime,
        )
        unknown = process_intelligence(
            samachar_image_payload("trace_wrap_004", "UNRECOGNIZED_TEXT"),
            observation_source="image", runtime=self.runtime,
        )
        self.assertLess(unknown["confidence_score"], known["confidence_score"])

    def test_ais_high_trust_source(self):
        result = process_intelligence(
            ais_payload("trace_wrap_005"), observation_source="ais", runtime=self.runtime,
        )
        self.assertEqual(result["vessel_candidate"], "MAERSK ESSEX")

    def test_submarine_forces_critical_deny(self):
        result = process_intelligence(
            manual_payload("trace_wrap_006", reported_type="submarine"),
            observation_source="manual", runtime=self.runtime,
        )
        self.assertEqual(result["risk_level"], "CRITICAL")
        self.assertEqual(result["validation_status"], "DENY")
        self.assertTrue(result["operator_action_required"])

    def test_restricted_zone_forces_critical_deny(self):
        payload = ais_payload("trace_wrap_007")
        payload["metadata"] = {"zone_id": "ZONE_X"}
        result = process_intelligence(
            payload, observation_source="ais", runtime=self.runtime,
            restricted_zones=["ZONE_X"],
        )
        self.assertEqual(result["risk_level"], "CRITICAL")
        self.assertEqual(result["validation_status"], "DENY")

    def test_no_duplicate_reasoning_output_matches_svacs_directly(self):
        direct_record = self.runtime.process(
            samachar_image_payload("trace_wrap_008", "\"BALEARIA"), observation_source="image"
        )
        wrapped_result = process_intelligence(
            samachar_image_payload("trace_wrap_009", "\"BALEARIA"),
            observation_source="image", runtime=self.runtime,
        )
        self.assertEqual(direct_record.explainable.candidate_vessel, wrapped_result["vessel_candidate"])

    def test_risk_level_rules_directly(self):
        self.assertEqual(determine_risk_level("submarine", 0.9), "CRITICAL")
        self.assertEqual(determine_risk_level("cargo", 0.2), "HIGH")
        self.assertEqual(determine_risk_level(None, 0.9), "HIGH")
        self.assertEqual(determine_risk_level("patrol", 0.9), "MEDIUM")
        self.assertEqual(determine_risk_level("cargo", 0.9), "LOW")

    def test_validation_status_rules_directly(self):
        self.assertEqual(determine_validation_status(0.1, "HIGH"), "DENY")
        self.assertEqual(determine_validation_status(0.5, "MEDIUM"), "FLAG")
        self.assertEqual(determine_validation_status(0.9, "LOW"), "ALLOW")
        self.assertEqual(determine_validation_status(0.9, "CRITICAL"), "DENY")


if __name__ == "__main__":
    unittest.main()