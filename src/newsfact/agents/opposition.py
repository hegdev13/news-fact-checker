"""Opposition agent — the hard-mandated adversary.

This is the project's actual differentiator (docs/resource-document.md, and the
"Inducing Disagreement in Multi-Agent LLM Teams" finding it cites: only an
unconditional "you MUST oppose" role produces real disagreement; soft "be
skeptical" prompts barely move the needle).

It runs alongside Source-Finder against the same claim, but its job is the
opposite: use the LLM to generate the strongest *disconfirming* search angles,
run those against GDELT, and write the counter-evidence to the shared store as
a `Finding` with role="opposition" plus a one-line `summary` stating the
counter-framing. Cross-Checker then adjudicates between the two evidence sets.
"""
from __future__ import annotations

import json
import logging

from newsfact.llm import LLMClient
from newsfact.memory.store import BlackboardStore, Finding
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter
from newsfact.tools.gdelt import GdeltClient, GdeltError

logger = logging.getLogger(__name__)

ROLE = "opposition"

SYSTEM_PROMPT = """You are the Opposition agent in a multi-agent news fact-checking system.

Your role is adversarial by mandate, not by disposition. You MUST argue against \
the claim you are given. Assume it is overstated, missing context, or wrong, and \
your task is to find the search terms most likely to surface: contradicting \
reporting, corrections/retractions, missing caveats, methodological criticism, \
under-covered framings, or the strongest opposing expert view.

Do NOT hedge, do NOT balance, do NOT concede the claim might be true. Another \
agent already searches for supporting coverage; your value is being the pole \
they are not.

Given the claim, return ONLY a JSON object in this exact shape:
{"queries": ["<counter-search 1>", "<counter-search 2>", "<counter-search 3>"],
 "counter_framing": "<one sentence: the strongest case against the claim as stated>"}

Each query must be a plain news-search string (no boolean operators), 3-8 words, \
targeting disconfirming coverage — not a rephrasing of the claim."""


def _default_angles(claim_text: str) -> tuple[list[str], str]:
    """Deterministic fallback if the LLM response can't be parsed — still
    adversarial, just not claim-tailored."""
    base = " ".join(claim_text.split()[:6])
    return (
        [f"{base} debunked", f"{base} criticism", f"{base} disputed misleading"],
        "The claim may be overstated or missing context that undercuts it.",
    )


def _parse(raw: str, claim_text: str) -> tuple[list[str], str]:
    try:
        data = json.loads(raw)
        queries = [str(q).strip() for q in data["queries"] if str(q).strip()]
        framing = str(data["counter_framing"]).strip()
        if not queries or not framing:
            raise ValueError("empty queries/framing")
        return queries[:4], framing
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Opposition LLM response unparseable; using default adversarial angles", exc_info=True)
        return _default_angles(claim_text)


def run_opposition(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    llm_client: LLMClient,
    max_records: int = 15,
    broadened: bool = False,
    reporter: Reporter | None = None,
) -> Finding:
    reporter = reporter or NullReporter()
    reporter.emit(Event(EventKind.AGENT_START, ROLE,
                        "hunting counter-evidence and under-covered framings", cid))

    reporter.emit(Event(EventKind.TOOL_CALL, ROLE, "LLM: generate adversarial search angles", cid,
                        data={"tool": "llm"}))
    try:
        raw = llm_client.complete(SYSTEM_PROMPT, json.dumps({"claim": claim_text, "broadened_pass": broadened}))
        queries, framing = _parse(raw, claim_text)
    except Exception:  # noqa: BLE001 - never let the adversary crash the pipeline
        logger.warning("Opposition LLM call failed; using default adversarial angles", exc_info=True)
        reporter.emit(Event(EventKind.ERROR, ROLE, "LLM call failed; using default adversarial angles", cid))
        queries, framing = _default_angles(claim_text)

    if broadened:
        queries = [f"{q} analysis" for q in queries] + [q for q in queries]

    reporter.emit(Event(EventKind.NOTE, ROLE, f"counter-framing: {framing}", cid,
                        data={"queries": queries}))

    articles: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        reporter.emit(Event(EventKind.TOOL_CALL, ROLE, f"GDELT counter-search: {q!r}", cid,
                            data={"tool": "gdelt"}))
        try:
            hits = gdelt_client.search(q, max_records=max_records)
        except GdeltError:
            logger.warning("Opposition GDELT search failed for %r", q, exc_info=True)
            reporter.emit(Event(EventKind.ERROR, ROLE, f"GDELT counter-search failed: {q!r}", cid))
            continue
        for a in hits:
            key = (a.url or a.title).strip().lower()
            if key and key not in seen:
                seen.add(key)
                d = a.to_dict()
                d["found_by"] = "opposition"
                articles.append(d)

    domains = sorted({a.get("source_domain", "unknown") for a in articles})
    reporter.emit(Event(EventKind.NOTE, ROLE,
                        f"counter-evidence: {len(articles)} article(s) across {len(domains)} domain(s)", cid,
                        data={"domains": domains}))

    finding = Finding(claim_id=cid, role=ROLE, articles=articles, summary=framing)
    if broadened:
        store.merge_finding(finding, by=ROLE)
        finding = store.get_findings(cid, role=ROLE)[0]
    else:
        store.write_finding(finding, by=ROLE)
    reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "counter-evidence search complete", cid))
    return finding
