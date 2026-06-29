LABEL_VARIANTS = {
    "likely_ai": (
        "Provenance Guard: This piece appears likely to be AI-generated. "
        "Multiple review signals point in that direction with high confidence. "
        "The creator can appeal this label."
    ),
    "likely_human": (
        "Provenance Guard: This piece appears likely to be human-written. "
        "The review found limited AI-generation signals, but this is not a guarantee."
    ),
    "uncertain": (
        "Provenance Guard: We cannot confidently determine how this piece was created. "
        "Readers should treat the attribution as uncertain, and the creator can provide more context."
    ),
}


def choose_label(ai_probability: float, confidence_score: float) -> tuple[str, str, str]:
    if ai_probability >= 0.72 and confidence_score >= 0.70:
        return "likely_ai", "ai_generated", LABEL_VARIANTS["likely_ai"]

    if ai_probability <= 0.28 and confidence_score >= 0.70:
        return "likely_human", "human_written", LABEL_VARIANTS["likely_human"]

    return "uncertain", "uncertain", LABEL_VARIANTS["uncertain"]

