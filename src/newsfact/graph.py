"""LangGraph wiring: Source-Finder -> Cross-Checker.

Deliberately a thin layer: each node just calls the corresponding agent
function and returns the piece of state it changed. All real state lives in
the shared BlackboardStore, not in the LangGraph state object itself — the
graph state here is just plumbing (claim text/id) plus the final result for
convenience, per the hybrid-blackboard design in docs/ARCHITECTURE.md.

Adding the Opposition agent later (see docs/HANDOFF.md) means: add an
`opposition` node that runs alongside `source_finder` (both as entry-point
parallel branches into `cross_checker`), and change `cross_checker`'s node to
read both roles' findings instead of just "source_finder".
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from newsfact.agents.cross_checker import LLMClient, run_cross_checker
from newsfact.agents.source_finder import run_source_finder
from newsfact.memory.store import BlackboardStore
from newsfact.tools.gdelt import GdeltClient


class GraphState(TypedDict, total=False):
    claim_text: str
    claim_id: str
    verdict_label: str
    verdict_confidence: float
    verdict_reasoning: str


def build_graph(store: BlackboardStore, gdelt_client: GdeltClient, llm_client: LLMClient):
    """Build (and compile) the Source-Finder -> Cross-Checker graph.

    `store`, `gdelt_client`, and `llm_client` are closed over by the node
    functions rather than threaded through GraphState, since they're
    infrastructure, not data the graph itself needs to reason about.
    """

    def source_finder_node(state: GraphState) -> dict[str, Any]:
        run_source_finder(state["claim_text"], state["claim_id"], store, gdelt_client)
        return {}

    def cross_checker_node(state: GraphState) -> dict[str, Any]:
        verdict = run_cross_checker(state["claim_text"], state["claim_id"], store, llm_client)
        return {
            "verdict_label": verdict.label,
            "verdict_confidence": verdict.confidence,
            "verdict_reasoning": verdict.reasoning,
        }

    graph = StateGraph(GraphState)
    graph.add_node("source_finder", source_finder_node)
    graph.add_node("cross_checker", cross_checker_node)
    graph.set_entry_point("source_finder")
    graph.add_edge("source_finder", "cross_checker")
    graph.add_edge("cross_checker", END)
    return graph.compile()


def run_pipeline(
    claim_text: str,
    store: BlackboardStore,
    gdelt_client: GdeltClient,
    llm_client: LLMClient,
) -> GraphState:
    cid = store.ensure_claim(claim_text)
    app = build_graph(store, gdelt_client, llm_client)
    result = app.invoke({"claim_text": claim_text, "claim_id": cid})
    return result
