import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/provenance_guard.sqlite3"))
    SUBMISSION_RATE_LIMIT = os.getenv(
        "SUBMISSION_RATE_LIMIT",
        "12 per minute; 100 per day",
    )
    JSON_SORT_KEYS = False

