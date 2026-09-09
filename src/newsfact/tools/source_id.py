"""Identify which outlet published a submitted article — "find the source".

Pure / offline. Tries, in order:
  1. an explicit URL passed alongside the article,
  2. the first http(s) URL in the article text,
  3. a byline / dateline / "(Reuters)"-style credit that matches a known outlet
     name from the bias table.

Returns an `OriginGuess`; `method="none"` means we couldn't tell. No network —
a URL is parsed for its domain, never fetched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from newsfact.tools.bias_table import BiasTable, OutletRating

_URL_RE = re.compile(r"https?://[^\s\)\]\">]+", re.IGNORECASE)
# "By Jane Doe", "By Jane Doe and John Roe". Inter-word separator is spaces/tabs
# only (never a newline) so the capture stops at the end of the byline line.
_NAME = r"[A-Z][A-Za-z.'-]+"
_BYLINE_RE = re.compile(
    rf"\bBy[ \t]+({_NAME}(?:[ \t]+{_NAME}){{0,3}}(?:[ \t]+and[ \t]+{_NAME}(?:[ \t]+{_NAME}){{0,2}})?)"
)
# "(Reuters)", "— AP", "| The Hindu"
_CREDIT_RE = re.compile(r"[\(\-—\|]\s*([A-Z][A-Za-z .&/']{2,40}?)\s*[\)\-—\|\n]")


@dataclass(frozen=True)
class OriginGuess:
    domain: str
    rating: OutletRating
    method: str          # "url" | "byline" | "none"
    byline: str = ""

    @property
    def identified(self) -> bool:
        return self.method != "none"


def _domain_of(url: str) -> str:
    netloc = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _match_named_outlet(text: str, table: BiasTable) -> OutletRating | None:
    """Look for any known outlet's display name appearing in the text."""
    head = text[:1200]
    lowered = head.lower()
    best: OutletRating | None = None
    for domain, row in table.items():
        name = str(row.get("name", "")).lower()
        if len(name) >= 4 and name in lowered:
            rating = table.lookup(domain)
            # prefer the longest name match (more specific)
            if best is None or len(rating.name) > len(best.name):
                best = rating
    return best


def identify_source(text: str, url: str | None, bias_table: BiasTable) -> OriginGuess:
    text = text or ""

    # 1 / 2: explicit URL, then first URL in the body
    candidate_url = (url or "").strip() or None
    if candidate_url is None:
        m = _URL_RE.search(text)
        candidate_url = m.group(0) if m else None

    byline = ""
    bm = _BYLINE_RE.search(text[:1500])
    if bm:
        byline = bm.group(1).strip()

    if candidate_url:
        domain = _domain_of(candidate_url)
        if domain:
            return OriginGuess(domain=domain, rating=bias_table.lookup(domain), method="url", byline=byline)

    # 3: named-outlet / credit match
    named = _match_named_outlet(text, bias_table)
    if named is None:
        cm = _CREDIT_RE.search(text[:1200])
        if cm:
            named = _match_named_outlet(cm.group(1), bias_table)
    if named is not None:
        return OriginGuess(domain=named.domain, rating=named, method="byline", byline=byline)

    unknown = bias_table.lookup("unknown")
    return OriginGuess(domain="unknown", rating=unknown, method="none", byline=byline)
