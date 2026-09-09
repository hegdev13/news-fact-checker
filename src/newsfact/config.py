"""Central configuration, loaded from environment variables / .env.

Keeping this in one module means no other file reaches into os.environ
directly, which makes it obvious where to look when wiring in real
credentials for the first time.

Supported LLM providers (NEWSFACT_LLM_PROVIDER):
  anthropic   — Anthropic API (default). Requires ANTHROPIC_API_KEY.
  nvidia      — NVIDIA NIM OpenAI-compatible endpoint. Requires NVIDIA_API_KEY.
                Compatible with Mistral models (e.g. mistralai/mistral-large-2-instruct).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    nvidia_api_key: str | None
    llm_provider: str           # "anthropic" | "nvidia"
    model: str
    gdelt_api_base: str
    db_path: str
    bias_table_path: str | None


_PROVIDER_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
    "nvidia": "mistralai/mistral-large-2-instruct",
}


def load_settings() -> Settings:
    provider = os.getenv("NEWSFACT_LLM_PROVIDER", "anthropic").lower()
    default_model = _PROVIDER_DEFAULTS.get(provider, "claude-sonnet-4-5")
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        nvidia_api_key=os.getenv("NVIDIA_API_KEY"),
        llm_provider=provider,
        model=os.getenv("NEWSFACT_MODEL", default_model),
        gdelt_api_base=os.getenv(
            "GDELT_API_BASE", "https://api.gdeltproject.org/api/v2/doc/doc"
        ),
        db_path=os.getenv("NEWSFACT_DB_PATH", "data/newsfact.db"),
        # None -> Bias/Blindspot Analyzer loads the bundled table in
        # newsfact/resources/outlet_bias.json. Override with a path to your own.
        bias_table_path=os.getenv("NEWSFACT_BIAS_TABLE") or None,
    )
