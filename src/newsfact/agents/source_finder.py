"""Source-Finder agent.

Takes a claim, queries GDELT for coverage, and writes the results to the
shared blackboard store as a `Finding` with role="source_finder". Does not
call an LLM in v1 — it's a retrieval step, not a reasoning step. (An LLM call
to turn the claim into a better search query would be a natural v1.1
addition; see docs/HANDOFF.md.)
"""
from __future__ import annotations

import logging

from newsfact.memory.store import BlackboardStore, Finding
from newsfact.tools.gdelt import GdeltClient, GdeltError

logger = logging.getLogger(__name__)


def run_source_finder(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    max_records: int = 25,
) -> Finding:
    """Query GDELT for `claim_text` and persist the findings.

    On a GDELT failure, writes (and returns) an empty finding rather than
    raising — a claim with zero found sources is meaningful downstream
    signal for Cross-Checker (-> "unverifiable"), while an unhandled
    exception would kill the whole graph run over what might be a transient
    network blip.
    """
    try:
        articles = gdelt_client.search(claim_text, max_records=max_records)
    except GdeltError:
        logger.warning("GDELT search failed for claim %s; recording zero findings", cid, exc_info=True)
        articles = []

    finding = Finding(
        claim_id=cid,
        role="source_finder",
        articles=[a.to_dict() for a in articles],
    )
    store.write_finding(finding)
    return finding
