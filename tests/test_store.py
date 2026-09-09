import tempfile
from pathlib import Path

from newsfact.memory.store import BlackboardStore, Finding, Verdict, claim_id


def make_store() -> BlackboardStore:
    tmpdir = tempfile.mkdtemp()
    return BlackboardStore(Path(tmpdir) / "test.db")


def test_claim_id_is_stable_and_case_insensitive():
    a = claim_id("The sky is blue")
    b = claim_id("  the SKY is   blue  ")
    assert a == b


def test_ensure_claim_is_idempotent():
    store = make_store()
    id1 = store.ensure_claim("Some claim")
    id2 = store.ensure_claim("Some claim")
    assert id1 == id2


def test_write_and_get_findings_roundtrip():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    finding = Finding(claim_id=cid, role="source_finder", articles=[{"title": "A"}])
    store.write_finding(finding)

    results = store.get_findings(cid, role="source_finder")
    assert len(results) == 1
    assert results[0].articles == [{"title": "A"}]


def test_get_findings_empty_when_none_written():
    store = make_store()
    cid = store.ensure_claim("Untouched claim")
    assert store.get_findings(cid) == []


def test_write_finding_upserts_on_same_role():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    store.write_finding(Finding(claim_id=cid, role="source_finder", articles=[{"title": "A"}]))
    store.write_finding(Finding(claim_id=cid, role="source_finder", articles=[{"title": "B"}]))

    results = store.get_findings(cid, role="source_finder")
    assert len(results) == 1
    assert results[0].articles == [{"title": "B"}]


def test_write_and_get_verdict_roundtrip():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    verdict = Verdict(claim_id=cid, label="corroborated", confidence=0.9, reasoning="Two outlets agree")
    store.write_verdict(verdict)

    fetched = store.get_verdict(cid)
    assert fetched is not None
    assert fetched.label == "corroborated"
    assert fetched.confidence == 0.9


def test_get_verdict_none_when_missing():
    store = make_store()
    cid = store.ensure_claim("Some claim")
    assert store.get_verdict(cid) is None
