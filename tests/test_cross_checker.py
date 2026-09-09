import json
import tempfile
from pathlib import Path

import pytest

from newsfact.agents.cross_checker import run_cross_checker
from newsfact.memory.store import BlackboardStore, Finding


class FakeLLMClient:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, user):
        return self._response


def make_store() -> BlackboardStore:
    tmpdir = tempfile.mkdtemp()
    return BlackboardStore(Path(tmpdir) / "test.db")


def test_short_circuits_to_unverifiable_when_no_articles():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    # no findings written at all

    verdict = run_cross_checker("Some claim", cid, store, FakeLLMClient("should not be called"))

    assert verdict.label == "unverifiable"
    assert verdict.confidence == 1.0


def test_short_circuits_to_unverifiable_with_single_domain():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    store.write_finding(Finding(
        claim_id=cid,
        role="source_finder",
        articles=[
            {"title": "A", "source_domain": "only.com"},
            {"title": "A2", "source_domain": "only.com"},
        ],
    ))

    verdict = run_cross_checker("Some claim", cid, store, FakeLLMClient("should not be called"))

    assert verdict.label == "unverifiable"


def test_calls_llm_and_parses_corroborated_verdict():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    store.write_finding(Finding(
        claim_id=cid,
        role="source_finder",
        articles=[
            {"title": "A", "source_domain": "a.com"},
            {"title": "B", "source_domain": "b.com"},
        ],
    ))
    llm_response = json.dumps({
        "label": "corroborated",
        "confidence": 0.85,
        "reasoning": "Two independent outlets report the same facts.",
    })

    verdict = run_cross_checker("Some claim", cid, store, FakeLLMClient(llm_response))

    assert verdict.label == "corroborated"
    assert verdict.confidence == 0.85
    stored = store.get_verdict(cid)
    assert stored.label == "corroborated"


def test_falls_back_to_unverifiable_on_unparseable_llm_response():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    store.write_finding(Finding(
        claim_id=cid,
        role="source_finder",
        articles=[
            {"title": "A", "source_domain": "a.com"},
            {"title": "B", "source_domain": "b.com"},
        ],
    ))

    verdict = run_cross_checker("Some claim", cid, store, FakeLLMClient("not json at all"))

    assert verdict.label == "unverifiable"


def test_rejects_invalid_label_from_llm():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    store.write_finding(Finding(
        claim_id=cid,
        role="source_finder",
        articles=[
            {"title": "A", "source_domain": "a.com"},
            {"title": "B", "source_domain": "b.com"},
        ],
    ))
    llm_response = json.dumps({"label": "false", "confidence": 0.9, "reasoning": "nope"})

    verdict = run_cross_checker("Some claim", cid, store, FakeLLMClient(llm_response))

    # "false" is not a valid label -> parse failure -> safe fallback
    assert verdict.label == "unverifiable"
