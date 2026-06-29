# Portfolio Walkthrough Script

Use this as a short recording guide for the Course Portal video. Aim for 2 to 3 minutes.

## Before Recording

Open the repo and activate the virtual environment:

```bash
source .venv/bin/activate
```

Optional sanity check:

```bash
python -m unittest discover -s tests
```

## Recording Flow

1. Start on the README.

Say: "This is Provenance Guard, a Flask backend for creative platforms that need to label whether submitted writing appears AI-generated, human-written, or uncertain without pretending the detector is perfect."

2. Show the architecture overview.

Say: "A submission enters through `/submit`, passes validation and rate limiting, then runs through independent signals: Groq when configured, stylometric heuristics, and a formulaic pattern scan. The scorer combines those into an AI probability and confidence score, selects a transparency label, stores the result in SQLite, and writes an audit-log entry."

3. Run the production-layer demo.

```bash
python scripts/milestone5_demo.py
```

Point out:

- The three transparency labels all appear.
- The high-confidence AI and high-confidence human cases get clear labels.
- The borderline case stays `uncertain`.

4. Show the appeal workflow in the demo output.

Say: "The creator can appeal with reasoning. The appeal updates the content status to `under_review` and records `appeal_reasoning` in the audit log beside the original classification."

5. Show the audit log and rate-limit proof.

Say: "The audit log is structured JSON with content IDs, statuses, confidence, signal evidence, and appeal fields. The demo also lowers the limit to `2 per minute` so it can show `[201, 201, 429]` quickly. The production default is `12 per minute; 100 per day`."

6. Mention design decisions.

Say: "The most important design choice was to make uncertainty a real outcome. If signals disagree, the system avoids a strong accusation and shows the uncertain label. That matters because false positives can hurt human creators."

7. Mention limitations.

Say: "This system can still get polished essays, short poems, non-native English writing, or intentionally repetitive experimental writing wrong because those styles can look uniform or formulaic to the local signals. That is why the appeal path and audit log are part of the core design."

## Closing Line

Say: "The detailed evidence is in the README and source code. The walkthrough just shows the end-to-end flow: submit, score, label, appeal, audit, and rate-limit."
