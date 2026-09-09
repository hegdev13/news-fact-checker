import tempfile
from pathlib import Path

from newsfact.agents.source_finder import run_source_finder
from newsfact.memory.store import BlackboardStore
from newsfact.tools.gdelt import Article, GdeltError


class FakeGdeltClient:
    def __init__(self, articles=None, raise_error=False):
        self._articles = articles or []
        self._raise_error = raise_error

    def search(self, query, max_records=25):
        if self._raise_error:
            raise GdeltError("boom")
        return self._articles


def make_store() -> BlackboardStore:
    tmpdir = tempfile.mkdtemp()
    return BlackboardStore(Path(tmpdir) / "test.db")


def test_source_finder_writes_findings():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    articles = [Article(title="T", url="u", source_domain="d.com", seen_date="20260101")]
    client = FakeGdeltClient(articles=articles)

    finding = run_source_finder("Some claim", cid, store, client)

    assert finding.articles[0]["title"] == "T"
    stored = store.get_findings(cid, role="source_finder")
    assert len(stored) == 1


def test_source_finder_handles_gdelt_error_gracefully():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    client = FakeGdeltClient(raise_error=True)

    finding = run_source_finder("Some claim", cid, store, client)

    assert finding.articles == []
    stored = store.get_findings(cid, role="source_finder")
    assert stored[0].articles == []
