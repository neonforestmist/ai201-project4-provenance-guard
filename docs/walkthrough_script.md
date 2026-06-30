# Portfolio Walkthrough Video Script

Target length: 2 to 3 minutes.

## Setup

Open the repo in your terminal and run:

```bash
source .venv/bin/activate
python -m unittest discover -s tests
```

Keep these files ready to show:

- `README.md`
- `planning.md`
- `scripts/milestone5_demo.py`
- `scripts/stretch_demo.py`

## 0:00-0:20 - Intro

Screen: Show the top of `README.md`.

Say:

"Hi, this is Provenance Guard, my Project 4 backend for CodePath AI201. The goal is to help a creative sharing platform give readers fair context about whether a piece of submitted content appears AI-generated, human-written, or uncertain. The system is intentionally cautious because a false AI accusation against a human creator can be harmful."

## 0:20-0:50 - Architecture

Screen: Show the architecture overview in `README.md` or the Mermaid diagram in `planning.md`.

Say:

"A submission comes into the Flask API through `/submit` or `/api/submissions`. The app accepts normal text, an image description, or structured metadata, then normalizes that into analysis text. It checks validation and rate limits, runs the detection signals, combines the signal scores into an AI probability and confidence score, selects a reader-facing transparency label, stores the result in SQLite, and writes a structured audit-log entry."

## 0:50-1:25 - Detection and Labels

Screen: Run:

```bash
python scripts/milestone5_demo.py
```

Say:

"Here I’m running the production-layer demo. The system returns three different transparency label variants. A high-confidence AI-like sample gets the likely AI label, a casual human-like sample gets the likely human label, and a mixed formulaic sample stays uncertain. That uncertain case is important: if the signals disagree or the confidence is low, the system avoids overclaiming."

Point out in the output:

- `likely_ai`
- `likely_human`
- `uncertain`
- confidence scores

## 1:25-1:55 - Appeals and Audit Log

Screen: Stay on the `milestone5_demo.py` output.

Say:

"The same demo also shows the appeals workflow. A creator can submit an appeal with their reasoning, and the content status changes to `under_review`. The appeal is written into the same audit log as the original classification, so reviewers can see both the original decision and the creator’s context. The audit log is structured JSON, not loose console output."

Point out:

- `status: under_review`
- `appeal_reasoning`
- `classification_decision`
- `appeal_submitted`

## 1:55-2:30 - Stretch Features

Screen: Run:

```bash
python scripts/stretch_demo.py
```

Say:

"I also implemented all four stretch features. First, the detector is an ensemble with three signals: Groq classification when configured, stylometric heuristics, and a formulaic pattern scan. Second, the provenance certificate endpoint can mark a piece as `verified_human` after extra evidence like draft history or manual review. Third, `/api/analytics` and `/dashboard` show detection patterns, appeal rate, average confidence, and verified-human rate. Fourth, the system supports image descriptions and structured metadata in addition to direct text."

Point out:

- `content_type: text`
- `content_type: image_description`
- `content_type: metadata`
- `Verified human creator`
- `appeal_rate`
- `average_confidence_score`

## 2:30-2:55 - Design Decisions and Limitations

Screen: Show README sections `Confidence and Uncertainty` and `Known Limitations`.

Say:

"The biggest design decision was making uncertainty a real product state instead of forcing a binary answer. The confidence score is based on distance from the uncertain middle and signal agreement. The main limitation is that polished essays, short poems, non-native English writing, or intentionally repetitive experimental writing can look formulaic to local signals. That is why the audit log, appeal workflow, and verified-human certificate are part of the design."

## Closing

Screen: Show the submission checklist in `README.md`.

Say:

"That’s the walkthrough: submit content, run multi-signal scoring, return a transparency label, support appeals, log the decision, rate-limit submissions, and provide the stretch features for certificates, analytics, and multi-modal input. The detailed evidence is in the README, tests, and demo scripts."

## Quick Backup Version

If you need a shorter version, say this:

"Provenance Guard is a Flask backend for labeling creative submissions as likely AI-generated, likely human-written, or uncertain. Submissions go through validation, rate limiting, three detection signals, weighted confidence scoring, transparency label selection, SQLite storage, and structured audit logging. The system is cautious because false positives can hurt creators, so uncertain is a real outcome. Creators can appeal, which updates the status to `under_review` and records their reasoning beside the original decision. For stretch, I added a three-signal ensemble, verified-human provenance certificates, an analytics dashboard, and support for image descriptions and structured metadata. The README documents the architecture, confidence examples, label text, rate limits, limitations, AI usage, and demo evidence."
