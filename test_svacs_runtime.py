import unittest
from svacs.runtime import SVACSRuntime
from svacs.bucket_store import BucketStore


def image_payload(trace_id="trace_img_001", vessel_ocr="\"BALEARIA"):
    return {
        "trace_id": trace_id,
        "observation_id": "obs_img_001",
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
            "ocr_text": vessel_ocr,
            "metadata": {}
        },
        "processing_metadata": {"processed_by": "Samachar Ingestion Companion Service v1.0.0"},
        "schema_version": "1.0.0",
    }


def ais_payload(trace_id="trace_ais_001"):
    return {
        "trace_id": trace_id,
        "observation_id": "obs_ais_001",
        "mmsi": "123456789",
        "vessel_name": "MAERSK ESSEX",
        "ais_type": "container_ship",
        "signal_quality": 0.9,
        "speed_knots": 18.2,
        "heading": 270,
        "lat": 15.4, "lon": 88.2,
    }


def manual_payload(trace_id="trace_manual_001"):
    return {
        "trace_id": trace_id,
        "observation_id": "obs_manual_001",
        "intelligence_type": "manual",
        "operator_id": "op_42",
        "reported_vessel_name": "Unknown Fishing Trawler",
        "reported_type": "fishing_vessel",
        "operator_confidence": 0.6,
        "notes": "Observed visually near coastline, no photo captured.",
    }


class TestSVACSRuntime(unittest.TestCase):

    def setUp(self):
        self.runtime = SVACSRuntime(bucket_store=BucketStore(directory="./test_bucket_store"))

    def test_image_observation_knowledge_match_boosts_confidence(self):
        record = self.runtime.process(image_payload(), observation_source="image")
        self.assertEqual(record.explainable.candidate_vessel, "BALEARIA")
        self.assertGreater(record.confidence.final_confidence, record.confidence.vision_confidence)
        self.assertTrue(record.reasoning.evidence_signals["knowledge_verified"])

    def test_image_observation_unknown_vessel_lowers_confidence(self):
        record = self.runtime.process(
            image_payload(trace_id="trace_img_002", vessel_ocr="RANDOMTEXT123"),
            observation_source="image"
        )
        self.assertFalse(record.reasoning.evidence_signals["knowledge_verified"])
        self.assertLess(record.confidence.final_confidence, record.confidence.vision_confidence)

    def test_ais_observation_high_confidence(self):
        record = self.runtime.process(ais_payload(), observation_source="ais")
        self.assertEqual(record.explainable.candidate_vessel, "MAERSK ESSEX")
        self.assertGreaterEqual(record.confidence.final_confidence, 0.9)

    def test_manual_observation_penalized(self):
        record = self.runtime.process(manual_payload(), observation_source="manual")
        self.assertLess(record.confidence.final_confidence, record.confidence.vision_confidence)

    def test_single_pipeline_convergence(self):
        """All three source types must pass through the identical stage sequence."""
        r1 = self.runtime.process(image_payload(trace_id="trace_conv_1"), observation_source="image")
        r2 = self.runtime.process(ais_payload(trace_id="trace_conv_2"), observation_source="ais")
        r3 = self.runtime.process(manual_payload(trace_id="trace_conv_3"), observation_source="manual")
        expected_stages = [
            "stage=StructuredIntelligenceConsumer:complete",
            "stage=MaritimeReasoningEngine:complete",
            "stage=ConfidenceRefinementEngine:complete",
            "stage=ExplainabilityGenerator:complete",
        ]
        for r in (r1, r2, r3):
            for stage in expected_stages:
                self.assertIn(stage, r.explainable.runtime_trace)

    def test_trace_continuity_across_bucket_and_replay(self):
        record = self.runtime.process(image_payload(trace_id="trace_continuity_1"), observation_source="image")
        replay = self.runtime.replay("trace_continuity_1")
        self.assertEqual(replay["trace_id"], record.trace_id)
        self.assertEqual(replay["dashboard_view"]["trace_id"], record.trace_id)
        self.assertEqual(replay["nicai_view"]["trace_id"], record.trace_id)
        self.assertTrue(replay["replay_safe"])
        self.assertTrue(all(replay["checks"].values()))

    def test_deterministic_execution(self):
        r1 = self.runtime.process(image_payload(trace_id="trace_det_1"), observation_source="image")
        r2 = self.runtime.process(image_payload(trace_id="trace_det_2"), observation_source="image")
        self.assertEqual(r1.confidence.final_confidence, r2.confidence.final_confidence)
        self.assertEqual(r1.explainable.candidate_vessel, r2.explainable.candidate_vessel)

    def test_replay_missing_trace_raises(self):
        with self.assertRaises(ValueError):
            self.runtime.replay("trace_does_not_exist")


if __name__ == "__main__":
    unittest.main()