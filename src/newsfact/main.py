"""CLI entrypoint.

Usage:
    python -m newsfact.main "Some claim or headline to check"

Checks the shared store for an existing verdict on this claim first (the
"don't re-investigate a checked claim" cache from the resource document)
before running the Source-Finder -> Cross-Checker graph.
"""
from __future__ import annotations

import json
import sys

from newsfact.agents.cross_checker import AnthropicLLMClient
from newsfact.config import load_settings
from newsfact.graph import run_pipeline
from newsfact.memory.store import BlackboardStore, claim_id
from newsfact.tools.gdelt import GdeltClient


def cli() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m newsfact.main "<claim to check>"', file=sys.stderr)
        raise SystemExit(1)

    claim_text = " ".join(sys.argv[1:])
    settings = load_settings()
    store = BlackboardStore(settings.db_path)

    cid = claim_id(claim_text)
    cached = store.get_verdict(cid)
    if cached is not None:
        print(json.dumps({"claim": claim_text, "cached": True, **_verdict_to_dict(cached)}, indent=2))
        return

    if not settings.anthropic_api_key:
        print(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and set it, "
            "or export it directly. Cross-Checker cannot run without it.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    gdelt_client = GdeltClient(settings.gdelt_api_base)
    llm_client = AnthropicLLMClient(settings.anthropic_api_key, settings.model)

    result = run_pipeline(claim_text, store, gdelt_client, llm_client)
    print(
        json.dumps(
            {
                "claim": claim_text,
                "cached": False,
                "label": result.get("verdict_label"),
                "confidence": result.get("verdict_confidence"),
                "reasoning": result.get("verdict_reasoning"),
            },
            indent=2,
        )
    )


def _verdict_to_dict(verdict) -> dict:
    return {
        "label": verdict.label,
        "confidence": verdict.confidence,
        "reasoning": verdict.reasoning,
    }


if __name__ == "__main__":
    cli()
