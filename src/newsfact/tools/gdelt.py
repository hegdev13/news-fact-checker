"""Client for the GDELT DOC 2.0 API.

No API key required. Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

We ask for JSON with the "artlist" mode, which returns per-article metadata
including a `tone` field GDELT computes — used here as a cheap sentiment
proxy, per the resource document's suggestion (not a substitute for a real
outlet bias rating).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Article:
    title: str
    url: str
    source_domain: str
    seen_date: str
    tone: float | None = None
    language: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source_domain": self.source_domain,
            "seen_date": self.seen_date,
            "tone": self.tone,
            "language": self.language,
        }


class GdeltError(RuntimeError):
    pass


class GdeltClient:
    def __init__(self, api_base: str, timeout: float = 15.0):
        self.api_base = api_base
        self.timeout = timeout

    def search(self, query: str, max_records: int = 25) -> list[Article]:
        """Search GDELT for articles matching `query`.

        Raises GdeltError on network failure or an unparseable response —
        callers should decide whether that means "no coverage" (it does not)
        or "retry later" (it does).
        """
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(max_records),
            "sort": "hybridrel",
        }
        try:
            resp = httpx.get(self.api_base, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise GdeltError(f"GDELT request failed: {exc}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise GdeltError(f"GDELT returned non-JSON response: {exc}") from exc

        return self._parse_response(data)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> list[Article]:
        articles_raw = data.get("articles", [])
        articles: list[Article] = []
        for a in articles_raw:
            try:
                articles.append(
                    Article(
                        title=a.get("title", "").strip(),
                        url=a.get("url", ""),
                        source_domain=a.get("domain", "unknown"),
                        seen_date=a.get("seendate", ""),
                        tone=_safe_float(a.get("tone")),
                        language=a.get("language"),
                    )
                )
            except Exception:
                # Skip malformed entries rather than failing the whole batch.
                continue
        return articles


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
