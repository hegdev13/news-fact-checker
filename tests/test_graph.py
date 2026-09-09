import json
import tempfile
from pathlib import Path

from newsfact.graph import run_pipeline
from newsfact.memory.store import BlackboardStore
from newsfact.tools.gdelt import Article


class FakeGdeltClient:
    def __init__(self, articles):
        self._articles = articles

    def search(self, query, max_records=25):
        return self._articles


class FakeLLMClient:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, user):
        return self._response


def make_store() -> BlackboardStore:
    tmpdir = tempfile.mkdtemp()
    return BlackboardStore(Path(tmpdir) / "test.db")


def test_end_to_end_pipeline_corroborated():
    store = make_store()
    gdelt = FakeGdeltClient([
        Article(title="A", url="ua", source_domain="a.com", seen_date="20260101"),
        Article(title="B", url="ub", source_domain="b.com", seen_date="20260101"),
    ])
    llm_response = json.dumps({
        "label": "corroborated",
        "confidence": 0.8,
        "reasoning": "Consistent reporting across two outlets.",
    })
    llm = FakeLLMClient(llm_response)

    result = run_pipeline("Some claim", store, gdelt, llm)

    assert result["verdict_label"] == "corroborated"
    assert result["verdict_confidence"] == 0.8

    # Both the finding and the verdict should now be in the shared store,
    # readable independently of the graph run that produced them.
    cid = store.ensure_claim("Some claim")
    findings = store.get_findings(cid, role="source_finder")
    assert len(findings) == 1
    assert len(findings[0].articles) == 2
    verdict = store.get_verdict(cid)
    assert verdict.label == "corroborated"


def test_end_to_end_pipeline_no_coverage_is_unverifiable():
    store = make_store()
    gdelt = FakeGdeltClient([])
    llm = FakeLLMClient("should not be called")

    result = run_pipeline("An obscure claim", store, gdelt, llm)

    assert result["verdict_label"] == "unverifiable"
