"""Bias/Blindspot Analyzer agent.

Mechanical, no LLM: pull every article both evidence agents put on the
blackboard, map each outlet to a bias/factuality rating from the curated table
(newsfact/tools/bias_table.py), and compute the left/center/right coverage
spread plus blindspot flags — which side of the spectrum isn't covering this
story, and how lopsided the coverage is.

In article-input mode (v2.1) it also folds in the outlet that published the
submitted article: it joins the spread, and drives extra blindspot notes —
most importantly "only the submitting outlet carries this; no independent
corroboration".

Writes a `BiasReport` to the shared store for the Writer to merge in.
"""
from __future__ import annotations

import logging
from collections import Counter

from newsfact.memory.store import BiasReport, BlackboardStore
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter
from newsfact.tools.bias_table import BiasTable

logger = logging.getLogger(__name__)

ROLE = "bias_analyzer"


def _dominant_side(spread: dict[str, int]) -> str:
    rated = {k: spread.get(k, 0) for k in ("left", "center", "right")}
    total = sum(rated.values())
    if total == 0:
        return "none"
    top = max(rated, key=rated.__getitem__)
    # "balanced" if no single side holds a majority of the *rated* outlets
    if rated[top] <= total / 2:
        return "balanced"
    return top


def _blindspots(spread: dict[str, int], outlets: list[dict]) -> list[str]:
    notes: list[str] = []
    left, center, right = spread.get("left", 0), spread.get("center", 0), spread.get("right", 0)
    rated_total = left + center + right

    if rated_total == 0:
        notes.append("No retrieved outlet could be matched to a bias rating — spectrum coverage unknown.")
        return notes

    if rated_total < 2:
        notes.append(f"Only {rated_total} rated outlet in the retrieved coverage — too few to assess spectrum spread.")
        return notes

    if left == 0 and right > 0:
        notes.append(f"Left-of-center blindspot: {right} right-leaning outlet(s) but 0 left-leaning covering this.")
    if right == 0 and left > 0:
        notes.append(f"Right-of-center blindspot: {left} left-leaning outlet(s) but 0 right-leaning covering this.")
    if center == 0 and rated_total > 0:
        notes.append("No center/wire-service outlet in the retrieved coverage — leans on partisan sources.")

    strongest = max(left, center, right)
    if rated_total >= 3 and strongest >= 0.75 * rated_total and strongest != rated_total:
        side = {left: "left", center: "center", right: "right"}[strongest]
        notes.append(f"Coverage is heavily skewed {side} ({strongest}/{rated_total} rated outlets).")

    low_fact = [o["domain"] for o in outlets if o.get("factuality") in ("low", "very-low")]
    if low_fact:
        notes.append("Low-factuality outlets in the evidence pool: " + ", ".join(sorted(set(low_fact))) + ".")

    unknown = spread.get("unknown", 0)
    if unknown and unknown >= rated_total:
        notes.append(f"{unknown} unrated outlet(s) — as many as the rated ones; spread estimate is weak.")

    if not notes:
        notes.append("No major blindspot: the story is covered across the spectrum.")
    return notes


def _origin_notes(source_doc, retrieved_domains: set[str]) -> list[str]:
    """Blindspot notes specific to the submitted article's own publisher."""
    if source_doc is None:
        return []
    notes: list[str] = []
    if source_doc.origin_method == "none":
        notes.append("Submitted article: publishing outlet could not be identified from the text.")
        return notes

    name = source_doc.origin_name
    notes.append(
        f"Submitted article is from {name} ({source_doc.origin_domain}) — bias "
        f"'{source_doc.origin_bias}', factuality '{source_doc.origin_factuality}'."
    )
    independent = retrieved_domains - {source_doc.origin_domain}
    if not independent:
        notes.append(
            f"No independent outlet corroborates the submitted article — only its own "
            f"publisher ({name}) carries this claim in the retrieved coverage."
        )
    if source_doc.origin_factuality in ("low", "very-low"):
        notes.append(f"The submitting outlet ({name}) carries a low factuality rating — weigh its reporting cautiously.")
    return notes


def run_bias_analyzer(
    cid: str,
    store: BlackboardStore,
    bias_table: BiasTable,
    reporter: Reporter | None = None,
) -> BiasReport:
    reporter = reporter or NullReporter()
    reporter.emit(Event(EventKind.AGENT_START, ROLE,
                        "mapping outlets to bias ratings and computing spread", cid))

    findings = store.get_findings(cid, by=ROLE)
    articles = [a for f in findings for a in f.articles]

    reporter.emit(Event(EventKind.TOOL_CALL, ROLE,
                        f"outlet bias table lookup ({len(bias_table)} outlets on file)", cid,
                        data={"tool": "bias_table"}))

    per_domain: dict[str, dict] = {}
    for a in articles:
        domain = a.get("source_domain", "unknown")
        if domain not in per_domain:
            r = bias_table.lookup(domain)
            per_domain[domain] = {
                "domain": domain,
                "name": r.name,
                "bias": r.bias,
                "side": r.side,
                "factuality": r.factuality,
                "country": r.country,
                "count": 0,
                "origin": False,
            }
        per_domain[domain]["count"] += 1

    # v2.1: fold in the outlet that published the submitted article
    source_doc = store.get_source_doc(cid, by=ROLE)
    retrieved_domains = set(per_domain)
    if source_doc is not None and source_doc.origin_method != "none":
        od = source_doc.origin_domain
        entry = per_domain.get(od)
        if entry is None:
            r = bias_table.lookup(od)
            entry = per_domain[od] = {
                "domain": od, "name": r.name, "bias": r.bias, "side": r.side,
                "factuality": r.factuality, "country": r.country, "count": 0, "origin": False,
            }
        entry["origin"] = True
        entry["count"] += 1

    outlets = sorted(per_domain.values(), key=lambda o: (-o["count"], o["domain"]))
    spread = Counter(o["side"] for o in outlets)
    spread_d = {k: int(spread.get(k, 0)) for k in ("left", "center", "right", "unknown")}
    dominant = _dominant_side(spread_d)
    blindspots = _origin_notes(source_doc, retrieved_domains) + _blindspots(spread_d, outlets)

    reporter.emit(Event(EventKind.NOTE, ROLE,
                        f"spread L/C/R = {spread_d['left']}/{spread_d['center']}/{spread_d['right']} "
                        f"(+{spread_d['unknown']} unrated); dominant={dominant}", cid,
                        data={"spread": spread_d}))
    for note in blindspots:
        reporter.emit(Event(EventKind.NOTE, ROLE, f"blindspot: {note}", cid))

    report = BiasReport(
        claim_id=cid,
        spread=spread_d,
        outlets=outlets,
        blindspots=blindspots,
        dominant_side=dominant,
    )
    store.write_bias_report(report, by=ROLE)
    reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "bias report written", cid))
    return report
