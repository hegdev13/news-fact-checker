import sqlite3
import tempfile
import time
from pathlib import Path

from newsfact.memory.store import (
    BiasReport,
    BlackboardStore,
    Finding,
    Report,
    Verdict,
)


def make_store():
    return BlackboardStore(Path(tempfile.mkdtemp()) / "t.db")


def test_merge_finding_unions_and_dedupes_on_url():
    store = make_store()
    cid = store.ensure_claim("c")
    store.write_finding(Finding(cid, "source_finder", [
        {"title": "A", "url": "http://x/a", "source_domain": "x"},
    ]))
    merged = store.merge_finding(Finding(cid, "source_finder", [
        {"title": "A", "url": "http://x/a", "source_domain": "x"},   # dupe
        {"title": "B", "url": "http://x/b", "source_domain": "x"},   # new
    ]))
    assert len(merged.articles) == 2
    assert store.get_findings(cid, role="source_finder")[0].articles[1]["title"] == "B"


def test_finding_summary_roundtrips():
    store = make_store()
    cid = store.ensure_claim("c")
    store.write_finding(Finding(cid, "opposition", [], summary="the counter case"))
    assert store.get_findings(cid, role="opposition")[0].summary == "the counter case"


def test_bias_report_and_report_roundtrip_and_cache():
    store = make_store()
    cid = store.ensure_claim("c")
    assert store.get_report(cid) is None  # nothing cached yet

    store.write_bias_report(BiasReport(cid, {"left": 1, "center": 2, "right": 0, "unknown": 1},
                                       [{"domain": "a"}], ["note"], "center"))
    store.write_report(Report(cid, "Headline", "corroborated", 0.8, "**Verdict**\nok"))

    assert store.get_bias_report(cid).spread["center"] == 2
    cached = store.get_report(cid)
    assert cached.verdict_label == "corroborated"
    assert cached.headline == "Headline"


def test_audit_log_is_append_only_and_scoped_by_claim():
    from newsfact.observability.events import Event, EventKind

    store = make_store()
    a = store.ensure_claim("claim A")
    b = store.ensure_claim("claim B")
    store.append_audit(Event(EventKind.NOTE, "x", "a1", a))
    store.append_audit(Event(EventKind.NOTE, "x", "b1", b))
    store.append_audit(Event(EventKind.NOTE, "x", "a2", a))

    assert [e.message for e in store.get_audit(a)] == ["a1", "a2"]
    assert [e.message for e in store.get_audit(b)] == ["b1"]


def test_migration_adds_summary_column_to_legacy_findings_table():
    path = Path(tempfile.mkdtemp()) / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE claims (id TEXT PRIMARY KEY, text TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE findings (
            claim_id TEXT NOT NULL, role TEXT NOT NULL, articles_json TEXT NOT NULL,
            created_at REAL NOT NULL, PRIMARY KEY (claim_id, role)
        );
        """
    )
    conn.execute("INSERT INTO claims VALUES ('cid', 'legacy claim', ?)", (time.time(),))
    conn.execute("INSERT INTO findings VALUES ('cid', 'source_finder', '[]', ?)", (time.time(),))
    conn.commit()
    conn.close()

    store = BlackboardStore(path)  # opening it should migrate in place

    findings = store.get_findings("cid", role="source_finder")
    assert findings[0].summary == ""
    store.write_finding(Finding("cid", "opposition", [], summary="new col works"))
    assert store.get_findings("cid", role="opposition")[0].summary == "new col works"
