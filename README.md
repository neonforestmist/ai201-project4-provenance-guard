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

Run the Milestone 5 production-layer evidence script:

```bash
python scripts/milestone5_demo.py
```

Prepare the portfolio walkthrough:

```bash
cat docs/walkthrough_script.md
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

## Milestone 5 Evidence

Milestone 5 adds the production layer: all three transparency label variants, a course-compatible appeals workflow, rate limiting, and a complete structured audit log.

Verification commands:

```bash
python -m unittest discover -s tests
python scripts/milestone5_demo.py
```

The demo script proves:

| Feature | Evidence |
| --- | --- |
| Transparency labels | Submits three samples through `POST /submit` and confirms `likely_ai`, `likely_human`, and `uncertain` all return the exact label text from `planning.md`. |
| Appeals workflow | Sends `POST /appeal` with `content_id` and `creator_reasoning`; the response returns `status: under_review` and the stored appeal reasoning. |
| Rate limiting | Runs a separate app instance with `SUBMISSION_RATE_LIMIT="2 per minute"` and gets status codes `[201, 201, 429]`. |
| Complete audit log | Reads `GET /log?limit=10` and shows classification entries with signal counts plus an appeal entry with `appeal_reasoning`. |

The production default submission limit is `12 per minute; 100 per day`. The lower demo limit is only used to make the `429` proof quick and repeatable.

## Milestone 6 Evidence

Milestone 6 is the final documentation and walkthrough pass. This README is the canonical project record: it explains the architecture, why each detection signal exists, how confidence scoring communicates uncertainty, exact transparency label text, rate-limit choices, audit-log evidence, limitations, spec reflection, and AI usage. The short recording outline for the separate Course Portal video is in `docs/walkthrough_script.md`.

## Architecture Overview

A submitted text enters through `POST /api/submissions` or the course-compatible `POST /submit` alias. Flask validates that the body is long enough to analyze, then Flask-Limiter checks the per-client submission limit before any scoring work happens. The detection pipeline runs independent signals over the same text: a Groq LLM review when an API key is present, local stylometric heuristics, and a local formulaic-pattern scan.

Each signal returns the same normalized shape: an AI probability, confidence, availability flag, rationale, and signal-specific details. The ensemble scorer weights the available signals into one `ai_probability`, then calculates `confidence_score` from distance away from the uncertain middle plus signal agreement. The label selector maps that result to one of three reader-facing transparency labels. SQLite stores the submission, content hash, scores, signal details, label text, status, and timestamps, then writes the same decision to the structured `audit_log`.

If the creator disagrees, they send `POST /api/appeals` or `POST /appeal` with the content ID and creator reasoning. The app verifies the original submission exists, records the appeal, updates the submission to `under_review`, and writes an appeal event beside the original classification decision in the audit log. Reviewers can inspect the current status with `GET /api/submissions/<id>` and inspect the evidence stream with `GET /api/log` or `GET /log`.

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
  "content_id": "uuid",
  "status": "classified",
  "attribution_result": "uncertain",
  "attribution": "uncertain",
  "ai_probability": 0.541,
  "confidence_score": 0.571,
  "confidence": 0.571,
  "transparency_label": "Provenance Guard: We cannot confidently determine how this piece was created. Readers should treat the attribution as uncertain, and the creator can provide more context.",
  "label": "Provenance Guard: We cannot confidently determine how this piece was created. Readers should treat the attribution as uncertain, and the creator can provide more context.",
  "appeal_filed": false,
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

Milestone 5 compatibility alias: `POST /appeal` accepts `content_id` as an alias for `submission_id` and `creator_reasoning` as an alias for `reason`.

```json
{
  "submission_id": "uuid-from-submit-response",
  "content_id": "same-uuid-if-using-the-course-alias",
  "creator_id": "creator-demo",
  "reason": "This was drafted from my notebook and I can provide earlier versions for review.",
  "creator_reasoning": "Same field, accepted for the course-compatible /appeal route."
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

I chose Groq plus stylometry as the required independent pair because they look at different evidence. Groq can make a holistic language judgment, while stylometry ignores meaning and measures structure. The formulaic scan is the stretch-style third signal. It catches repeated template phrasing that is related to, but not identical to, sentence uniformity. That extra signal also keeps local demos useful when Groq is unavailable.

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

Example scores from `python scripts/milestone4_eval.py` with local deterministic scoring:

| Sample | AI probability | Confidence score | Result | Why it landed there |
| --- | ---: | ---: | --- | --- |
| `casual_human` | `0.120` | `0.874` | `human_written` | Both local signals show low AI evidence: stylometry `0.180`, formulaic scan `0.000`. The score is far from the uncertain middle, so confidence is high. |
| `template_ai` | `0.740` | `0.738` | `ai_generated` | Stylometry `0.648` and formulaic scan `0.925` both point toward AI-like structure, enough to cross the high-confidence AI threshold. |
| `borderline_formulaic` | `0.517` | `0.506` | `uncertain` | The formulaic scan is high at `0.910`, but stylometry is lower at `0.320`. That disagreement keeps confidence low and prevents an overclaimed label. |

The third row is the important validation case: a text can contain AI-like phrases and still receive `uncertain` when signals do not agree strongly enough. That behavior is intentional because the system should protect human creators from brittle false positives.

## Transparency Labels

The label text returned by the API is written for readers, not developers.

| Variant | Exact label text |
| --- | --- |
| High-confidence AI | "Provenance Guard: This piece appears likely to be AI-generated. Multiple review signals point in that direction with high confidence. The creator can appeal this label." |
| High-confidence human | "Provenance Guard: This piece appears likely to be human-written. The review found limited AI-generation signals, but this is not a guarantee." |
| Uncertain | "Provenance Guard: We cannot confidently determine how this piece was created. Readers should treat the attribution as uncertain, and the creator can provide more context." |

## Rate Limiting

`POST /api/submissions` is limited to `12 per minute; 100 per day` per remote address.

Reasoning: a real writing platform might see a creator checking several drafts in a burst, so the per-minute limit allows normal experimentation. The daily cap blocks automated flooding and repeated adversarial probing without blocking realistic personal usage. When the limit is hit, Flask-Limiter returns HTTP `429` with a JSON error message. `python scripts/milestone5_demo.py` verifies this path with a temporary `2 per minute` limit and receives `[201, 201, 429]`.

## Audit Log

The audit log is stored in SQLite at `data/provenance_guard.sqlite3` by default. Each classification entry includes timestamp, content ID, attribution result, confidence score, content hash, label text, individual signal scores, and `appeal_filed: false`. Each appeal entry includes the content ID, creator reasoning, `status: under_review`, `appeal_filed: true`, and the original decision.

Example visible entries from `GET /api/log?limit=3` after running `python scripts/seed_demo.py`:

```json
{
  "entries": [
    {
      "event_type": "appeal_submitted",
      "payload": {
        "status": "under_review",
        "appeal_reasoning": "The creator says this was drafted from their own outline and wants manual review.",
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

Short poems are a weak spot because there may not be enough sentence variety or vocabulary range for stylometry to measure reliably. Highly polished school essays and non-native English writing can also be misclassified because they may use repeated transition phrases, restrained punctuation, and uniform sentence structures that the stylometric and formulaic signals treat as AI-like. Intentionally repetitive experimental writing is another risky case: the formulaic scan may treat artistic repetition as template repetition.

The Groq signal reduces some of those blind spots by reading semantics, but it still cannot know the creator's drafting history and may inherit model bias around what "AI-like" prose sounds like. For real deployment, I would add more creator-controlled evidence such as draft history, optional verification, reviewer notes, and appeal outcomes before making strong product decisions from the score.

## Spec Reflection

The spec helped most by forcing the architecture to include both the original decision and the appeal path from the beginning. Because the assignment asked for the audit log, status update, and transparency label together, I designed submissions, appeals, labels, and logging as one flow instead of treating appeals as an afterthought.

The main divergence from my first plan was adding `formulaic_pattern_scan` as a third lightweight signal. The required design only needed Groq plus stylometry, but repeated template language felt distinct enough to measure separately. I kept its ensemble weight smaller than Groq and stylometry because formal human writing can trigger those markers. I also kept the label thresholds conservative to reflect the project hint that false positives against human creators are especially harmful.

## AI Usage

I used Codex in several specific places, but I treated the output as a draft to inspect and revise.

1. I directed Codex to turn the planning architecture into a Flask backend with submission, appeal, and audit-log routes. It produced the initial app factory, SQLite store, and route structure. I revised the API shape to keep both canonical routes and course-compatible aliases (`/api/submissions` plus `/submit`, `/api/appeals` plus `/appeal`) and added explicit audit fields such as `content_id`, `appeal_filed`, and `appeal_reasoning`.

2. I directed Codex to implement the scoring pipeline from the planned signals. It produced Groq, stylometric, and formulaic signal functions plus the weighted combiner. I revised the confidence thresholds to be conservative, added deterministic tests for high-confidence and uncertain cases, and checked that borderline formulaic writing stayed `uncertain` instead of being forced into an AI label.

3. I used Codex to draft evidence sections for the README and the milestone demo scripts. I revised the language to avoid claiming perfect detection, added actual score examples from the test script, and made the transparency labels readable for non-technical platform users.

## Portfolio Walkthrough

The required walkthrough video is submitted separately through the Course Portal. The repo includes a short script at `docs/walkthrough_script.md` that walks through the architecture, runs the demo evidence, and gives a few design decisions to narrate. The fastest recording path is:

```bash
source .venv/bin/activate
python scripts/milestone5_demo.py
python -m unittest discover -s tests
```

The video should show the README architecture section, run the milestone demo, point out the three labels, show the appeal status changing to `under_review`, show the audit-log entries, and briefly explain why uncertain is a real product state rather than a failure.

## Submission Checklist

- `POST /api/submissions` returns structured JSON with result, confidence, label, and per-signal scores.
- At least two distinct detection signals are implemented; the app includes three.
- README includes an architecture overview of the submission and appeal paths.
- README includes confidence-scoring reasoning plus actual high-confidence and lower-confidence example scores.
- README includes confidence thresholds and all three label variants as exact text.
- `POST /api/appeals` and `POST /appeal` record creator reasoning and mark the submission `under_review`.
- `POST /api/submissions` is rate-limited and documents the chosen limits.
- `GET /api/log` returns structured audit entries with classifications and appeals.
- `planning.md` includes an `## Architecture` section with a diagram and design narrative.
- `docs/walkthrough_script.md` prepares the short portfolio walkthrough video.
