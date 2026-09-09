"""Claim Extractor agent (v2.1 article-input mode).

Front-end for "here is an article, check it" instead of "here is a claim".
Two jobs:

1. **Find the source** — identify which outlet published the submitted article
   (from an accompanying URL, a URL in the body, or a byline/credit line) and
   look up its bias/factuality. Pure/offline via tools/source_id.py.
2. **Extract the checkable claim** — one LLM call turns the article into its
   single most central, verifiable factual claim (plus up to two secondary
   claims). That primary claim becomes the `claim_id` the rest of the existing
   pipeline runs on, unchanged.

Writes a `SourceDoc` to the shared store; every downstream agent (and the
report cache) keys off the extracted primary claim exactly as in claim mode.
"""
from __future__ import annotations

import json
import logging

from newsfact.llm import LLMClient
from newsfact.memory.store import BlackboardStore, SourceDoc
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter
from newsfact.tools.bias_table import BiasTable
from newsfact.tools.source_id import identify_source

logger = logging.getLogger(__name__)

ROLE = "claim_extractor"

SYSTEM_PROMPT = """You are the Claim Extractor agent. You are given the full text of a news \
article a user wants fact-checked.

Return the single most central, checkable factual claim the article makes — the \
one a reader would most want verified. Phrase it as one self-contained sentence \
that stands on its own without the article (resolve pronouns, keep names, \
numbers and dates). Then list up to two secondary checkable claims, and a \
one-sentence neutral summary of the article.

Do NOT fact-check anything. Do NOT add caveats or opinion. Just extract.

Return ONLY a JSON object in this exact shape:
{"primary_claim": "<one sentence>",
 "secondary_claims": ["<sentence>", "<sentence>"],
 "article_summary": "<one sentence>"}
"""


def _fallback_primary(text: str) -> str:
    """No/*unusable* LLM: take the first substantial line (headline heuristic)."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 25 and not line.lower().startswith(("http", "by ", "source:", "source :", "photo", "image")):
            return line[:300]
    return " ".join(text.split()[:30])[:300] or "(empty article)"


def _parse(raw: str, text: str) -> tuple[str, list[str], str]:
    try:
        data = json.loads(raw)
        primary = str(data["primary_claim"]).strip()
        secondary = [str(s).strip() for s in data.get("secondary_claims", []) if str(s).strip()][:2]
        summary = str(data.get("article_summary", "")).strip()
        if not primary:
            raise ValueError("empty primary_claim")
        return primary, secondary, summary
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Claim Extractor LLM response unparseable; using headline heuristic", exc_info=True)
        return _fallback_primary(text), [], ""


def run_claim_extractor(
    article_text: str,
    url: str | None,
    store: BlackboardStore,
    llm_client: LLMClient,
    bias_table: BiasTable,
    reporter: Reporter | None = None,
) -> tuple[str, SourceDoc]:
    """Returns (claim_id_of_primary_claim, SourceDoc). The SourceDoc is also
    persisted to the shared store keyed by that claim_id."""
    reporter = reporter or NullReporter()
    reporter.emit(Event(EventKind.AGENT_START, ROLE,
                        "identifying the source outlet and extracting the checkable claim", None))

    # 1. find the source
    reporter.emit(Event(EventKind.TOOL_CALL, ROLE, "source identification (URL / byline / credit)", None,
                        data={"tool": "source_id", "url_given": bool(url)}))
    origin = identify_source(article_text, url, bias_table)
    if origin.identified:
        reporter.emit(Event(EventKind.NOTE, ROLE,
                            f"source: {origin.rating.name} ({origin.domain}) — bias={origin.rating.bias}, "
                            f"factuality={origin.rating.factuality} [via {origin.method}]", None))
    else:
        reporter.emit(Event(EventKind.NOTE, ROLE,
                            "source outlet could not be identified from the submitted text", None))

    # 2. extract the claim
    reporter.emit(Event(EventKind.TOOL_CALL, ROLE, "LLM: extract primary + secondary claims", None,
                        data={"tool": "llm"}))
    try:
        raw = llm_client.complete(SYSTEM_PROMPT, article_text[:8000])
        primary, secondary, summary = _parse(raw, article_text)
    except Exception:  # noqa: BLE001 - never crash the pipeline on the extractor
        logger.warning("Claim Extractor LLM call failed; using headline heuristic", exc_info=True)
        reporter.emit(Event(EventKind.ERROR, ROLE, "LLM call failed; using headline heuristic", None))
        primary, secondary, summary = _fallback_primary(article_text), [], ""

    cid = store.ensure_claim(primary)
    reporter.emit(Event(EventKind.NOTE, ROLE, f"primary claim: {primary}", cid,
                        data={"secondary": secondary, "summary": summary}))

    doc = SourceDoc(
        claim_id=cid,
        primary_claim=primary,
        secondary_claims=secondary,
        origin_domain=origin.domain,
        origin_name=origin.rating.name,
        origin_bias=origin.rating.bias,
        origin_factuality=origin.rating.factuality,
        origin_country=origin.rating.country,
        origin_method=origin.method,
        byline=origin.byline,
        excerpt=article_text.strip()[:600],
    )
    store.write_source_doc(doc, by=ROLE)
    reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "source identified, claim extracted", cid))
    return cid, doc
