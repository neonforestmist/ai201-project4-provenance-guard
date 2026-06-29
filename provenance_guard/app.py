from pathlib import Path
from typing import Optional

from flask import Flask, current_app, jsonify, render_template_string, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from provenance_guard.config import Config
from provenance_guard.content import normalize_submission_payload
from provenance_guard.detectors import classify_content
from provenance_guard.storage import AuditStore


ALLOWED_CERTIFICATE_METHODS = {
    "draft_history",
    "platform_identity",
    "manual_review",
}


def create_app(test_config: Optional[dict] = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    database_path = Path(app.config["DATABASE_PATH"])
    store = AuditStore(database_path)
    app.extensions["audit_store"] = store

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )
    app.extensions["limiter"] = limiter

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify(
            {
                "error": "rate_limit_exceeded",
                "message": "Too many submissions. Please wait before trying again.",
                "limit": current_app.config["SUBMISSION_RATE_LIMIT"],
            }
        ), 429

    @app.get("/")
    def index():
        return jsonify(
            {
                "service": "Provenance Guard",
                "routes": {
                    "health": "GET /health",
                    "submit": "POST /api/submissions",
                    "appeal": "POST /api/appeals or POST /appeal",
                    "log": "GET /api/log",
                    "certificate": "POST /api/certificates or POST /certificate",
                    "analytics": "GET /api/analytics",
                    "dashboard": "GET /dashboard",
                },
            }
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    def classify_submission_payload(payload: dict):
        normalized, error = normalize_submission_payload(payload)
        if error:
            return jsonify(error), 400

        content = normalized.analysis_text.strip()
        creator_id = payload.get("creator_id")

        if len(content) < 40:
            return jsonify(
                {
                    "error": "content_too_short",
                    "message": "Submit at least 40 characters so the signals have enough text to evaluate.",
                }
            ), 400

        decision = classify_content(
            content,
            groq_api_key=current_app.config.get("GROQ_API_KEY"),
            groq_model=current_app.config.get("GROQ_MODEL"),
        )
        submission = current_app.extensions["audit_store"].create_submission(
            content=content,
            creator_id=creator_id,
            decision=decision,
            content_type=normalized.content_type,
            source_payload=normalized.source_payload,
        )
        return jsonify(submission), 201

    @app.post("/api/submissions")
    @limiter.limit(lambda: current_app.config["SUBMISSION_RATE_LIMIT"])
    def submit_content():
        payload = request.get_json(silent=True) or {}
        return classify_submission_payload(payload)

    @app.post("/submit")
    @limiter.limit(lambda: current_app.config["SUBMISSION_RATE_LIMIT"])
    def submit_content_alias():
        payload = request.get_json(silent=True) or {}
        return classify_submission_payload(payload)

    @app.get("/api/submissions/<submission_id>")
    def get_submission(submission_id: str):
        submission = current_app.extensions["audit_store"].get_submission(submission_id)
        if not submission:
            return jsonify({"error": "not_found"}), 404
        return jsonify(submission)

    def create_appeal_from_payload(payload: dict):
        submission_id = (payload.get("submission_id") or payload.get("content_id") or "").strip()
        reason = (payload.get("reason") or payload.get("creator_reasoning") or "").strip()
        creator_id = payload.get("creator_id")

        if not submission_id:
            return jsonify({"error": "missing_submission_id"}), 400
        if len(reason) < 20:
            return jsonify(
                {
                    "error": "reason_too_short",
                    "message": "Explain the creator's reasoning in at least 20 characters.",
                }
            ), 400

        appeal = current_app.extensions["audit_store"].create_appeal(
            submission_id=submission_id,
            creator_id=creator_id,
            reason=reason,
        )
        if not appeal:
            return jsonify({"error": "submission_not_found"}), 404
        return jsonify(appeal), 201

    @app.post("/api/appeals")
    def submit_appeal():
        payload = request.get_json(silent=True) or {}
        return create_appeal_from_payload(payload)

    @app.post("/appeal")
    def submit_appeal_alias():
        payload = request.get_json(silent=True) or {}
        return create_appeal_from_payload(payload)

    def create_certificate_from_payload(payload: dict):
        submission_id = (payload.get("submission_id") or payload.get("content_id") or "").strip()
        creator_id = payload.get("creator_id")
        verification_method = (payload.get("verification_method") or payload.get("method") or "").strip()
        evidence_summary = (payload.get("evidence_summary") or payload.get("evidence") or "").strip()

        if not submission_id:
            return jsonify({"error": "missing_submission_id"}), 400
        if verification_method not in ALLOWED_CERTIFICATE_METHODS:
            return jsonify(
                {
                    "error": "unsupported_verification_method",
                    "message": "Use draft_history, platform_identity, or manual_review.",
                }
            ), 400
        if len(evidence_summary) < 30:
            return jsonify(
                {
                    "error": "evidence_too_short",
                    "message": "Summarize the additional human-verification evidence in at least 30 characters.",
                }
            ), 400

        submission = current_app.extensions["audit_store"].get_submission(submission_id)
        if not submission:
            return jsonify({"error": "submission_not_found"}), 404
        if submission.get("creator_id") and creator_id and submission["creator_id"] != creator_id:
            return jsonify({"error": "creator_mismatch"}), 403

        certificate = current_app.extensions["audit_store"].create_certificate(
            submission_id=submission_id,
            creator_id=creator_id or submission.get("creator_id"),
            verification_method=verification_method,
            evidence_summary=evidence_summary,
        )
        if not certificate:
            return jsonify({"error": "submission_not_found"}), 404
        return jsonify(certificate), 201

    @app.post("/api/certificates")
    def issue_certificate():
        payload = request.get_json(silent=True) or {}
        return create_certificate_from_payload(payload)

    @app.post("/certificate")
    def issue_certificate_alias():
        payload = request.get_json(silent=True) or {}
        return create_certificate_from_payload(payload)

    def audit_log_response():
        raw_limit = request.args.get("limit", "50")
        try:
            limit = max(1, min(int(raw_limit), 100))
        except ValueError:
            limit = 50
        entries = current_app.extensions["audit_store"].list_audit_log(limit=limit)
        return jsonify({"entries": entries, "count": len(entries)})

    @app.get("/api/log")
    def audit_log():
        return audit_log_response()

    @app.get("/log")
    def audit_log_alias():
        return audit_log_response()

    @app.get("/api/analytics")
    def analytics_summary():
        summary = current_app.extensions["audit_store"].analytics_summary()
        return jsonify(summary)

    @app.get("/dashboard")
    def dashboard():
        summary = current_app.extensions["audit_store"].analytics_summary()
        return render_template_string(
            """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <title>Provenance Guard Analytics</title>
              <style>
                body {
                  color: #1f2937;
                  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                  line-height: 1.45;
                  margin: 32px auto;
                  max-width: 920px;
                }
                h1, h2 { color: #111827; }
                table {
                  border-collapse: collapse;
                  margin: 16px 0 28px;
                  width: 100%;
                }
                th, td {
                  border-bottom: 1px solid #d1d5db;
                  padding: 10px 12px;
                  text-align: left;
                }
                th { background: #f3f4f6; }
                .metrics {
                  display: grid;
                  gap: 12px;
                  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                  margin: 16px 0 28px;
                }
                .metric {
                  border: 1px solid #d1d5db;
                  border-radius: 6px;
                  padding: 12px;
                }
                .value {
                  display: block;
                  font-size: 1.55rem;
                  font-weight: 700;
                  margin-top: 4px;
                }
              </style>
            </head>
            <body>
              <h1>Provenance Guard Analytics</h1>
              <section class="metrics" aria-label="Summary metrics">
                <div class="metric">Total submissions <span class="value">{{ summary.total_submissions }}</span></div>
                <div class="metric">Appeal rate <span class="value">{{ "%.1f"|format(summary.appeal_rate * 100) }}%</span></div>
                <div class="metric">Average confidence <span class="value">{{ "%.3f"|format(summary.average_confidence_score) }}</span></div>
                <div class="metric">Verified-human rate <span class="value">{{ "%.1f"|format(summary.verified_human_rate * 100) }}%</span></div>
              </section>

              <h2>Detection Patterns</h2>
              <table>
                <thead><tr><th>Attribution result</th><th>Count</th></tr></thead>
                <tbody>
                {% for name, count in summary.detection_patterns.attribution_counts.items() %}
                  <tr><td>{{ name }}</td><td>{{ count }}</td></tr>
                {% endfor %}
                </tbody>
              </table>

              <h2>Content Types</h2>
              <table>
                <thead><tr><th>Content type</th><th>Count</th></tr></thead>
                <tbody>
                {% for name, count in summary.detection_patterns.content_type_counts.items() %}
                  <tr><td>{{ name }}</td><td>{{ count }}</td></tr>
                {% endfor %}
                </tbody>
              </table>
            </body>
            </html>
            """,
            summary=summary,
        )

    return app
