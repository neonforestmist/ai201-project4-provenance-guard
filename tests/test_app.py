import tempfile
import unittest
from pathlib import Path

from provenance_guard.app import create_app
from provenance_guard.detectors import classify_content, stylometric_signal


TEMPLATE_AI_SAMPLE = (
    "This essay highlights the transformative power of artificial intelligence. "
    "This essay highlights the transformative power of artificial intelligence. "
    "This essay highlights the transformative power of artificial intelligence. "
    "It is important to note that responsible innovation matters. "
    "It is important to note that responsible innovation matters. "
    "In conclusion, artificial intelligence is a transformative paradigm shift."
)

CASUAL_HUMAN_SAMPLE = (
    "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
    "the broth was fine but they put WAY too much sodium in it and i was thirsty for "
    "like three hours after. my friend got the spicy version and said it was better. "
    "probably won't go back unless someone drags me there"
)

BORDERLINE_FORMULAIC_SAMPLE = (
    "In today's rapidly evolving landscape, artificial intelligence represents a "
    "transformative paradigm shift. In today's rapidly evolving landscape, artificial "
    "intelligence represents a transformative paradigm shift. It is important to note "
    "that the benefits are numerous. Furthermore, stakeholders across various sectors "
    "must collaborate. In conclusion, this essay demonstrates responsible deployment."
)

BORDERLINE_MIXED_SAMPLE = (
    "I've been thinking about remote work lately. The flexibility is real, and the "
    "lack of commute changes the whole day. At the same time, it is important to note "
    "that isolation can creep in quietly. Overall, the tradeoff depends on the person, "
    "the job, and the team."
)


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

    def test_stylometric_signal_is_standalone(self):
        signal = stylometric_signal(BORDERLINE_FORMULAIC_SAMPLE)

        self.assertEqual(signal.name, "stylometric_heuristics")
        self.assertTrue(0 <= signal.ai_probability <= 1)
        self.assertTrue(0 <= signal.confidence <= 1)
        self.assertIn("type_token_ratio", signal.details)
        self.assertIn("sentence_length_stdev", signal.details)
        self.assertIn("punctuation_density", signal.details)

    def test_milestone4_confidence_scores_span_label_categories(self):
        template_ai = classify_content(TEMPLATE_AI_SAMPLE, groq_api_key="")
        casual_human = classify_content(CASUAL_HUMAN_SAMPLE, groq_api_key="")
        borderline_formulaic = classify_content(BORDERLINE_FORMULAIC_SAMPLE, groq_api_key="")
        borderline_mixed = classify_content(BORDERLINE_MIXED_SAMPLE, groq_api_key="")

        self.assertEqual(template_ai["attribution_result"], "ai_generated")
        self.assertEqual(casual_human["attribution_result"], "human_written")
        self.assertEqual(borderline_formulaic["attribution_result"], "uncertain")
        self.assertEqual(borderline_mixed["attribution_result"], "uncertain")
        self.assertGreater(
            template_ai["ai_probability"] - casual_human["ai_probability"],
            0.5,
        )
        self.assertGreater(borderline_formulaic["ai_probability"], casual_human["ai_probability"])

    def test_submit_alias_accepts_text_field(self):
        response = self.client.post(
            "/submit",
            json={
                "creator_id": "creator-alias",
                "text": (
                    "In today's rapidly evolving creative landscape, storytelling helps "
                    "communities share context, trust, and creative intent with readers."
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("submission_id", data)
        self.assertIn("transparency_label", data)
        self.assertTrue(
            any(signal["name"] == "groq_llm_classification" for signal in data["signals"])
        )

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

    def test_audit_log_records_individual_signal_scores(self):
        self.client.post(
            "/submit",
            json={
                "creator_id": "creator-log",
                "content": TEMPLATE_AI_SAMPLE,
            },
        )

        response = self.client.get("/log?limit=1")
        self.assertEqual(response.status_code, 200)
        log_entry = response.get_json()["entries"][0]
        payload = log_entry["payload"]
        signal_names = {signal["name"] for signal in payload["signals"]}

        self.assertEqual(log_entry["event_type"], "classification_decision")
        self.assertIn("confidence_score", payload)
        self.assertIn("ai_probability", payload)
        self.assertIn("groq_llm_classification", signal_names)
        self.assertIn("stylometric_heuristics", signal_names)
        self.assertTrue(
            all("ai_probability" in signal and "confidence" in signal for signal in payload["signals"])
        )


if __name__ == "__main__":
    unittest.main()
