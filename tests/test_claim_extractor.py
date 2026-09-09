import json
import tempfile
from pathlib import Path

from newsfact.agents.claim_extractor import run_claim_extractor
from newsfact.memory.store import BlackboardStore, claim_id
from newsfact.tools.bias_table import BiasTable

TABLE = BiasTable({
    "thehindu.com": {"name": "The Hindu", "bias": "center-left", "factuality": "high", "country": "IN"},
})

ARTICLE = (
    "Source: https://www.thehindu.com/business/story\n"
    "By Meera Iyer\n\n"
    "India's economy grew 7.8% in the most recent quarter, official data showed, "
    "the fastest pace among major economies.\n"
)


class FakeLLM:
    def __init__(self, response):
        self._response = response
        self.saw_system = None

    def complete(self, system, user):
        self.saw_system = system
        return self._response


def make_store():
    return BlackboardStore(Path(tempfile.mkdtemp()) / "t.db")


def test_identifies_source_and_extracts_primary_claim():
    store = make_store()
    llm = FakeLLM(json.dumps({
        "primary_claim": "India's economy grew 7.8% last quarter, the fastest among major economies.",
        "secondary_claims": ["Growth was driven by services."],
        "article_summary": "A GDP report.",
    }))

    cid, doc = run_claim_extractor(ARTICLE, None, store, llm, TABLE)

    assert "Claim Extractor agent" in llm.saw_system
    assert cid == claim_id("India's economy grew 7.8% last quarter, the fastest among major economies.")
    assert doc.origin_domain == "thehindu.com"
    assert doc.origin_name == "The Hindu"
    assert doc.origin_method == "url"
    assert doc.byline == "Meera Iyer"
    assert doc.secondary_claims == ["Growth was driven by services."]
    # persisted and keyed by the extracted claim's id
    assert store.get_source_doc(cid).primary_claim.startswith("India's economy grew 7.8%")


def test_explicit_url_arg_overrides_missing_in_text():
    store = make_store()
    llm = FakeLLM(json.dumps({"primary_claim": "A claim.", "secondary_claims": [], "article_summary": ""}))
    cid, doc = run_claim_extractor("Body with no url and no outlet name.", "https://thehindu.com/x", store, llm, TABLE)
    assert doc.origin_method == "url"
    assert doc.origin_domain == "thehindu.com"


def test_falls_back_to_headline_heuristic_on_bad_llm_json():
    store = make_store()
    article = "India's economy grew 7.8% last quarter, the fastest among major economies\n\nMore text here."
    cid, doc = run_claim_extractor(article, None, store, FakeLLM("not json"), TABLE)
    assert doc.primary_claim.startswith("India's economy grew 7.8%")
    assert doc.secondary_claims == []
    assert store.get_claim_text(cid) == doc.primary_claim


def test_unidentified_source_still_produces_a_claim():
    store = make_store()
    llm = FakeLLM(json.dumps({"primary_claim": "Something happened.", "secondary_claims": [], "article_summary": ""}))
    cid, doc = run_claim_extractor("no clues at all here", None, store, llm, TABLE)
    assert doc.origin_method == "none"
    assert doc.origin_bias == "unknown"
    assert store.get_source_doc(cid) is not None
