# Provenance Guard

Provenance Guard is a Flask backend for creative sharing platforms that need to label submitted writing with fair attribution context. It classifies a text submission, returns a confidence-aware transparency label, rate-limits submissions, stores structured audit entries, and lets creators appeal a classification.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your Groq key to `.env`:

```bash
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
flask --app app run --debug
```

Run tests:

```bash
python -m unittest discover -s tests
```

Seed demo submissions and an appeal:

```bash
python scripts/seed_demo.py
```

## Milestone 3 Evidence

Milestone 3 asks for the Flask submission endpoint and first detection signal to work end to end. This repo now supports both the canonical `POST /api/submissions` route and a course-wording-compatible `POST /submit` alias. The first signal is `groq_llm_classification`, which calls Groq `llama-3.3-70b-versatile` when `GROQ_API_KEY` is configured and returns an auditable signal object with `ai_probability`, `confidence`, `available`, `rationale`, and model details.

Verification commands:

```bash
python -m unittest discover -s tests
flask --app app run --debug

curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "creator-demo",
    "content": "In a rapidly evolving creative landscape, it is important to note that storytelling empowers communities. Overall, this essay explores how technology can enhance expression, foster collaboration, and unlock new opportunities for meaningful human connection."
  }'
```

A successful response includes `submission_id`, `attribution_result`, `confidence_score`, `transparency_label`, and a `signals` array containing `groq_llm_classification`.

## Milestone 4 Evidence

Milestone 4 adds the second detection signal and real confidence scoring. The second signal is `stylometric_heuristics`, a standalone function that measures sentence-length variance, vocabulary diversity, average sentence length, and punctuation density. The app combines that score with `groq_llm_classification` and the optional `formulaic_pattern_scan` ensemble signal to produce `ai_probability`, `confidence_score`, and one of three label categories.

Run the four-input scoring check:

```bash
python scripts/milestone4_eval.py
```

This script uses deterministic local scoring and skips live Groq calls so the comparison remains stable. The Flask app still uses Groq automatically when `GROQ_API_KEY` is configured.

Expected local output pattern:

| Sample | Expected pattern |
| --- | --- |
| `template_ai` | Highest AI probability; should map to `ai_generated`. |
| `casual_human` | Lowest AI probability; should map to `human_written`. |
| `borderline_formulaic` | Middle score; should stay `uncertain`. |
| `borderline_mixed_human` | Middle score; should stay `uncertain`. |

The audit log records individual signal scores and the combined result. Use either endpoint:

```bash
curl -s http://127.0.0.1:5000/api/log?limit=3
curl -s http://127.0.0.1:5000/log?limit=3
```

## API

### Submit content

`POST /api/submissions`

Milestone 3 compatibility alias: `POST /submit` accepts the same JSON body. It also accepts `text` as an alias for `content`, but `content` is the canonical field used in the rest of the API.

```json
{
  "creator_id": "creator-demo",
  "content": "A poem, short story excerpt, blog post, or other text-based creative work..."
}
```

The response includes a structured attribution result, confidence score, transparency label, and individual signal scores:

```json
{
  "submission_id": "uuid",
  "status": "classified",
  "attribution_result": "uncertain",
  "ai_probability": 0.541,
  "confidence_score": 0.571,
  "transparency_label": "Provenance Guard: We cannot confidently determine how this piece was created. Readers should treat the attribution as uncertain, and the creator can provide more context.",
  "signals": [
    {
      "name": "groq_llm_classification",
      "ai_probability": 0.5,
      "confidence": 0.0,
      "available": false
    },
    {
      "name": "stylometric_heuristics",
      "ai_probability": 0.62,
      "confidence": 0.57,
      "available": true
    },
    {
      "name": "formulaic_pattern_scan",
      "ai_probability": 0.28,
      "confidence": 0.64,
      "available": true
    }
  ]
}
```

### Appeal a classification

`POST /api/appeals`

```json
{
  "submission_id": "uuid-from-submit-response",
  "creator_id": "creator-demo",
  "reason": "This was drafted from my notebook and I can provide earlier versions for review."
}
```

The appeal endpoint stores the creator's reasoning, logs the appeal beside the original decision, and updates the content status to `under_review`.

### View the audit log

`GET /api/log?limit=10`

Milestone compatibility alias: `GET /log?limit=10`.

Returns structured JSON entries ordered newest-first.

## Detection Signals

This project uses an ensemble of three distinct signals. The first two satisfy the required multi-signal pipeline; the third adds a small stretch-style ensemble signal and makes local development useful before the Groq key is configured.

| Signal | What it measures | What it misses |
| --- | --- | --- |
| `groq_llm_classification` | A semantic, holistic judgment from Groq `llama-3.3-70b-versatile` about whether the text reads as AI-generated. | It can overreact to polished human writing and depends on the external API being available. |
| `stylometric_heuristics` | Sentence-length variance, vocabulary diversity, average sentence length, and punctuation density. | It cannot understand meaning, authorship history, genre, or deliberate stylistic choices. |
| `formulaic_pattern_scan` | Template-like phrases, repeated bigrams, and repeated sentence openings. | It can mistake intentionally formal writing for generated writing and misses subtle AI text with varied wording. |

Weights are `55% Groq`, `30% stylometry`, and `15% formulaic pattern scan` when Groq is available. If Groq is not configured, the local signals are reweighted so the app can still run, but the final demo should include a real Groq key.

## Confidence and Uncertainty

The system calculates `ai_probability` as a weighted average of available signal scores. It then converts distance from `0.50` into a `confidence_score` and adjusts it slightly based on agreement between signals.

Thresholds:

| Case | Rule | Result |
| --- | --- | --- |
| High-confidence AI | `ai_probability >= 0.72` and `confidence_score >= 0.70` | `ai_generated` |
| High-confidence human | `ai_probability <= 0.28` and `confidence_score >= 0.70` | `human_written` |
| Uncertain | Anything between those ranges or with low confidence | `uncertain` |

I tested this by submitting polished formulaic text, more idiosyncratic personal prose, and mixed/shorter creative excerpts. The scores are intentionally conservative because a false positive against a human creator is more harmful than a missed AI-generated piece.

## Transparency Labels

The label text returned by the API is written for readers, not developers.

| Variant | Exact label text |
| --- | --- |
| High-confidence AI | "Provenance Guard: This piece appears likely to be AI-generated. Multiple review signals point in that direction with high confidence. The creator can appeal this label." |
| High-confidence human | "Provenance Guard: This piece appears likely to be human-written. The review found limited AI-generation signals, but this is not a guarantee." |
| Uncertain | "Provenance Guard: We cannot confidently determine how this piece was created. Readers should treat the attribution as uncertain, and the creator can provide more context." |

## Rate Limiting

`POST /api/submissions` is limited to `12 per minute; 100 per day` per remote address.

Reasoning: a real writing platform might see a creator checking several drafts in a burst, so the per-minute limit allows normal experimentation. The daily cap blocks automated flooding and repeated adversarial probing without blocking realistic personal usage. When the limit is hit, Flask-Limiter returns HTTP `429` with a JSON error message.

## Audit Log

The audit log is stored in SQLite at `data/provenance_guard.sqlite3` by default. Each classification entry includes timestamp, result, confidence score, content hash, label text, and signal details. Each appeal entry includes the creator's reasoning and the original decision.

Example visible entries from `GET /api/log?limit=3` after running `python scripts/seed_demo.py`:

```json
{
  "entries": [
    {
      "event_type": "appeal_submitted",
      "payload": {
        "status": "under_review",
        "reason": "The creator says this was drafted from their own outline and wants manual review.",
        "original_decision": {
          "attribution_result": "uncertain",
          "confidence_score": 0.61
        }
      }
    },
    {
      "event_type": "classification_decision",
      "payload": {
        "attribution_result": "ai_generated",
        "confidence_score": 0.78,
        "signals": ["groq_llm_classification", "stylometric_heuristics", "formulaic_pattern_scan"]
      }
    },
    {
      "event_type": "classification_decision",
      "payload": {
        "attribution_result": "human_written",
        "confidence_score": 0.74,
        "signals": ["groq_llm_classification", "stylometric_heuristics", "formulaic_pattern_scan"]
      }
    }
  ]
}
```

## Known Limitations

Short poems, highly polished human essays, and intentionally repetitive experimental writing are likely weak spots. The stylometric and formulaic signals may treat formal structure as suspicious, while the LLM signal may not know the creator's actual drafting history. The appeals workflow exists because the system should not pretend that automated provenance detection is definitive.

## Spec Reflection

The original plan was the recommended two-signal design: Groq plus stylometric heuristics. During implementation I added `formulaic_pattern_scan` as a third lightweight signal because it captures template repetition separately from broad stylometry and gives the app a useful local signal when Groq is not configured. I kept the final label thresholds conservative to match the project hint that false positives against human creators are especially harmful.

## AI Usage

I used Codex to scaffold the Flask routes, SQLite audit store, detection pipeline, tests, and documentation from the CodePath Project 4 spec and grading rubric. I reviewed the generated structure against the rubric and revised the plan to include visible per-signal scores, exact label text in the README, and an appeal entry that appears alongside the original classification in the audit log.

I also used AI assistance to draft the architecture narrative and confidence-threshold explanation. I revised the output to keep the language conservative, to avoid claiming perfect AI detection, and to make the labels understandable to non-technical readers.

## Submission Checklist

- `POST /api/submissions` returns structured JSON with result, confidence, label, and per-signal scores.
- At least two distinct detection signals are implemented; the app includes three.
- README includes confidence thresholds and all three label variants as exact text.
- `POST /api/appeals` records creator reasoning and marks the submission `under_review`.
- `POST /api/submissions` is rate-limited and documents the chosen limits.
- `GET /api/log` returns structured audit entries with classifications and appeals.
- `planning.md` includes an `## Architecture` section with a diagram and design narrative.
