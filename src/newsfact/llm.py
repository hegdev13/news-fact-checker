"""Shared LLM client interface used by every agent that reasons (Opposition,
Cross-Checker, Writer).

Kept as a `Protocol` so tests and the `--demo` mode can inject a fake without
the `anthropic` package, an API key, or the network. The one real
implementation is a thin wrapper over the Anthropic SDK.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicLLMClient:
    """Thin real implementation backed by the Anthropic SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 1024):
        import anthropic  # lazy: tests / demo mode never need the package installed

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if hasattr(block, "text"))
