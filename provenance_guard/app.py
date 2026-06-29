from pathlib import Path
from typing import Optional

from flask import Flask, current_app, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from provenance_guard.config import Config
from provenance_guard.detectors import classify_content
from provenance_guard.storage import AuditStore


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
                    "appeal": "POST /api/appeals",
                    "log": "GET /api/log",
                },
            }
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    def classify_submission_payload(payload: dict):
        content = (payload.get("content") or payload.get("text") or "").strip()
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

    @app.post("/api/appeals")
    def submit_appeal():
        payload = request.get_json(silent=True) or {}
        submission_id = (payload.get("submission_id") or "").strip()
        reason = (payload.get("reason") or "").strip()
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

    @app.get("/api/log")
    def audit_log():
        raw_limit = request.args.get("limit", "50")
        try:
            limit = max(1, min(int(raw_limit), 100))
        except ValueError:
            limit = 50
        entries = current_app.extensions["audit_store"].list_audit_log(limit=limit)
        return jsonify({"entries": entries, "count": len(entries)})

    return app
