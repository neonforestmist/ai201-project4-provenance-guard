import sys
import tempfile
from pathlib import Path
from pprint import pprint


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provenance_guard.app import create_app
from provenance_guard.labels import LABEL_VARIANTS


SAMPLES = [
    {
        "name": "likely_ai",
        "label_key": "likely_ai",
        "content": (
            "This essay highlights the transformative power of artificial intelligence. "
            "This essay highlights the transformative power of artificial intelligence. "
            "This essay highlights the transformative power of artificial intelligence. "
            "It is important to note that responsible innovation matters. "
            "It is important to note that responsible innovation matters. "
            "In conclusion, artificial intelligence is a transformative paradigm shift."
        ),
    },
    {
        "name": "likely_human",
        "label_key": "likely_human",
        "content": (
            "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
            "the broth was fine but they put WAY too much sodium in it and i was thirsty for "
            "like three hours after. my friend got the spicy version and said it was better. "
            "probably won't go back unless someone drags me there"
        ),
    },
    {
        "name": "uncertain",
        "label_key": "uncertain",
        "content": (
            "In today's rapidly evolving landscape, artificial intelligence represents a "
            "transformative paradigm shift. In today's rapidly evolving landscape, artificial "
            "intelligence represents a transformative paradigm shift. It is important to note "
            "that the benefits are numerous. Furthermore, stakeholders across various sectors "
            "must collaborate. In conclusion, this essay demonstrates responsible deployment."
        ),
    },
]


def create_demo_app(database_path: Path, rate_limit: str):
    return create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": database_path,
            "GROQ_API_KEY": "",
            "SUBMISSION_RATE_LIMIT": rate_limit,
        }
    )


def run_label_appeal_and_log_demo() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        app = create_demo_app(Path(tempdir) / "milestone5.sqlite3", "1000 per minute")
        client = app.test_client()
        submissions = []

        print("\nTRANSPARENCY LABEL VARIANTS")
        for sample in SAMPLES:
            response = client.post(
                "/submit",
                json={
                    "creator_id": f"demo-{sample['name']}",
                    "content": sample["content"],
                },
            )
            data = response.get_json()
            submissions.append(data)

            assert response.status_code == 201
            assert data["label_key"] == sample["label_key"]
            assert data["transparency_label"] == LABEL_VARIANTS[sample["label_key"]]

            pprint(
                {
                    "sample": sample["name"],
                    "status_code": response.status_code,
                    "content_id": data["content_id"],
                    "attribution": data["attribution"],
                    "confidence": data["confidence"],
                    "label": data["label"],
                }
            )

        appeal_response = client.post(
            "/appeal",
            json={
                "content_id": submissions[0]["content_id"],
                "creator_id": "demo-likely-ai",
                "creator_reasoning": (
                    "This piece came from my own draft history, and I can provide notes "
                    "and revisions for the reviewer."
                ),
            },
        )
        appeal = appeal_response.get_json()

        assert appeal_response.status_code == 201
        assert appeal["status"] == "under_review"
        assert appeal["appeal_reasoning"]

        print("\nAPPEALS WORKFLOW")
        pprint(
            {
                "status_code": appeal_response.status_code,
                "content_id": appeal["content_id"],
                "status": appeal["status"],
                "appeal_reasoning": appeal["appeal_reasoning"],
            }
        )

        log_response = client.get("/log?limit=10")
        log = log_response.get_json()
        summary = [
            {
                "event_type": entry["event_type"],
                "content_id": entry["content_id"],
                "status": entry["payload"].get("status"),
                "appeal_reasoning": entry["payload"].get("appeal_reasoning"),
                "signal_count": len(entry["payload"].get("signals", [])),
            }
            for entry in log["entries"]
        ]

        assert log["count"] >= 4
        assert any(entry["event_type"] == "appeal_submitted" for entry in log["entries"])

        print("\nCOMPLETE AUDIT LOG")
        pprint(summary)


def run_rate_limit_demo() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        app = create_demo_app(Path(tempdir) / "ratelimit.sqlite3", "2 per minute")
        client = app.test_client()

        responses = [
            client.post("/submit", json={"content": SAMPLES[0]["content"]})
            for _ in range(3)
        ]
        statuses = [response.status_code for response in responses]
        final_payload = responses[-1].get_json()

        assert statuses == [201, 201, 429]

        print("\nRATE LIMIT CHECK")
        pprint(
            {
                "configured_limit": "2 per minute",
                "submission_statuses": statuses,
                "rate_limit_error": final_payload,
            }
        )


def main() -> None:
    run_label_appeal_and_log_demo()
    run_rate_limit_demo()


if __name__ == "__main__":
    main()
