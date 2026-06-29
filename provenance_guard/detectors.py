import json
import math
import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable, Optional

from groq import Groq

from provenance_guard.labels import choose_label


WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")


@dataclass
class SignalResult:
    name: str
    ai_probability: float
    confidence: float
    available: bool
    rationale: str
    details: dict

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ai_probability"] = round(self.ai_probability, 3)
        data["confidence"] = round(self.confidence, 3)
        return data


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def words(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(text)]


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_RE.findall(text) if part.strip()]


def safe_stdev(values: Iterable[float]) -> float:
    values = list(values)
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def stylometric_signal(text: str) -> SignalResult:
    token_list = words(text)
    sentence_list = sentences(text)
    word_count = max(len(token_list), 1)
    sentence_lengths = [
        max(len(words(sentence)), 1)
        for sentence in sentence_list
    ] or [word_count]

    type_token_ratio = len(set(token_list)) / word_count
    avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths)
    sentence_length_stdev = safe_stdev(sentence_lengths)
    punctuation_density = sum(1 for char in text if char in ",;:!?") / word_count

    uniform_sentence_score = clamp((8.0 - sentence_length_stdev) / 8.0)
    low_variety_score = clamp((0.62 - type_token_ratio) / 0.32)
    polished_length_score = clamp((avg_sentence_length - 12.0) / 18.0)
    restrained_punctuation_score = clamp((0.18 - punctuation_density) / 0.18)

    ai_probability = (
        0.34 * uniform_sentence_score
        + 0.30 * low_variety_score
        + 0.22 * polished_length_score
        + 0.14 * restrained_punctuation_score
    )
    confidence = clamp(0.45 + abs(ai_probability - 0.5))

    return SignalResult(
        name="stylometric_heuristics",
        ai_probability=ai_probability,
        confidence=confidence,
        available=True,
        rationale=(
            "Measures structural regularity: sentence-length variance, "
            "vocabulary diversity, length, and punctuation density."
        ),
        details={
            "word_count": word_count,
            "sentence_count": len(sentence_list),
            "type_token_ratio": round(type_token_ratio, 3),
            "avg_sentence_length": round(avg_sentence_length, 2),
            "sentence_length_stdev": round(sentence_length_stdev, 2),
            "punctuation_density": round(punctuation_density, 3),
        },
    )


def formulaic_pattern_signal(text: str) -> SignalResult:
    token_list = words(text)
    word_count = max(len(token_list), 1)
    bigrams = list(zip(token_list, token_list[1:]))
    unique_bigrams = len(set(bigrams)) or 1
    repeated_bigram_ratio = 1 - (unique_bigrams / max(len(bigrams), 1))

    lower_text = text.lower()
    formulaic_markers = [
        "it is important to note",
        "in conclusion",
        "overall",
        "moreover",
        "furthermore",
        "as a result",
        "in today's",
        "this essay",
    ]
    marker_hits = sum(1 for marker in formulaic_markers if marker in lower_text)
    marker_density = marker_hits / word_count

    repeated_openers = 0
    openers = []
    for sentence in sentences(text):
        sentence_words = words(sentence)
        if sentence_words:
            openers.append(sentence_words[0])
    if openers:
        repeated_openers = len(openers) - len(set(openers))

    repetition_score = clamp(repeated_bigram_ratio * 6)
    marker_score = clamp(marker_density * 80)
    opener_score = clamp(repeated_openers / max(len(openers), 1))
    ai_probability = 0.45 * repetition_score + 0.40 * marker_score + 0.15 * opener_score
    confidence = clamp(0.42 + abs(ai_probability - 0.5))

    return SignalResult(
        name="formulaic_pattern_scan",
        ai_probability=ai_probability,
        confidence=confidence,
        available=True,
        rationale=(
            "Looks for template-like wording, repeated phrasing, and repeated sentence openings."
        ),
        details={
            "repeated_bigram_ratio": round(repeated_bigram_ratio, 3),
            "formulaic_marker_hits": marker_hits,
            "repeated_sentence_openers": repeated_openers,
        },
    )


def parse_groq_json(raw_text: str) -> dict:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def groq_signal(text: str, api_key: Optional[str] = None, model: Optional[str] = None) -> SignalResult:
    api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY", "")
    model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if not api_key:
        return SignalResult(
            name="groq_llm_classification",
            ai_probability=0.5,
            confidence=0.0,
            available=False,
            rationale="Skipped because GROQ_API_KEY is not configured.",
            details={"model": model},
        )

    prompt = (
        "You are a cautious provenance reviewer for a creative writing platform. "
        "Estimate whether the submitted text was AI-generated. Return only JSON with keys "
        "ai_probability (number from 0 to 1), confidence (number from 0 to 1), and rationale "
        "(one short sentence). Be conservative: false positives against human creators are costly.\n\n"
        f"Submitted text:\n{text[:6000]}"
    )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "Return strict JSON and avoid overclaiming.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        parsed = parse_groq_json(raw)
        ai_probability = clamp(float(parsed.get("ai_probability", 0.5)))
        confidence = clamp(float(parsed.get("confidence", 0.5)))
        rationale = str(parsed.get("rationale", "Groq classification completed."))
        return SignalResult(
            name="groq_llm_classification",
            ai_probability=ai_probability,
            confidence=confidence,
            available=True,
            rationale=rationale,
            details={"model": model},
        )
    except Exception as exc:
        return SignalResult(
            name="groq_llm_classification",
            ai_probability=0.5,
            confidence=0.0,
            available=False,
            rationale=f"Groq classification failed: {exc.__class__.__name__}",
            details={"model": model},
        )


def combine_signals(signal_results: list[SignalResult]) -> dict:
    base_weights = {
        "groq_llm_classification": 0.55,
        "stylometric_heuristics": 0.30,
        "formulaic_pattern_scan": 0.15,
    }
    available = [signal for signal in signal_results if signal.available]
    if not available:
        ai_probability = 0.5
        agreement = 0.0
    else:
        total_weight = sum(base_weights.get(signal.name, 0.1) for signal in available)
        ai_probability = sum(
            signal.ai_probability * base_weights.get(signal.name, 0.1)
            for signal in available
        ) / total_weight
        max_gap = max(
            abs(left.ai_probability - right.ai_probability)
            for left in available
            for right in available
        ) if len(available) > 1 else 0.35
        agreement = clamp(1 - max_gap)

    distance_from_uncertain = abs(ai_probability - 0.5) * 2
    confidence_score = clamp(0.45 + 0.45 * distance_from_uncertain + 0.10 * agreement, 0.0, 0.98)
    label_key, attribution_result, label_text = choose_label(ai_probability, confidence_score)

    return {
        "attribution_result": attribution_result,
        "label_key": label_key,
        "ai_probability": round(ai_probability, 3),
        "confidence_score": round(confidence_score, 3),
        "transparency_label": label_text,
        "signals": [signal.to_dict() for signal in signal_results],
        "signal_agreement": round(agreement, 3),
    }


def classify_content(text: str, groq_api_key: Optional[str] = None, groq_model: Optional[str] = None) -> dict:
    signal_results = [
        groq_signal(text, api_key=groq_api_key, model=groq_model),
        stylometric_signal(text),
        formulaic_pattern_signal(text),
    ]
    return combine_signals(signal_results)
