"""Cross-Checker agent.

Reads Source-Finder's findings for a claim from the shared store, asks
Claude to assess agreement/conflict across independent outlets, and writes a
confidence-scored verdict back to the shared store.

Verdict labels are deliberately restricted to corroborated/disputed/
unverifiable (see docs/ARCHITECTURE.md) — never a binary true/false, and
never "corroborated" off a single source.
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

from newsfact.memory.store import BlackboardStore, Verdict

logger = logging.getLogger(__name__)

VALID_LABELS = {"corroborated", "disputed", "unverifiable"}

SYSTEM_PROMPT = """You are the Cross-Checker agent in a news fact-checking pipeline.

You are given a claim and a list of news articles retrieved by another agent \
(Source-Finder) that ran an independent search for coverage of the claim.

Your job: assess whether independent outlets corroborate the claim, dispute \
it, or whether there isn't enough coverage to say either way.

Hard rules:
- NEVER label anything as flatly true or false. Use only these three labels:
  "corroborated" (multiple independent outlets report consistent facts),
  "disputed" (outlets report conflicting facts or framing),
  "unverifiable" (too few or too thin sources to judge either way).
- A SINGLE source, no matter how reputable, is never enough for "corroborated".
  Multiple *distinct* outlets/domains reporting the same core facts is required.
- If the article list is empty or has fewer than 2 distinct source domains,
  the label must be "unverifiable".
- confidence is a float from 0.0 to 1.0 reflecting your confidence in the
  label itself (not confidence that the claim is true).

Respond with ONLY a JSON object, no other text, in this exact shape:
{"label": "corroborated" | "disputed" | "unverifiable", "confidence": 0.0-1.0, "reasoning": "2-4 sentences"}
"""


class LLMClient(Protocol):
    """Minimal interface Cross-Checker needs from an LLM client.

    Kept as a Protocol (rather than importing anthropic.Anthropic directly
    everywhere) so tests can inject a fake without touching the network or
    requiring an API key.
    """

    def complete(self, system: str, user: str) -> str: ...


class AnthropicLLMClient:
    """Thin real implementation backed by the Anthropic SDK."""

    def __init__(self, api_key: str, model: str):
        import anthropic  # imported lazily so tests never need the package installed as a hard requirement

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if hasattr(block, "text"))


def _build_user_prompt(claim_text: str, articles: list[dict]) -> str:
    distinct_domains = sorted({a.get("source_domain", "unknown") for a in articles})
    payload = {
        "claim": claim_text,
        "distinct_source_domains": distinct_domains,
        "articles": articles,
    }
    return json.dumps(payload, indent=2)


def _parse_llm_response(raw: str) -> tuple[str, float, str]:
    try:
        data = json.loads(raw)
        label = str(data["label"]).strip().lower()
        confidence = float(data["confidence"])
        reasoning = str(data["reasoning"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Could not parse Cross-Checker LLM response: {raw!r}") from exc

    if label not in VALID_LABELS:
        raise ValueError(f"LLM returned an invalid label: {label!r}")
    confidence = max(0.0, min(1.0, confidence))
    return label, confidence, reasoning


def run_cross_checker(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    llm_client: LLMClient,
) -> Verdict:
    findings = store.get_findings(cid, role="source_finder")
    articles: list[dict] = findings[0].articles if findings else []

    distinct_domains = {a.get("source_domain", "unknown") for a in articles}
    if len(distinct_domains) < 2:
        # Short-circuit without an LLM call: not enough independent sources
        # to possibly be anything but unverifiable. Saves a call and removes
        # any chance of the model second-guessing this hard rule.
        verdict = Verdict(
            claim_id=cid,
            label="unverifiable",
            confidence=1.0 if not articles else 0.6,
            reasoning=(
                "No coverage found." if not articles else
                "Only one distinct source domain found; at least two independent "
                "outlets are required before a claim can be corroborated or disputed."
            ),
        )
        store.write_verdict(verdict)
        return verdict

    user_prompt = _build_user_prompt(claim_text, articles)
    raw = llm_client.complete(SYSTEM_PROMPT, user_prompt)

    try:
        label, confidence, reasoning = _parse_llm_response(raw)
    except ValueError:
        logger.warning("Cross-Checker LLM response unparseable for claim %s; falling back to unverifiable", cid, exc_info=True)
        label, confidence, reasoning = (
            "unverifiable",
            0.0,
            "Cross-Checker could not interpret the model's response; treated as unverifiable pending retry.",
        )

    verdict = Verdict(claim_id=cid, label=label, confidence=confidence, reasoning=reasoning)
    store.write_verdict(verdict)
    return verdict
