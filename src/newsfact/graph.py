"""LangGraph wiring for the v2 pipeline.

    START ─┬─▶ source_finder ─┐
           └─▶ opposition ────┴─▶ cross_checker ──(disputed & low-confidence
                                        │            & passes < max)──▶ deep_research ─┐
                                        │                                              │
                                        │ ◀────────────────────────────────────────────┘
                                        ▼ (else)
                                   bias_analyzer ──▶ writer ──▶ END

Each node is a thin adapter: it calls the agent function and returns only the
slice of GraphState it changed. The real state lives in the shared
BlackboardStore, not in GraphState — the graph object just carries plumbing
(claim text/id, loop counter) and the final verdict for convenience, per the
hybrid-blackboard design in docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from newsfact.agents.bias_analyzer import run_bias_analyzer
from newsfact.agents.claim_extractor import run_claim_extractor
from newsfact.agents.cross_checker import run_cross_checker
from newsfact.agents.opposition import run_opposition
from newsfact.agents.source_finder import run_source_finder
from newsfact.agents.writer import run_writer
from newsfact.llm import LLMClient
from newsfact.memory.store import BlackboardStore
from newsfact.observability.events import Event, EventKind, NullReporter, Reporter
from newsfact.tools.bias_table import BiasTable
from newsfact.tools.gdelt import GdeltClient

DEEP_RESEARCH_CONFIDENCE = 0.6
MAX_RESEARCH_PASSES = 1


class GraphState(TypedDict, total=False):
    claim_text: str
    claim_id: str
    research_passes: int
    verdict_label: str
    verdict_confidence: float
    verdict_reasoning: str
    report_headline: str
    report_body_md: str


def build_graph(
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    llm_client: LLMClient,
    bias_table: BiasTable,
    reporter: Reporter | None = None,
):
    """Build (and compile) the 5-agent graph. Infrastructure is closed over
    rather than threaded through GraphState."""
    reporter = reporter or NullReporter()

    def source_finder_node(state: GraphState) -> dict[str, Any]:
        run_source_finder(state["claim_text"], state["claim_id"], store, gdelt_client, reporter=reporter)
        return {}

    def opposition_node(state: GraphState) -> dict[str, Any]:
        run_opposition(state["claim_text"], state["claim_id"], store, gdelt_client, llm_client, reporter=reporter)
        return {}

    def cross_checker_node(state: GraphState) -> dict[str, Any]:
        verdict = run_cross_checker(state["claim_text"], state["claim_id"], store, llm_client, reporter=reporter)
        return {
            "verdict_label": verdict.label,
            "verdict_confidence": verdict.confidence,
            "verdict_reasoning": verdict.reasoning,
        }

    def deep_research_node(state: GraphState) -> dict[str, Any]:
        passes = state.get("research_passes", 0) + 1
        reporter.emit(Event(
            EventKind.LOOP, "orchestrator",
            f"conflicting/low-confidence verdict — deep-research pass {passes}: broadening both searches",
            state["claim_id"], data={"pass": passes},
        ))
        run_source_finder(state["claim_text"], state["claim_id"], store, gdelt_client,
                          broadened=True, reporter=reporter)
        run_opposition(state["claim_text"], state["claim_id"], store, gdelt_client, llm_client,
                       broadened=True, reporter=reporter)
        return {"research_passes": passes}

    def bias_analyzer_node(state: GraphState) -> dict[str, Any]:
        run_bias_analyzer(state["claim_id"], store, bias_table, reporter=reporter)
        return {}

    def writer_node(state: GraphState) -> dict[str, Any]:
        report = run_writer(state["claim_text"], state["claim_id"], store, llm_client, reporter=reporter)
        return {"report_headline": report.headline, "report_body_md": report.body_md}

    def route_after_cross_check(state: GraphState) -> str:
        label = state.get("verdict_label")
        conf = state.get("verdict_confidence", 1.0)
        passes = state.get("research_passes", 0)
        if label == "disputed" and conf < DEEP_RESEARCH_CONFIDENCE and passes < MAX_RESEARCH_PASSES:
            return "deep_research"
        return "bias_analyzer"

    graph = StateGraph(GraphState)
    graph.add_node("source_finder", source_finder_node)
    graph.add_node("opposition", opposition_node)
    graph.add_node("cross_checker", cross_checker_node)
    graph.add_node("deep_research", deep_research_node)
    graph.add_node("bias_analyzer", bias_analyzer_node)
    graph.add_node("writer", writer_node)

    graph.add_edge(START, "source_finder")
    graph.add_edge(START, "opposition")
    graph.add_edge("source_finder", "cross_checker")
    graph.add_edge("opposition", "cross_checker")
    graph.add_conditional_edges(
        "cross_checker",
        route_after_cross_check,
        {"deep_research": "deep_research", "bias_analyzer": "bias_analyzer"},
    )
    graph.add_edge("deep_research", "cross_checker")
    graph.add_edge("bias_analyzer", "writer")
    graph.add_edge("writer", END)
    return graph.compile()


def _invoke_graph(
    claim_text: str,
    cid: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    llm_client: LLMClient,
    bias_table: BiasTable,
    reporter: Reporter,
) -> GraphState:
    app = build_graph(store, gdelt_client, llm_client, bias_table, reporter)
    result = app.invoke({"claim_text": claim_text, "claim_id": cid, "research_passes": 0})
    reporter.emit(Event(EventKind.ITEM_DONE, "orchestrator",
                        f"done: {result.get('verdict_label')} "
                        f"({result.get('verdict_confidence', 0.0):.2f})", cid))
    return result


def run_pipeline(
    claim_text: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    llm_client: LLMClient,
    bias_table: BiasTable | None = None,
    reporter: Reporter | None = None,
) -> GraphState:
    """Claim mode: check a single claim/headline string."""
    # Fall back to whatever observability the store already carries, so callers
    # that configured it once (main.py, tests) don't have to pass it twice.
    reporter = reporter or store.reporter or NullReporter()
    bias_table = bias_table or BiasTable.load()
    cid = store.ensure_claim(claim_text)
    reporter.emit(Event(EventKind.ITEM_START, "orchestrator", claim_text, cid))
    return _invoke_graph(claim_text, cid, store, gdelt_client, llm_client, bias_table, reporter)


def run_article_pipeline(
    article_text: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    llm_client: LLMClient,
    bias_table: BiasTable | None = None,
    reporter: Reporter | None = None,
    url: str | None = None,
) -> GraphState:
    """Article mode (v2.1): submit a full article. The Claim Extractor identifies
    the source outlet and pulls out the primary checkable claim; the normal
    5-agent graph then runs on that claim."""
    reporter = reporter or store.reporter or NullReporter()
    bias_table = bias_table or BiasTable.load()

    first_line = next((ln.strip() for ln in article_text.splitlines() if ln.strip()), "(submitted article)")
    # ITEM_START with a provisional id; the real claim_id follows extraction.
    reporter.emit(Event(EventKind.ITEM_START, "orchestrator", f"[article] {first_line[:120]}", None))

    cid, _doc = run_claim_extractor(article_text, url, store, llm_client, bias_table, reporter)
    return _invoke_graph(_doc.primary_claim, cid, store, gdelt_client, llm_client, bias_table, reporter)
