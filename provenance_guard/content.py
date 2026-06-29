import json
from dataclasses import dataclass
from typing import Any, Optional


SUPPORTED_CONTENT_TYPES = {"text", "image_description", "metadata"}


@dataclass
class NormalizedSubmission:
    content_type: str
    analysis_text: str
    source_payload: dict[str, Any]


def normalize_submission_payload(payload: dict) -> tuple[Optional[NormalizedSubmission], Optional[dict]]:
    raw_content_type = (payload.get("content_type") or "text").strip().lower()
    content_type = {
        "image": "image_description",
        "structured_metadata": "metadata",
    }.get(raw_content_type, raw_content_type)

    if content_type not in SUPPORTED_CONTENT_TYPES:
        return None, {
            "error": "unsupported_content_type",
            "message": "Supported content types are text, image_description, and metadata.",
        }

    if content_type == "text":
        content = (payload.get("content") or payload.get("text") or "").strip()
        return NormalizedSubmission(
            content_type="text",
            analysis_text=content,
            source_payload={
                "input_field": "content" if payload.get("content") else "text",
                "content_length": len(content),
            },
        ), None

    if content_type == "image_description":
        description = (
            payload.get("image_description")
            or payload.get("description")
            or payload.get("content")
            or ""
        ).strip()
        alt_text = (payload.get("alt_text") or "").strip()
        analysis_text = "Image description submission. Description: " + description
        if alt_text:
            analysis_text += f" Alt text: {alt_text}"
        return NormalizedSubmission(
            content_type="image_description",
            analysis_text=analysis_text,
            source_payload={
                "image_description": description,
                "alt_text": alt_text,
            },
        ), None

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None, {
            "error": "invalid_metadata",
            "message": "Metadata submissions require a metadata object.",
        }

    metadata_text = metadata_to_text(metadata)
    return NormalizedSubmission(
        content_type="metadata",
        analysis_text=f"Structured metadata submission. {metadata_text}",
        source_payload={"metadata": metadata},
    ), None


def metadata_to_text(metadata: dict[str, Any]) -> str:
    parts = []
    for key in sorted(metadata):
        value = metadata[key]
        if value is None or value == "":
            continue
        label = str(key).replace("_", " ").strip().title()
        parts.append(f"{label}: {stringify_metadata_value(value)}")
    return " ".join(parts)


def stringify_metadata_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(stringify_metadata_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)
