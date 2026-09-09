import json
import tempfile
from pathlib import Path

from newsfact.agents.opposition import run_opposition
from newsfact.memory.store import BlackboardStore
from newsfact.tools.gdelt import Article, GdeltError


class FakeGdelt:
    def __init__(self, by_query=None, default=None, raise_on=None):
        self._by_query = by_query or {}
        self._default = default or []
        self._raise_on = raise_on or set()
        self.queries: list[str] = []

    def search(self, query, max_records=25):
        self.queries.append(query)
        if query in self._raise_on:
            raise GdeltError("boom")
        return self._by_query.get(query, self._default)


class FakeLLM:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        assert "Opposition agent" in system  # it is the adversary's prompt
        return self._response


def make_store():
    return BlackboardStore(Path(tempfile.mkdtemp()) / "t.db")


def test_opposition_uses_llm_angles_and_writes_counter_evidence():
    store = make_store()
    cid = store.ensure_claim("Claim X is true")
    llm = FakeLLM(json.dumps({
        "queries": ["claim x debunked", "claim x criticism"],
        "counter_framing": "It is overstated.",
    }))
    gdelt = FakeGdelt(
        by_query={
            "claim x debunked": [Article("Debunk", "a.com", "a.com", "d")],
            "claim x criticism": [Article("Critique", "b.com", "b.com", "d")],
        }
    )

    finding = run_opposition("Claim X is true", cid, store, gdelt, llm)

    assert finding.role == "opposition"
    assert finding.summary == "It is overstated."
    assert {a["source_domain"] for a in finding.articles} == {"a.com", "b.com"}
    assert llm.calls == 1
    assert gdelt.queries == ["claim x debunked", "claim x criticism"]
    # persisted to the shared store, readable by any other agent
    assert store.get_findings(cid, role="opposition")[0].summary == "It is overstated."


def test_opposition_falls_back_to_default_angles_on_bad_llm_json():
    store = make_store()
    cid = store.ensure_claim("Some claim here")
    llm = FakeLLM("not json")
    gdelt = FakeGdelt(default=[Article("t", "x.com", "x.com", "d")])

    finding = run_opposition("Some claim here about things", cid, store, gdelt, llm)

    # default angles are derived from the claim and still adversarial
    assert any("debunked" in q for q in gdelt.queries)
    assert finding.summary  # non-empty counter-framing fallback


def test_opposition_dedupes_and_survives_partial_gdelt_failure():
    store = make_store()
    cid = store.ensure_claim("Claim Y")
    llm = FakeLLM(json.dumps({"queries": ["q1", "q2", "q3"], "counter_framing": "cf"}))
    dupe = Article("Same", "s.com", "s.com", "d", tone=0.0)
    gdelt = FakeGdelt(
        by_query={"q1": [dupe], "q2": [dupe]},
        raise_on={"q3"},
    )

    finding = run_opposition("Claim Y", cid, store, gdelt, llm)

    assert len(finding.articles) == 1  # dupe collapsed, q3 failure swallowed
