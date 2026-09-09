"""Cross-Checker agent.

Reads both evidence sets for a claim from the shared store — Source-Finder's
neutral coverage search and Opposition's adversarial counter-search — and asks
Claude to adjudicate between them: do independent outlets corroborate the
claim, do they conflict, or is coverage too thin to say?

Verdict labels are deliberately restricted to corroborated / disputed /
unverifiable (see docs/ARCHITECTURE.md) — never a binary true/false, and never
"corroborated" off a single source.

When the LLM returns `disputed` with low confidence, the orchestrator may run a
bounded deep-research loop (see graph.py) that broadens both searches and calls
Cross-Checker again.
"""
from __future__ import annotations

import json
import logging

# Re-exported for backwards compatibility (callers imported these from here in v1).
from newsfact.llm import AnthropicLLMClient, LLMClient  # noqa: F401
from newsfact.memory.store import BlackboardStore, Verdict
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter

logger = logging.getLogger(__name__)

ROLE = "cross_checker"
VALID_LABELS = {"corroborated", "disputed", "unverifiable"}

SYSTEM_PROMPT = """You are the Cross-Checker agent in a multi-agent news fact-checking pipeline.

You are given a claim and TWO independently gathered evidence sets:
- "source_finder": a neutral search for coverage of the claim.
- "opposition": an adversarial search whose mandate was to find contradicting \
reporting, missing caveats, and the strongest opposing view. Treat its \
"counter_framing" as an argument to weigh, not as fact.

Your job: adjudicate whether independent outlets corroborate the claim, dispute \
it, or whether there is not enough coverage to say either way.

Hard rules:
- NEVER label anything as flatly true or false. Use only these three labels:
  "corroborated" (multiple independent outlets report consistent core facts and \
the opposition set does not surface substantive contradiction),
  "disputed" (independent outlets or the two evidence sets report conflicting \
facts or framing),
  "unverifiable" (too few or too thin sources across BOTH sets to judge).
- A SINGLE source is never enough for "corroborated". Require multiple distinct \
outlets/domains reporting the same core facts.
- If the opposition set surfaces credible contradicting coverage, prefer \
"disputed" over "corroborated".
- confidence is a float 0.0-1.0 reflecting your confidence in the LABEL itself \
(not confidence that the claim is true). Use < 0.6 when the two evidence sets \
genuinely conflict and more evidence would help.

Respond with ONLY a JSON object, no other text, in this exact shape:
{"label": "corroborated" | "disputed" | "unverifiable", "confidence": 0.0-1.0, "reasoning": "2-4 sentences"}
"""


def _distinct_domains(articles: list[dict]) -> set[str]:
    return {a.get("source_domain", "unknown") for a in articles}


def _build_user_prompt(
    claim_text: str,
    sf_articles: list[dict],
    opp_articles: list[dict],
    opp_summary: str,
) -> str:
    payload = {
        "claim": claim_text,
        "distinct_source_domains": sorted(_distinct_domains(sf_articles + opp_articles)),
        "source_finder": {"articles": sf_articles},
        "opposition": {"counter_framing": opp_summary, "articles": opp_articles},
    }
    return json.dumps(payload, indent=2)


def _parse_llm_response(raw: str) -> tuple[str, float, str]:
    try:
        data = json.loads(raw)
        label = str(data["label"]).strip().lower()
        confidence = float(data["confidence"])
        reasoning = str(data["reasoning"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Could not parse Cross-Checker LLM response: {raw!r}") from exc

    if label not in VALID_LABELS:
        raise ValueError(f"LLM returned an invalid label: {label!r}")
    confidence = max(0.0, min(1.0, confidence))
    return label, confidence, reasoning


def run_cross_checker(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    llm_client: LLMClient,
    reporter: Reporter | None = None,
) -> Verdict:
    reporter = reporter or NullReporter()
    reporter.emit(Event(EventKind.AGENT_START, ROLE,
                        "adjudicating Source-Finder vs Opposition evidence", cid))

    sf = store.get_findings(cid, role="source_finder", by=ROLE)
    opp = store.get_findings(cid, role="opposition", by=ROLE)
    sf_articles: list[dict] = sf[0].articles if sf else []
    opp_articles: list[dict] = opp[0].articles if opp else []
    opp_summary: str = opp[0].summary if opp else ""

    distinct = _distinct_domains(sf_articles + opp_articles)
    if len(distinct) < 2:
        verdict = Verdict(
            claim_id=cid,
            label="unverifiable",
            confidence=1.0 if not (sf_articles or opp_articles) else 0.6,
            reasoning=(
                "No coverage found by either the coverage search or the adversarial search."
                if not (sf_articles or opp_articles)
                else "Only one distinct source domain found across both evidence sets; at least "
                "two independent outlets are required before a claim can be corroborated or disputed."
            ),
        )
        reporter.emit(Event(EventKind.NOTE, ROLE,
                            "short-circuit: <2 distinct domains across both sets -> unverifiable", cid))
        store.write_verdict(verdict, by=ROLE)
        reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "verdict written (short-circuit)", cid))
        return verdict

    reporter.emit(Event(EventKind.TOOL_CALL, ROLE,
                        f"LLM: adjudicate ({len(sf_articles)} coverage + {len(opp_articles)} counter articles, "
                        f"{len(distinct)} domains)", cid, data={"tool": "llm"}))
    user_prompt = _build_user_prompt(claim_text, sf_articles, opp_articles, opp_summary)
    try:
        raw = llm_client.complete(SYSTEM_PROMPT, user_prompt)
        label, confidence, reasoning = _parse_llm_response(raw)
    except ValueError:
        logger.warning("Cross-Checker LLM response unparseable for claim %s; falling back to unverifiable", cid, exc_info=True)
        reporter.emit(Event(EventKind.ERROR, ROLE, "LLM response unparseable; treating as unverifiable", cid))
        label, confidence, reasoning = (
            "unverifiable", 0.0,
            "Cross-Checker could not interpret the model's response; treated as unverifiable pending retry.",
        )
    except Exception:  # noqa: BLE001
        logger.warning("Cross-Checker LLM call failed for claim %s", cid, exc_info=True)
        reporter.emit(Event(EventKind.ERROR, ROLE, "LLM call failed; treating as unverifiable", cid))
        label, confidence, reasoning = (
            "unverifiable", 0.0,
            "Cross-Checker's reasoning call failed; treated as unverifiable pending retry.",
        )

    reporter.emit(Event(EventKind.NOTE, ROLE, f"verdict: {label} (confidence {confidence:.2f})", cid,
                        data={"label": label, "confidence": confidence}))
    verdict = Verdict(claim_id=cid, label=label, confidence=confidence, reasoning=reasoning)
    store.write_verdict(verdict, by=ROLE)
    reporter.emit(Event(EventKind.AGENT_DONE, ROLE, "verdict written", cid))
    return verdict
