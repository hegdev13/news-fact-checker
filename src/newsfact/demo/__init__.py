"""Offline fixtures so the full 5-agent pipeline and the live terminal
dashboard can run with no API keys and no network — `python -m newsfact.main
--demo`. Swapped out for the real GDELT / Anthropic clients the moment
`ANTHROPIC_API_KEY` is set.
"""
from newsfact.demo.fixtures import FakeGdeltClient, FakeLLMClient

__all__ = ["FakeGdeltClient", "FakeLLMClient"]
