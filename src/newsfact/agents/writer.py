"""Writer agent.

Reads every artifact the other four agents left on the blackboard — both
evidence sets, the verdict, the bias report — and asks the LLM to merge them
into one structured report: verdict + confidence, the evidence for and against,
Opposition's strongest counterpoint, the bias/blindspot breakdown.

The audit trail section is assembled deterministically from the `audit_log`
table (not written by the LLM) so it faithfully reflects what actually
happened. The whole report is persisted as a `Report`, which also serves as the
"already checked this claim" cache entry.
"""
from __future__ import annotations

import json
import logging

from newsfact.llm import LLMClient
from newsfact.memory.store import BlackboardStore, Report, SourceDoc
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter

logger = logging.getLogger(__name__)

ROLE = "writer"

SYSTEM_PROMPT = """You are the Writer agent in a multi-agent news fact-checking pipeline.

You receive structured JSON: the claim, the Cross-Checker verdict (label +
confidence + reasoning), the Source-Finder and Opposition evidence, and the
Bias/Blindspot Analyzer's spread. Merge it into a tight report for a reader.

Hard rules:
- Use the Cross-Checker's label verbatim: "corroborated" / "disputed" /
  "unverifiable". Never say a claim is simply true or false. Never override the
  verdict.
- State the confidence as given.
- Always include Opposition's strongest counterpoint, even when the verdict is
  "corroborated".
- Report the L/C/R spread and name the blindspot(s) plainly.
- If "submitted_article" is present, the claim was extracted from an article the
  user provided: reference its originating outlet and whether independent
  outlets corroborate it.
- Be concise. No preamble, no "as an AI".

Return ONLY a JSON object in this exact shape:
{"headline": "<=12 word neutral summary of the finding",
 "body_md": "<markdown body, ~150-250 words, with these sections as bold lines: **Verdict**, **What the coverage shows**, **The opposing case**, **Bias & blindspots**>"}
"""


def _fallback_report(claim_text: str, verdict, bias, sf_articles, opp_articles, opp_summary="") -> tuple[str, str]:
    conf = f"{verdict.confidence:.0%}" if verdict else "n/a"
    label = verdict.label if verdict else "unverifiable"
    spread = bias.spread if bias else {"left": 0, "center": 0, "right": 0, "unknown": 0}
    blind = "; ".join(bias.blindspots) if bias and bias.blindspots else "not assessed"
    counter = opp_articles[0]["title"] if opp_articles else "no counter-coverage retrieved"
    headline = f"Claim is {label} (confidence {conf})"
    body = (
        f"**Verdict**\nThe claim is **{label}** with {conf} confidence in that label. "
        f"{verdict.reasoning if verdict else ''}\n\n"
        f"**What the coverage shows**\nSource-Finder retrieved {len(sf_articles)} article(s); "
        f"Opposition retrieved {len(opp_articles)} counter-article(s).\n\n"
        f"**The opposing case**\n{opp_summary or counter}\n\n"
        f"**Bias & blindspots**\nSpread L/C/R = {spread.get('left',0)}/{spread.get('center',0)}/"
        f"{spread.get('right',0)} (+{spread.get('unknown',0)} unrated). {blind}"
    )
    return headline, body


def _source_md(doc: SourceDoc | None) -> str:
    """Deterministic 'find the source' section for article-input mode — prepended
    to the report so it's always present and accurate regardless of the LLM."""
    if doc is None:
        return ""
    lines = ["**Source of the submitted article**", ""]
    if doc.origin_method == "none":
        lines.append("- Publishing outlet: could not be identified from the submitted text.")
    else:
        lines.append(
            f"- Publishing outlet: **{doc.origin_name}** ({doc.origin_domain}) — "
            f"bias `{doc.origin_bias}`, factuality `{doc.origin_factuality}`, "
            f"{doc.origin_country} (identified via {doc.origin_method})."
        )
    if doc.byline:
        lines.append(f"- Byline: {doc.byline}")
    lines.append(f"- Extracted primary claim: {doc.primary_claim}")
    if doc.secondary_claims:
        lines.append("- Secondary claims: " + "; ".join(doc.secondary_claims))
    return "\n".join(lines) + "\n\n"


def _audit_trail_md(store: BlackboardStore, cid: str) -> str:
    events = store.get_audit(cid)
    if not events:
        return ""
    lines = ["", "**Audit trail**", ""]
    for e in events:
        if e.kind in ("tool_call", "bb_write", "loop", "error"):
            lines.append(f"- `{e.agent}` — {e.message}")
    return "\n".join(lines)


def run_writer(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    llm_client: LLMClient,
    reporter: Reporter | None = None,
) -> Report:
    reporter = reporter or NullReporter()
    reporter.emit(Event(EventKind.AGENT_START, ROLE, "merging all findings into the final report", cid))

    verdict = store.get_verdict(cid, by=ROLE)
    bias = store.get_bias_report(cid, by=ROLE)
    source_doc = store.get_source_doc(cid, by=ROLE)
    findings = {f.role: f for f in store.get_findings(cid, by=ROLE)}
    sf_articles = findings["source_finder"].articles if "source_finder" in findings else []
    opp = findings.get("opposition")
    opp_articles = opp.articles if opp else []
    opp_summary = opp.summary if opp else ""

    payload = json.dumps({
        "claim": claim_text,
        "submitted_article": None if source_doc is None else {
            "origin_outlet": source_doc.origin_name,
            "origin_domain": source_doc.origin_domain,
            "origin_bias": source_doc.origin_bias,
            "origin_factuality": source_doc.origin_factuality,
            "identified_via": source_doc.origin_method,
            "secondary_claims": source_doc.secondary_claims,
        },
        "verdict": None if not verdict else {
            "label": verdict.label, "confidence": verdict.confidence, "reasoning": verdict.reasoning,
        },
        "source_finder": {"count": len(sf_articles), "articles": sf_articles[:12]},
        "opposition": {"counter_framing": opp_summary, "count": len(opp_articles), "articles": opp_articles[:12]},
        "bias": None if not bias else {
            "spread": bias.spread, "dominant_side": bias.dominant_side,
            "blindspots": bias.blindspots, "outlets": bias.outlets,
        },
    }, indent=2)

    reporter.emit(Event(EventKind.TOOL_CALL, ROLE, "LLM: compose report from blackboard artifacts", cid,
                        data={"tool": "llm"}))
    headline, body = "", ""
    try:
        raw = llm_client.complete(SYSTEM_PROMPT, payload)
        data = json.loads(raw)
        headline = str(data["headline"]).strip()
        body = str(data["body_md"]).strip()
        if not headline or not body:
            raise ValueError("empty headline/body")
    except Exception:  # noqa: BLE001
        logger.warning("Writer LLM response unusable for claim %s; using deterministic fallback", cid, exc_info=True)
        reporter.emit(Event(EventKind.ERROR, ROLE, "LLM report unusable; using deterministic fallback", cid))
        headline, body = _fallback_report(claim_text, verdict, bias, sf_articles, opp_articles, opp_summary)

    body = _source_md(source_doc) + body + "\n" + _audit_trail_md(store, cid)

    report = Report(
        claim_id=cid,
        headline=headline,
        verdict_label=verdict.label if verdict else "unverifiable",
        verdict_confidence=verdict.confidence if verdict else 0.0,
        body_md=body.strip(),
    )
    store.write_report(report, by=ROLE)
    reporter.emit(Event(EventKind.REPORT, ROLE, headline, cid,
                        data={"label": report.verdict_label, "confidence": report.verdict_confidence}))
    reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "final report written", cid))
    return report
