import sys
import tempfile
from pathlib import Path
from pprint import pprint


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provenance_guard.app import create_app


TEXT_SAMPLE = (
    "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
    "the broth was fine but they put WAY too much sodium in it and i was thirsty for "
    "like three hours after. my friend got the spicy version and said it was better. "
    "probably won't go back unless someone drags me there"
)

IMAGE_DESCRIPTION_SAMPLE = (
    "A hand-painted poster hangs beside a studio window after a rainy afternoon. "
    "The paper is buckled at the corners, the lettering is uneven, and a coffee "
    "ring cuts through the lower margin near the artist's notes."
)

METADATA_SAMPLE = {
    "title": "Gallery Wall Notes",
    "caption": "Installation notes for a handmade gallery wall with uneven frames.",
    "materials": ["paper", "ink", "wood"],
    "creator_notes": "Frames were rearranged twice before the final photo was taken.",
}


def main() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        app = create_app(
            {
                "TESTING": True,
                "DATABASE_PATH": Path(tempdir) / "stretch.sqlite3",
                "GROQ_API_KEY": "",
                "SUBMISSION_RATE_LIMIT": "1000 per minute",
            }
        )
        client = app.test_client()

        text_response = client.post(
            "/submit",
            json={
                "creator_id": "stretch-human",
                "content": TEXT_SAMPLE,
            },
        )
        image_response = client.post(
            "/submit",
            json={
                "creator_id": "stretch-image",
                "content_type": "image_description",
                "image_description": IMAGE_DESCRIPTION_SAMPLE,
            },
        )
        metadata_response = client.post(
            "/submit",
            json={
                "creator_id": "stretch-metadata",
                "content_type": "metadata",
                "metadata": METADATA_SAMPLE,
            },
        )

        submissions = [
            text_response.get_json(),
            image_response.get_json(),
            metadata_response.get_json(),
        ]
        assert all(response.status_code == 201 for response in [text_response, image_response, metadata_response])
        assert all(len(submission["signals"]) >= 3 for submission in submissions)

        print("\nENSEMBLE + MULTI-MODAL SUBMISSIONS")
        pprint(
            [
                {
                    "content_id": submission["content_id"],
                    "content_type": submission["content_type"],
                    "attribution": submission["attribution"],
                    "confidence": submission["confidence"],
                    "signals": [signal["name"] for signal in submission["signals"]],
                }
                for submission in submissions
            ]
        )

        certificate_response = client.post(
            "/certificate",
            json={
                "content_id": submissions[0]["content_id"],
                "creator_id": "stretch-human",
                "verification_method": "draft_history",
                "evidence_summary": (
                    "Creator supplied timestamped draft notes and revision history "
                    "that match the submitted piece."
                ),
            },
        )
        certificate = certificate_response.get_json()
        assert certificate_response.status_code == 201
        assert certificate["status"] == "verified_human"

        print("\nPROVENANCE CERTIFICATE")
        pprint(certificate)

        appeal_response = client.post(
            "/appeal",
            json={
                "content_id": submissions[1]["content_id"],
                "creator_reasoning": "The image description came from my own studio notes.",
            },
        )
        assert appeal_response.status_code == 201

        analytics_response = client.get("/api/analytics")
        analytics = analytics_response.get_json()
        assert analytics_response.status_code == 200
        assert analytics["total_submissions"] == 3
        assert analytics["appeal_count"] == 1
        assert analytics["certificate_count"] == 1

        dashboard_response = client.get("/dashboard")
        assert dashboard_response.status_code == 200
        assert "Detection Patterns" in dashboard_response.get_data(as_text=True)

        print("\nANALYTICS DASHBOARD SUMMARY")
        pprint(analytics)
        print("\nDASHBOARD")
        pprint({"status_code": dashboard_response.status_code, "contains_detection_patterns": True})


if __name__ == "__main__":
    main()
