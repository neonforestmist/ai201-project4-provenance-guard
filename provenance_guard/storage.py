import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditStore:
    def __init__(self, database_path: Union[Path, str]):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    creator_id TEXT,
                    content_type TEXT NOT NULL DEFAULT 'text',
                    content_hash TEXT NOT NULL,
                    content_preview TEXT NOT NULL,
                    source_payload_json TEXT,
                    status TEXT NOT NULL,
                    attribution_result TEXT NOT NULL,
                    ai_probability REAL NOT NULL,
                    confidence_score REAL NOT NULL,
                    transparency_label TEXT NOT NULL,
                    signals_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS appeals (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    creator_id TEXT,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (submission_id) REFERENCES submissions(id)
                );

                CREATE TABLE IF NOT EXISTS certificates (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL UNIQUE,
                    creator_id TEXT,
                    verification_method TEXT NOT NULL,
                    evidence_summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    display_label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (submission_id) REFERENCES submissions(id)
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    submission_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )
            self._ensure_column(
                connection,
                "submissions",
                "content_type",
                "TEXT NOT NULL DEFAULT 'text'",
            )
            self._ensure_column(
                connection,
                "submissions",
                "source_payload_json",
                "TEXT",
            )

    def create_submission(
        self,
        content: str,
        creator_id: Optional[str],
        decision: dict,
        content_type: str = "text",
        source_payload: Optional[dict] = None,
    ) -> dict:
        submission_id = str(uuid.uuid4())
        created_at = utc_now()
        content_preview = content.strip().replace("\n", " ")[:180]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        source_payload = source_payload or {}
        payload = {
            "submission_id": submission_id,
            "content_id": submission_id,
            "creator_id": creator_id,
            "content_type": content_type,
            "status": "classified",
            "content_hash": content_hash,
            "content_preview": content_preview,
            "source_payload": source_payload,
            **decision,
            "attribution": decision["attribution_result"],
            "confidence": decision["confidence_score"],
            "label": decision["transparency_label"],
            "appeal_filed": False,
            "provenance_certificate": None,
            "created_at": created_at,
        }

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO submissions (
                    id, creator_id, content_type, content_hash, content_preview,
                    source_payload_json, status,
                    attribution_result, ai_probability, confidence_score,
                    transparency_label, signals_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    creator_id,
                    content_type,
                    content_hash,
                    content_preview,
                    json.dumps(source_payload),
                    "classified",
                    decision["attribution_result"],
                    decision["ai_probability"],
                    decision["confidence_score"],
                    decision["transparency_label"],
                    json.dumps(decision["signals"]),
                    created_at,
                    created_at,
                ),
            )
            self._log_event(
                connection,
                "classification_decision",
                submission_id,
                payload,
                created_at=created_at,
            )

        return payload

    def get_submission(self, submission_id: str) -> Optional[dict]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM submissions WHERE id = ?",
                (submission_id,),
            ).fetchone()
            appeal_exists = connection.execute(
                "SELECT 1 FROM appeals WHERE submission_id = ? LIMIT 1",
                (submission_id,),
            ).fetchone()
            certificate_row = connection.execute(
                "SELECT * FROM certificates WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        if not row:
            return None
        submission = self._submission_from_row(row)
        submission["appeal_filed"] = bool(appeal_exists)
        submission["provenance_certificate"] = (
            self._certificate_from_row(certificate_row)
            if certificate_row
            else None
        )
        return submission

    def create_appeal(self, submission_id: str, creator_id: Optional[str], reason: str) -> Optional[dict]:
        submission = self.get_submission(submission_id)
        if not submission:
            return None

        appeal_id = str(uuid.uuid4())
        created_at = utc_now()
        payload = {
            "appeal_id": appeal_id,
            "submission_id": submission_id,
            "content_id": submission_id,
            "creator_id": creator_id,
            "reason": reason,
            "creator_reasoning": reason,
            "appeal_reasoning": reason,
            "status": "under_review",
            "appeal_filed": True,
            "original_decision": {
                "attribution_result": submission["attribution_result"],
                "attribution": submission["attribution_result"],
                "ai_probability": submission["ai_probability"],
                "confidence_score": submission["confidence_score"],
                "confidence": submission["confidence_score"],
                "transparency_label": submission["transparency_label"],
                "label": submission["transparency_label"],
            },
            "created_at": created_at,
        }

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO appeals (id, submission_id, creator_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (appeal_id, submission_id, creator_id, reason, created_at),
            )
            connection.execute(
                "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
                ("under_review", created_at, submission_id),
            )
            self._log_event(
                connection,
                "appeal_submitted",
                submission_id,
                payload,
                created_at=created_at,
            )

        return payload

    def create_certificate(
        self,
        submission_id: str,
        creator_id: Optional[str],
        verification_method: str,
        evidence_summary: str,
    ) -> Optional[dict]:
        submission = self.get_submission(submission_id)
        if not submission:
            return None

        certificate_id = str(uuid.uuid4())
        created_at = utc_now()
        display_label = (
            "Verified human creator: additional provenance evidence was reviewed for this content."
        )
        payload = {
            "certificate_id": certificate_id,
            "submission_id": submission_id,
            "content_id": submission_id,
            "creator_id": creator_id,
            "verification_method": verification_method,
            "evidence_summary": evidence_summary,
            "status": "verified_human",
            "display_label": display_label,
            "created_at": created_at,
        }

        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO certificates (
                    id, submission_id, creator_id, verification_method,
                    evidence_summary, status, display_label, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    certificate_id,
                    submission_id,
                    creator_id,
                    verification_method,
                    evidence_summary,
                    "verified_human",
                    display_label,
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
                ("verified_human", created_at, submission_id),
            )
            self._log_event(
                connection,
                "certificate_issued",
                submission_id,
                {
                    **payload,
                    "original_decision": {
                        "attribution_result": submission["attribution_result"],
                        "confidence_score": submission["confidence_score"],
                        "transparency_label": submission["transparency_label"],
                    },
                },
                created_at=created_at,
            )

        return payload

    def analytics_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            total_submissions = connection.execute(
                "SELECT COUNT(*) AS count FROM submissions"
            ).fetchone()["count"]
            attribution_rows = connection.execute(
                """
                SELECT attribution_result, COUNT(*) AS count
                FROM submissions
                GROUP BY attribution_result
                """
            ).fetchall()
            content_type_rows = connection.execute(
                """
                SELECT content_type, COUNT(*) AS count
                FROM submissions
                GROUP BY content_type
                """
            ).fetchall()
            appeal_count = connection.execute(
                "SELECT COUNT(*) AS count FROM appeals"
            ).fetchone()["count"]
            certificate_count = connection.execute(
                "SELECT COUNT(*) AS count FROM certificates"
            ).fetchone()["count"]
            average_confidence = connection.execute(
                "SELECT AVG(confidence_score) AS value FROM submissions"
            ).fetchone()["value"]
            high_confidence_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM submissions
                WHERE confidence_score >= 0.70
                """
            ).fetchone()["count"]

        attribution_counts = {
            "ai_generated": 0,
            "human_written": 0,
            "uncertain": 0,
        }
        attribution_counts.update(
            {row["attribution_result"]: row["count"] for row in attribution_rows}
        )
        content_type_counts = {
            row["content_type"]: row["count"]
            for row in content_type_rows
        }
        appeal_rate = appeal_count / total_submissions if total_submissions else 0.0
        verified_human_rate = certificate_count / total_submissions if total_submissions else 0.0

        return {
            "total_submissions": total_submissions,
            "detection_patterns": {
                "attribution_counts": attribution_counts,
                "content_type_counts": content_type_counts,
                "high_confidence_count": high_confidence_count,
            },
            "appeal_count": appeal_count,
            "appeal_rate": round(appeal_rate, 3),
            "certificate_count": certificate_count,
            "verified_human_rate": round(verified_human_rate, 3),
            "average_confidence_score": round(float(average_confidence or 0.0), 3),
        }

    def list_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, submission_id, created_at, payload_json
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        entries = []
        for row in rows:
            entries.append(
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "submission_id": row["submission_id"],
                    "content_id": row["submission_id"],
                    "created_at": row["created_at"],
                    "payload": json.loads(row["payload_json"]),
                }
            )
        return entries

    def _log_event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        submission_id: Optional[str],
        payload: dict,
        created_at: Optional[str] = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_log (event_type, submission_id, created_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                event_type,
                submission_id,
                created_at or utc_now(),
                json.dumps(payload),
            ),
        )

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )

    def _submission_from_row(self, row: sqlite3.Row) -> dict:
        source_payload_json = row["source_payload_json"] or "{}"
        return {
            "submission_id": row["id"],
            "content_id": row["id"],
            "creator_id": row["creator_id"],
            "content_type": row["content_type"],
            "content_hash": row["content_hash"],
            "content_preview": row["content_preview"],
            "source_payload": json.loads(source_payload_json),
            "status": row["status"],
            "attribution_result": row["attribution_result"],
            "attribution": row["attribution_result"],
            "ai_probability": row["ai_probability"],
            "confidence_score": row["confidence_score"],
            "confidence": row["confidence_score"],
            "transparency_label": row["transparency_label"],
            "label": row["transparency_label"],
            "signals": json.loads(row["signals_json"]),
            "appeal_filed": False,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _certificate_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "certificate_id": row["id"],
            "submission_id": row["submission_id"],
            "content_id": row["submission_id"],
            "creator_id": row["creator_id"],
            "verification_method": row["verification_method"],
            "evidence_summary": row["evidence_summary"],
            "status": row["status"],
            "display_label": row["display_label"],
            "created_at": row["created_at"],
        }
