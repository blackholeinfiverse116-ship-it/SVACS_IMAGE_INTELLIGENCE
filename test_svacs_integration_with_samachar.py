"""
End-to-end validation: real Samachar StructuredIntelligence output ->
SVACS runtime -> Bucket -> Replay -> Dashboard -> NICAI, confirming
trace_id continuity across every stage (Task 5 acceptance criteria).
"""
import unittest
import io
import json
from fastapi.testclient import TestClient

from ingest_service import app as samachar_app
from svacs.runtime import SVACSRuntime
from svacs.bucket_store import BucketStore


class TestSVACSSamacharIntegration(unittest.TestCase):

    def setUp(self):
        self.samachar_client = TestClient(samachar_app)
        self.svacs_runtime = SVACSRuntime(bucket_store=BucketStore(directory="./test_bucket_store_integration"))

    def test_full_lifecycle_trace_continuity(self):
        file_data = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                     b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
                     b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
        metadata = json.dumps({"description": "cargo vessel spotted near territorial boundaries"})

        samachar_response = self.samachar_client.post(
            "/api/ingest/image",
            data={"source_type": "mobile", "metadata": metadata},
            files={"image": ("ship.png", io.BytesIO(file_data), "image/png")}
        )
        self.assertEqual(samachar_response.status_code, 200)
        structured_intel = samachar_response.json()["data"]
        samachar_trace_id = structured_intel["trace_id"]

        # SVACS consumes Samachar's structured intelligence untouched
        record = self.svacs_runtime.process(structured_intel, observation_source="image")

        # Trace continuity: SAME trace_id from Samachar all the way through
        self.assertEqual(record.trace_id, samachar_trace_id)

        replay = self.svacs_runtime.replay(samachar_trace_id)
        self.assertEqual(replay["trace_id"], samachar_trace_id)
        self.assertEqual(replay["dashboard_view"]["trace_id"], samachar_trace_id)
        self.assertEqual(replay["nicai_view"]["trace_id"], samachar_trace_id)
        self.assertTrue(replay["replay_safe"])


if __name__ == "__main__":
    unittest.main()