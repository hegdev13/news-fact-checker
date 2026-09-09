"""Central configuration, loaded from environment variables / .env.

Keeping this in one module means no other file reaches into os.environ
directly, which makes it obvious where to look when wiring in real
credentials for the first time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    model: str
    gdelt_api_base: str
    db_path: str


def load_settings() -> Settings:
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=os.getenv("NEWSFACT_MODEL", "claude-sonnet-4-5"),
        gdelt_api_base=os.getenv(
            "GDELT_API_BASE", "https://api.gdeltproject.org/api/v2/doc/doc"
        ),
        db_path=os.getenv("NEWSFACT_DB_PATH", "data/newsfact.db"),
    )
