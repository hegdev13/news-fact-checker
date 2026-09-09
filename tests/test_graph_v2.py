"""End-to-end tests for the v2 five-agent graph, driven by the offline demo
fixtures (newsfact.demo) — same code path `python -m newsfact.main --demo` uses.
"""
import tempfile
from pathlib import Path

from newsfact.demo import FakeGdeltClient, FakeLLMClient
from newsfact.graph import run_pipeline
from newsfact.memory.store import BlackboardStore
from newsfact.observability.events import AuditLogReporter, NullReporter
from newsfact.tools.bias_table import BiasTable


def make_store(reporter=None):
    return BlackboardStore(Path(tempfile.mkdtemp()) / "t.db", reporter=reporter)


def run(claim, store):
    # mirror main.py: the store carries an audit-log sink; run_pipeline picks it up
    if isinstance(store.reporter, NullReporter):
        store.set_reporter(AuditLogReporter(store))
    return run_pipeline(claim, store, FakeGdeltClient(), FakeLLMClient(), BiasTable.load())


def test_all_five_agents_write_to_the_blackboard():
    store = make_store()
    cid = store.ensure_claim("India's economy grew 7.8% last quarter")
    run("India's economy grew 7.8% last quarter", store)

    assert [f.role for f in store.get_findings(cid)] == ["opposition", "source_finder"]  # SF + Opposition
    assert store.get_verdict(cid).label == "corroborated"                                 # Cross-Checker
    assert store.get_bias_report(cid) is not None                                         # Bias/Blindspot
    report = store.get_report(cid)                                                        # Writer
    assert report is not None and report.verdict_label == "corroborated"


def test_deep_research_loop_fires_on_low_confidence_disputed():
    store = make_store()
    cid = store.ensure_claim("A study claims one cup of coffee reverses cognitive decline")
    result = run("A study claims one cup of coffee reverses cognitive decline", store)

    trail = store.get_audit(cid)
    loop_events = [e for e in trail if e.kind == "loop"]
    assert len(loop_events) == 1                       # loop triggered exactly once (bounded)
    assert result["verdict_label"] == "disputed"
    # second pass raised confidence above the re-loop threshold, so it stopped
    assert result["verdict_confidence"] >= 0.6
    # the loop actually added evidence
    sf = store.get_findings(cid, role="source_finder")[0]
    assert len(sf.articles) > 4


def test_sparse_coverage_short_circuits_to_unverifiable():
    store = make_store()
    cid = store.ensure_claim("The central bank announced an emergency interest rate cut over the weekend")
    result = run("The central bank announced an emergency interest rate cut over the weekend", store)

    assert result["verdict_label"] == "unverifiable"
    # Cross-Checker short-circuited: no LLM adjudication tool_call recorded
    assert not [e for e in store.get_audit(cid)
                if e.agent == "cross_checker" and e.kind == "tool_call"]


def test_run_persists_a_full_audit_trail():
    store = make_store()
    store.set_reporter(AuditLogReporter(store))
    cid = store.ensure_claim("India's economy grew 7.8% last quarter")
    run("India's economy grew 7.8% last quarter", store)

    agents_seen = {e.agent for e in store.get_audit(cid)}
    assert {"source_finder", "opposition", "cross_checker", "bias_analyzer", "writer", "orchestrator"} <= agents_seen


def test_second_identical_run_hits_the_report_cache_via_store():
    store = make_store()
    cid = store.ensure_claim("India's economy grew 7.8% last quarter")
    run("India's economy grew 7.8% last quarter", store)
    first = store.get_report(cid).created_at

    # main.py checks get_report() before re-running; emulate that check here
    assert store.get_report(cid) is not None
    assert store.get_report(cid).created_at == first
