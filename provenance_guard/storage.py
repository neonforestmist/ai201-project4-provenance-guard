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
                    content_hash TEXT NOT NULL,
                    content_preview TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    submission_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def create_submission(self, content: str, creator_id: Optional[str], decision: dict) -> dict:
        submission_id = str(uuid.uuid4())
        created_at = utc_now()
        content_preview = content.strip().replace("\n", " ")[:180]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        payload = {
            "submission_id": submission_id,
            "content_id": submission_id,
            "creator_id": creator_id,
            "status": "classified",
            "content_hash": content_hash,
            "content_preview": content_preview,
            **decision,
            "attribution": decision["attribution_result"],
            "confidence": decision["confidence_score"],
            "label": decision["transparency_label"],
            "appeal_filed": False,
            "created_at": created_at,
        }

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO submissions (
                    id, creator_id, content_hash, content_preview, status,
                    attribution_result, ai_probability, confidence_score,
                    transparency_label, signals_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    creator_id,
                    content_hash,
                    content_preview,
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
        if not row:
            return None
        submission = self._submission_from_row(row)
        submission["appeal_filed"] = bool(appeal_exists)
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

    def _submission_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "submission_id": row["id"],
            "content_id": row["id"],
            "creator_id": row["creator_id"],
            "content_hash": row["content_hash"],
            "content_preview": row["content_preview"],
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
