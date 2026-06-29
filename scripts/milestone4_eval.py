import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provenance_guard.detectors import classify_content


SAMPLES = {
    "template_ai": (
        "This essay highlights the transformative power of artificial intelligence. "
        "This essay highlights the transformative power of artificial intelligence. "
        "This essay highlights the transformative power of artificial intelligence. "
        "It is important to note that responsible innovation matters. "
        "It is important to note that responsible innovation matters. "
        "In conclusion, artificial intelligence is a transformative paradigm shift."
    ),
    "casual_human": (
        "ok so i finally tried that new ramen place downtown and honestly? "
        "underwhelming. the broth was fine but they put WAY too much sodium in it "
        "and i was thirsty for like three hours after. my friend got the spicy "
        "version and said it was better. probably won't go back unless someone "
        "drags me there"
    ),
    "borderline_formulaic": (
        "In today's rapidly evolving landscape, artificial intelligence represents "
        "a transformative paradigm shift. In today's rapidly evolving landscape, "
        "artificial intelligence represents a transformative paradigm shift. "
        "It is important to note that the benefits are numerous. Furthermore, "
        "stakeholders across various sectors must collaborate. In conclusion, "
        "this essay demonstrates responsible deployment."
    ),
    "borderline_mixed_human": (
        "I've been thinking about remote work lately. The flexibility is real, "
        "and the lack of commute changes the whole day. At the same time, it is "
        "important to note that isolation can creep in quietly. Overall, the "
        "tradeoff depends on the person, the job, and the team."
    ),
}


def summarize(name: str, text: str) -> dict:
    result = classify_content(text, groq_api_key="")
    signal_scores = {
        signal["name"]: {
            "ai_probability": signal["ai_probability"],
            "available": signal["available"],
        }
        for signal in result["signals"]
    }
    return {
        "sample": name,
        "ai_probability": result["ai_probability"],
        "confidence_score": result["confidence_score"],
        "attribution_result": result["attribution_result"],
        "signal_scores": signal_scores,
    }


def main() -> None:
    for name, text in SAMPLES.items():
        print(summarize(name, text))


if __name__ == "__main__":
    main()
