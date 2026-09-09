"""Deterministic offline stand-ins for the GDELT and Anthropic clients.

These are intentionally scripted, not "smart": they recognise a few keywords
from the bundled sample claims (src/newsfact/resources/sample_claims.txt) so the
demo shows all three verdict paths — corroborated, disputed (with the
deep-research loop firing), and unverifiable (short-circuit) — and fall back to
a generic multi-outlet result for anything else. No network, no API key.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from newsfact.tools.gdelt import Article


def _a(title: str, domain: str, tone: float) -> Article:
    slug = hashlib.sha1(f"{domain}{title}".encode()).hexdigest()[:10]
    return Article(
        title=title,
        url=f"https://{domain}/{slug}",
        source_domain=domain,
        seen_date="20260908T120000Z",
        tone=tone,
        language="English",
    )


# --- scripted evidence pools ------------------------------------------------

_CORROBORATED_COVERAGE = [
    _a("India GDP grows 7.8% in the quarter, fastest among major economies", "reuters.com", 2.1),
    _a("Indian economy expands 7.8%, beating forecasts", "apnews.com", 1.8),
    _a("GDP data: India retains fastest-growing major economy tag at 7.8%", "thehindu.com", 3.0),
    _a("India Q1 GDP growth at 7.8%, government hails resilience", "livemint.com", 2.6),
    _a("India grows 7.8%, outpacing China and the US", "timesofindia.indiatimes.com", 3.4),
    _a("India's 7.8% growth: strong services, farm sector rebound", "business-standard.com", 1.2),
    _a("India economy grew 7.8% last quarter, official data shows", "bbc.com", 0.9),
    _a("India posts 7.8% growth as global economies slow", "wsj.com", 0.4),
]
_CORROBORATED_COUNTER = [
    _a("Economists question India's 7.8% GDP: deflator and base effects flattered the number", "wsj.com", -1.6),
    _a("Is India's 7.8% growth as strong as it looks? Private investment still weak", "livemint.com", -0.8),
]

_DISPUTED_COVERAGE = [
    _a("One cup of coffee a day may reverse cognitive decline in older adults, study finds", "theguardian.com", 3.1),
    _a("Daily coffee linked to sharp memory gains in over-60s, researchers say", "nytimes.com", 2.7),
    _a("Coffee reverses ageing of the brain, new research claims", "timesofindia.indiatimes.com", 3.6),
    _a("Study: a single coffee restores cognitive function in older people", "ndtv.com", 2.9),
]
_DISPUTED_COUNTER = [
    _a("Experts cast doubt on coffee-and-memory study: small sample, no control group", "apnews.com", -2.4),
    _a("No, one coffee a day won't reverse cognitive decline — what the study actually showed", "bbc.com", -1.9),
    _a("Nutrition scientists say coffee cognition claim is overstated and unreplicated", "reuters.com", -2.1),
    _a("The coffee 'brain reversal' headlines outran a preliminary, industry-funded study", "wsj.com", -1.7),
]
_DISPUTED_COVERAGE_BROADENED = [
    _a("Coffee and cognition: what a week of headlines got wrong", "npr.org", -0.6),
    _a("Follow-up: authors of coffee study walk back 'reverses decline' framing", "theguardian.com", -0.4),
]

_UNVERIFIABLE_COVERAGE = [
    _a("Rumours swirl of weekend emergency rate cut; central bank has not commented", "timesofindia.indiatimes.com", -0.5),
]


def _pick(query: str) -> tuple[str, str]:
    q = query.lower()
    if "coffee" in q or "cognitive" in q:
        return "disputed", q
    if "rate cut" in q or ("central bank" in q and "emergency" in q) or "emergency interest rate" in q:
        return "unverifiable", q
    if "7.8%" in q or ("india" in q and "econom" in q):
        return "corroborated", q
    return "generic", q


class FakeGdeltClient:
    """Scripted GDELT. Coverage vs counter-search is inferred from the query
    text the way the real outlets would differ: neutral claim text vs the
    Opposition agent's 'debunked / criticism / disputed' phrasings."""

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def search(self, query: str, max_records: int = 25) -> list[Article]:
        scenario, q = _pick(query)
        counterish = any(w in q for w in ("debunk", "criticism", "disputed", "misleading",
                                          "overstated", "skeptic", "no evidence", "analysis", "walk back"))
        broadened = any(w in q for w in ("latest update report", "analysis"))

        if scenario == "corroborated":
            pool = _CORROBORATED_COUNTER if counterish else _CORROBORATED_COVERAGE
        elif scenario == "disputed":
            if counterish:
                pool = _DISPUTED_COUNTER + (_DISPUTED_COVERAGE_BROADENED if broadened else [])
            else:
                pool = _DISPUTED_COVERAGE + (_DISPUTED_COVERAGE_BROADENED if broadened else [])
        elif scenario == "unverifiable":
            pool = [] if counterish else _UNVERIFIABLE_COVERAGE
        else:  # generic
            pool = _CORROBORATED_COUNTER if counterish else [
                _a(f"Report: {query[:60]}", "reuters.com", 0.5),
                _a(f"Analysis: {query[:60]}", "bbc.com", 0.2),
                _a(f"Opinion: {query[:60]}", "thehindu.com", 1.1),
                _a(f"Coverage: {query[:60]}", "foxnews.com", -0.8),
            ]
        return pool[:max_records]


# --- scripted LLM --------------------------------------------------------------

_CROSS_CHECK_SCRIPT: dict[str, list[dict]] = {}


class FakeLLMClient:
    """Scripted Claude. Branches on which agent's system prompt it was handed."""

    def __init__(self, *_: Any, **__: Any) -> None:
        self._calls: dict[str, int] = {}

    # -- helpers
    @staticmethod
    def _claim_of(user: str) -> str:
        try:
            return str(json.loads(user).get("claim", user))
        except Exception:  # noqa: BLE001
            return user

    def complete(self, system: str, user: str) -> str:
        if "Claim Extractor agent" in system:
            return self._claim_extractor(user)
        if "Opposition agent" in system:
            return self._opposition(user)
        if "Cross-Checker agent" in system:
            return self._cross_checker(user)
        if "Writer agent" in system:
            return self._writer(user)
        return json.dumps({"note": "unrecognised agent prompt"})

    def _claim_extractor(self, user: str) -> str:
        """`user` is the raw article text here, not JSON."""
        t = user.lower()
        if "7.8%" in t or ("india" in t and "econom" in t):
            return json.dumps({
                "primary_claim": "India's economy grew 7.8% in the most recent quarter, the fastest among major economies.",
                "secondary_claims": [
                    "The growth was driven by services and a farm-sector rebound.",
                    "India's growth outpaced China's in the same quarter.",
                ],
                "article_summary": "An article reporting India's latest quarterly GDP growth figure and its ranking among major economies.",
            })
        if "coffee" in t or "cognitive" in t:
            return json.dumps({
                "primary_claim": "A new study claims a single cup of coffee per day reverses cognitive decline in adults over 60.",
                "secondary_claims": ["The effect was measured after a short trial period."],
                "article_summary": "An article summarising a study that links daily coffee to recovered cognitive function in older adults.",
            })
        # generic: first substantial line that looks like a sentence, not metadata
        for line in user.splitlines():
            line = line.strip()
            if len(line) >= 25 and not line.lower().startswith(("http", "by ", "source:", "source :", "photo", "image")):
                return json.dumps({"primary_claim": line[:200], "secondary_claims": [], "article_summary": line[:200]})
        return json.dumps({"primary_claim": user.strip()[:200] or "(empty article)", "secondary_claims": [], "article_summary": ""})

    # -- per-agent scripts
    def _opposition(self, user: str) -> str:
        claim = self._claim_of(user).lower()
        if "coffee" in claim or "cognitive" in claim:
            return json.dumps({
                "queries": [
                    "coffee cognitive decline study debunked",
                    "coffee memory claim overstated criticism",
                    "coffee brain study small sample no control",
                ],
                "counter_framing": "The 'reverses cognitive decline' claim rests on a small, "
                                   "short, industry-funded study with no control group and no replication.",
            })
        if "7.8%" in claim or "econom" in claim:
            return json.dumps({
                "queries": [
                    "India GDP 7.8% deflator base effect criticism",
                    "India growth private investment weak disputed",
                    "India GDP figure overstated economists",
                ],
                "counter_framing": "The 7.8% headline may be flattered by a low deflator and base effects; "
                                   "private investment and consumption remain soft.",
            })
        return json.dumps({
            "queries": [f"{claim[:40]} debunked", f"{claim[:40]} criticism", f"{claim[:40]} disputed misleading"],
            "counter_framing": "The claim may be overstated or missing context that undercuts it.",
        })

    def _cross_checker(self, user: str) -> str:
        try:
            payload = json.loads(user)
        except Exception:  # noqa: BLE001
            payload = {}
        claim = str(payload.get("claim", "")).lower()
        domains = payload.get("distinct_source_domains", [])
        key = hashlib.sha1(claim.encode()).hexdigest()[:12]
        self._calls[key] = self._calls.get(key, 0) + 1
        n = self._calls[key]

        if "coffee" in claim or "cognitive" in claim:
            if n == 1:
                return json.dumps({
                    "label": "disputed", "confidence": 0.48,
                    "reasoning": "The coverage search and the adversarial search point in opposite directions: "
                                 "several outlets report the 'reverses decline' framing while wire services and "
                                 "science desks call the study small, uncontrolled and unreplicated. Confidence is "
                                 "low; more corroborating or refuting reporting would help.",
                })
            return json.dumps({
                "label": "disputed", "confidence": 0.71,
                "reasoning": "A second evidence pass confirms the split: the strong causal claim is carried mainly "
                             "by first-wave headlines, while follow-up reporting shows the authors themselves walking "
                             "back the framing. Independent outlets disagree on what the study supports.",
            })
        if "7.8%" in claim or "econom" in claim:
            return json.dumps({
                "label": "corroborated", "confidence": 0.86,
                "reasoning": "Multiple independent outlets across the spectrum (Reuters, AP, BBC, The Hindu, WSJ) "
                             "report the same 7.8% figure and the 'fastest major economy' characterisation. The "
                             "adversarial search only surfaces interpretation caveats, not a factual contradiction.",
            })
        if len(domains) >= 2:
            return json.dumps({
                "label": "corroborated", "confidence": 0.74,
                "reasoning": "Several distinct outlets report consistent core facts and the adversarial search did "
                             "not surface substantive contradiction.",
            })
        return json.dumps({
            "label": "unverifiable", "confidence": 0.5,
            "reasoning": "Coverage across both evidence sets is too thin to adjudicate.",
        })

    def _writer(self, user: str) -> str:
        try:
            p = json.loads(user)
        except Exception:  # noqa: BLE001
            p = {}
        claim = str(p.get("claim", "the claim"))
        v = p.get("verdict") or {}
        label = v.get("label", "unverifiable")
        conf = v.get("confidence", 0.0)
        bias = p.get("bias") or {}
        spread = bias.get("spread", {"left": 0, "center": 0, "right": 0, "unknown": 0})
        blind = bias.get("blindspots", []) or ["not assessed"]
        opp = p.get("opposition") or {}
        counter = opp.get("counter_framing") or "No specific counter-framing was produced."
        sf_n = (p.get("source_finder") or {}).get("count", 0)
        opp_n = opp.get("count", 0)

        headline = {
            "corroborated": f"Independent outlets corroborate: {claim[:70]}",
            "disputed": f"Outlets disagree on: {claim[:74]}",
            "unverifiable": f"Not enough coverage to verify: {claim[:64]}",
        }.get(label, claim[:80])

        body = (
            f"**Verdict**\n"
            f"This claim is **{label}** (confidence {conf:.0%} in the label, not in the claim being true). "
            f"{v.get('reasoning', '')}\n\n"
            f"**What the coverage shows**\n"
            f"Source-Finder retrieved {sf_n} article(s) of coverage; the Opposition agent retrieved "
            f"{opp_n} counter-article(s). "
            + ("The two sets broadly agree on the core facts.\n\n" if label == "corroborated"
               else "The two sets pull in different directions on what is established.\n\n" if label == "disputed"
               else "Neither set produced enough independent reporting to judge.\n\n")
            + f"**The opposing case**\n{counter}\n\n"
            f"**Bias & blindspots**\n"
            f"Retrieved-outlet spread is L/C/R = {spread.get('left', 0)}/{spread.get('center', 0)}/"
            f"{spread.get('right', 0)} (+{spread.get('unknown', 0)} unrated), dominant side "
            f"'{bias.get('dominant_side', 'n/a')}'. " + " ".join(blind)
        )
        return json.dumps({"headline": headline, "body_md": body})
