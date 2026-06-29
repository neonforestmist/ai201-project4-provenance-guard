import sys
from pathlib import Path
from pprint import pprint


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provenance_guard.app import create_app


SAMPLES = [
    {
        "creator_id": "demo-human-1",
        "content": (
            "My grandmother kept basil on the windowsill in a cracked blue mug. "
            "Every Sunday, the kitchen smelled like rain on concrete and garlic "
            "warming in oil, and I wrote her grocery lists on envelopes."
        ),
    },
    {
        "creator_id": "demo-ai-1",
        "content": (
            "In today's rapidly evolving creative landscape, it is important to note "
            "that innovation empowers communities. Overall, this essay explores how "
            "technology can enhance expression, foster collaboration, and unlock new "
            "opportunities for meaningful human connection."
        ),
    },
    {
        "creator_id": "demo-uncertain-1",
        "content": (
            "The river moved quietly beside the warehouse. I wanted the ending to feel "
            "earned, but the sentence kept folding back on itself, part memory and part "
            "stage direction."
        ),
    },
]


def main():
    app = create_app({"SUBMISSION_RATE_LIMIT": "1000 per minute"})
    client = app.test_client()

    submission_ids = []
    for sample in SAMPLES:
        response = client.post("/api/submissions", json=sample)
        data = response.get_json()
        submission_ids.append(data["submission_id"])
        print("\nSUBMISSION")
        pprint(
            {
                "status": response.status_code,
                "submission_id": data["submission_id"],
                "result": data["attribution_result"],
                "confidence": data["confidence_score"],
                "label": data["transparency_label"],
            }
        )

    appeal_response = client.post(
        "/api/appeals",
        json={
            "submission_id": submission_ids[1],
            "creator_id": "demo-ai-1",
            "reason": "The creator says this was drafted from their own outline and wants manual review.",
        },
    )
    print("\nAPPEAL")
    pprint(appeal_response.get_json())

    log_response = client.get("/api/log?limit=10")
    print("\nAUDIT LOG")
    pprint(log_response.get_json())


if __name__ == "__main__":
    main()
