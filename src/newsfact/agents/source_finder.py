"""Source-Finder agent.

Takes a claim, queries GDELT for coverage, and writes the results to the
shared blackboard store as a `Finding` with role="source_finder". Does not
call an LLM — it's a neutral retrieval step, not a reasoning step. (An LLM
call to turn the claim into a better search query would be a natural
addition; see docs/HANDOFF.md.)

Its adversarial counterpart is `opposition.py`, which runs alongside it and
deliberately searches for the counter-case.
"""
from __future__ import annotations

import logging

from newsfact.memory.store import BlackboardStore, Finding
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter
from newsfact.tools.gdelt import GdeltClient, GdeltError

logger = logging.getLogger(__name__)

ROLE = "source_finder"


def run_source_finder(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    max_records: int = 25,
    broadened: bool = False,
    reporter: Reporter | None = None,
) -> Finding:
    """Query GDELT for `claim_text` and persist the findings.

    On a GDELT failure, writes (and returns) an empty finding rather than
    raising — a claim with zero found sources is meaningful downstream signal
    for Cross-Checker (-> "unverifiable"), while an unhandled exception would
    kill the whole graph run over what might be a transient network blip.

    `broadened=True` is the deep-research loop's second pass: it widens the
    query and *merges* into the existing finding instead of overwriting it.
    """
    reporter = reporter or NullReporter()
    reporter.emit(Event(EventKind.AGENT_START, ROLE,
                        "widening the coverage search" if broadened else "searching news coverage for the claim",
                        cid))
    query = f"{claim_text} latest update report" if broadened else claim_text
    reporter.emit(Event(EventKind.TOOL_CALL, ROLE, f"GDELT DOC 2.0 query: {query!r}", cid,
                        data={"tool": "gdelt", "max_records": max_records}))
    try:
        articles = gdelt_client.search(query, max_records=max_records)
    except GdeltError:
        logger.warning("GDELT search failed for claim %s; recording zero findings", cid, exc_info=True)
        reporter.emit(Event(EventKind.ERROR, ROLE, "GDELT search failed; recording zero findings", cid))
        articles = []

    domains = sorted({a.source_domain for a in articles})
    reporter.emit(Event(EventKind.NOTE, ROLE,
                        f"found {len(articles)} article(s) across {len(domains)} domain(s)", cid,
                        data={"domains": domains}))

    finding = Finding(
        claim_id=cid,
        role=ROLE,
        articles=[a.to_dict() for a in articles],
        summary=f"{len(articles)} articles from {len(domains)} outlets via GDELT",
    )
    if broadened:
        store.merge_finding(finding, by=ROLE)
        finding = store.get_findings(cid, role=ROLE)[0]
    else:
        store.write_finding(finding, by=ROLE)
    reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "coverage search complete", cid))
    return finding
