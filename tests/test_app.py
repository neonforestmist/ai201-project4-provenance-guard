import tempfile
import unittest
from pathlib import Path

from provenance_guard.app import create_app


class ProvenanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "DATABASE_PATH": Path(self.tempdir.name) / "test.sqlite3",
                "GROQ_API_KEY": "",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_submission_returns_structured_decision(self):
        response = self.client.post(
            "/api/submissions",
            json={
                "creator_id": "creator-123",
                "content": (
                    "The lamp above the desk flickered twice before dawn. "
                    "I left the letter folded under a chipped mug and waited "
                    "for the hallway to stop echoing."
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("submission_id", data)
        self.assertIn(data["attribution_result"], {"ai_generated", "human_written", "uncertain"})
        self.assertIn("confidence_score", data)
        self.assertIn("transparency_label", data)
        self.assertGreaterEqual(len(data["signals"]), 3)
        self.assertTrue(any(signal["name"] == "stylometric_heuristics" for signal in data["signals"]))

    def test_submission_rejects_too_short_content(self):
        response = self.client.post("/api/submissions", json={"content": "Too short."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "content_too_short")

    def test_appeal_updates_status_and_audit_log(self):
        submission_response = self.client.post(
            "/api/submissions",
            json={
                "creator_id": "creator-appeal",
                "content": (
                    "Overall, this reflection discusses creativity, attribution, and context "
                    "in a rapidly changing digital environment where trust matters."
                ),
            },
        )
        submission_id = submission_response.get_json()["submission_id"]

        appeal_response = self.client.post(
            "/api/appeals",
            json={
                "submission_id": submission_id,
                "creator_id": "creator-appeal",
                "reason": "This is my original work and I can provide drafts for review.",
            },
        )
        self.assertEqual(appeal_response.status_code, 201)
        self.assertEqual(appeal_response.get_json()["status"], "under_review")

        updated_submission = self.client.get(f"/api/submissions/{submission_id}").get_json()
        self.assertEqual(updated_submission["status"], "under_review")

        log = self.client.get("/api/log").get_json()["entries"]
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["event_type"], "appeal_submitted")
        self.assertEqual(log[1]["event_type"], "classification_decision")


if __name__ == "__main__":
    unittest.main()

