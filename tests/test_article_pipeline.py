"""End-to-end article-input mode (v2.1), driven by the offline demo fixtures."""
import tempfile
from pathlib import Path

from newsfact.demo import FakeGdeltClient, FakeLLMClient
from newsfact.graph import run_article_pipeline
from newsfact.memory.store import BlackboardStore
from newsfact.observability.events import AuditLogReporter, NullReporter
from newsfact.tools.bias_table import BiasTable

CORROBORATED_ARTICLE = (
    "Source: https://www.hindustantimes.com/business/india-gdp\n"
    "By Arun Kumar\n\n"
    "India's economy grew 7.8% in the most recent quarter, the fastest among major economies, "
    "government data showed. Economists cautioned the deflator flattered the number.\n"
)

ONLY_ORIGIN_ARTICLE = (
    "The central bank announced an emergency interest rate cut over the weekend, a report said. "
    "Officials did not confirm the move.\n\n"
    "Read more: https://timesofindia.indiatimes.com/business/rate-cut\n"
)


def make_store():
    store = BlackboardStore(Path(tempfile.mkdtemp()) / "t.db")
    if isinstance(store.reporter, NullReporter):
        store.set_reporter(AuditLogReporter(store))
    return store


def run(article, store, url=None):
    return run_article_pipeline(article, store, FakeGdeltClient(), FakeLLMClient(), BiasTable.load(), url=url)


def test_article_in_report_out_with_source_identified():
    store = make_store()
    state = run(CORROBORATED_ARTICLE, store)
    cid = state["claim_id"]

    doc = store.get_source_doc(cid)
    assert doc is not None
    assert doc.origin_domain == "hindustantimes.com"
    assert doc.origin_method == "url"
    assert doc.primary_claim  # extracted, non-empty

    # the normal pipeline ran on the extracted claim
    assert store.get_verdict(cid).label == "corroborated"
    report = store.get_report(cid)
    assert "Source of the submitted article" in report.body_md
    assert "Hindustan Times" in report.body_md


def test_origin_outlet_joins_the_bias_spread():
    store = make_store()
    cid = run(CORROBORATED_ARTICLE, store)["claim_id"]
    bias = store.get_bias_report(cid)

    assert any(o.get("origin") for o in bias.outlets)
    assert any("Hindustan Times" in n for n in bias.blindspots)


def test_flags_when_only_the_submitting_outlet_carries_the_claim():
    store = make_store()
    cid = run(ONLY_ORIGIN_ARTICLE, store)["claim_id"]
    bias = store.get_bias_report(cid)

    assert any("No independent outlet corroborates" in n for n in bias.blindspots)
    assert store.get_verdict(cid).label == "unverifiable"


def test_claim_extractor_appears_in_the_audit_trail():
    store = make_store()
    cid = run(CORROBORATED_ARTICLE, store)["claim_id"]
    agents = {e.agent for e in store.get_audit(cid)}
    assert "claim_extractor" in agents
    assert {"source_finder", "opposition", "cross_checker", "bias_analyzer", "writer"} <= agents


def test_explicit_article_url_is_used_for_source_id():
    store = make_store()
    plain = "India's economy grew 7.8% in the most recent quarter, the fastest among major economies.\n"
    cid = run(plain, store, url="https://www.thehindu.com/business/gdp")["claim_id"]
    assert store.get_source_doc(cid).origin_domain == "thehindu.com"
