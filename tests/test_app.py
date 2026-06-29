import tempfile
import unittest
from pathlib import Path

from provenance_guard.app import create_app
from provenance_guard.detectors import classify_content, stylometric_signal
from provenance_guard.labels import LABEL_VARIANTS


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
        self.assertEqual(data["content_id"], data["submission_id"])
        self.assertIn(data["attribution_result"], {"ai_generated", "human_written", "uncertain"})
        self.assertEqual(data["attribution"], data["attribution_result"])
        self.assertIn("confidence_score", data)
        self.assertEqual(data["confidence"], data["confidence_score"])
        self.assertIn("transparency_label", data)
        self.assertEqual(data["label"], data["transparency_label"])
        self.assertFalse(data["appeal_filed"])
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

    def test_submit_endpoint_reaches_all_transparency_label_variants(self):
        cases = [
            (TEMPLATE_AI_SAMPLE, "ai_generated", "likely_ai"),
            (CASUAL_HUMAN_SAMPLE, "human_written", "likely_human"),
            (BORDERLINE_FORMULAIC_SAMPLE, "uncertain", "uncertain"),
        ]
        seen_label_keys = set()

        for content, expected_result, expected_label_key in cases:
            response = self.client.post("/submit", json={"content": content})

            self.assertEqual(response.status_code, 201)
            data = response.get_json()
            seen_label_keys.add(data["label_key"])
            self.assertEqual(data["attribution_result"], expected_result)
            self.assertEqual(data["label_key"], expected_label_key)
            self.assertEqual(data["transparency_label"], LABEL_VARIANTS[expected_label_key])
            self.assertEqual(data["label"], LABEL_VARIANTS[expected_label_key])

        self.assertEqual(seen_label_keys, {"likely_ai", "likely_human", "uncertain"})

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

        appeal_reasoning = "This is my original work and I can provide drafts for review."
        appeal_response = self.client.post(
            "/appeal",
            json={
                "content_id": submission_id,
                "creator_id": "creator-appeal",
                "creator_reasoning": appeal_reasoning,
            },
        )
        self.assertEqual(appeal_response.status_code, 201)
        appeal = appeal_response.get_json()
        self.assertEqual(appeal["status"], "under_review")
        self.assertEqual(appeal["content_id"], submission_id)
        self.assertEqual(appeal["creator_reasoning"], appeal_reasoning)
        self.assertEqual(appeal["appeal_reasoning"], appeal_reasoning)

        updated_submission = self.client.get(f"/api/submissions/{submission_id}").get_json()
        self.assertEqual(updated_submission["status"], "under_review")
        self.assertEqual(updated_submission["content_id"], submission_id)
        self.assertTrue(updated_submission["appeal_filed"])

        log = self.client.get("/api/log").get_json()["entries"]
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["event_type"], "appeal_submitted")
        self.assertEqual(log[1]["event_type"], "classification_decision")
        self.assertEqual(log[0]["content_id"], submission_id)
        self.assertEqual(log[0]["payload"]["status"], "under_review")
        self.assertEqual(log[0]["payload"]["appeal_reasoning"], appeal_reasoning)

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
        self.assertEqual(log_entry["content_id"], payload["content_id"])
        self.assertIn("confidence_score", payload)
        self.assertIn("confidence", payload)
        self.assertIn("ai_probability", payload)
        self.assertIn("attribution", payload)
        self.assertIn("label", payload)
        self.assertFalse(payload["appeal_filed"])
        self.assertIn("groq_llm_classification", signal_names)
        self.assertIn("stylometric_heuristics", signal_names)
        self.assertTrue(
            all("ai_probability" in signal and "confidence" in signal for signal in payload["signals"])
        )

    def test_submission_rate_limit_returns_429(self):
        with tempfile.TemporaryDirectory() as tempdir:
            app = create_app(
                {
                    "TESTING": True,
                    "RATELIMIT_ENABLED": True,
                    "DATABASE_PATH": Path(tempdir) / "ratelimit.sqlite3",
                    "GROQ_API_KEY": "",
                    "SUBMISSION_RATE_LIMIT": "2 per minute",
                }
            )
            client = app.test_client()
            statuses = [
                client.post("/submit", json={"content": TEMPLATE_AI_SAMPLE}).status_code
                for _ in range(3)
            ]
            limit_response = client.post("/submit", json={"content": TEMPLATE_AI_SAMPLE})

        self.assertEqual(statuses, [201, 201, 429])
        self.assertEqual(limit_response.status_code, 429)
        self.assertEqual(limit_response.get_json()["error"], "rate_limit_exceeded")
        self.assertEqual(limit_response.get_json()["limit"], "2 per minute")


if __name__ == "__main__":
    unittest.main()
