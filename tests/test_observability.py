import tempfile
from pathlib import Path

from newsfact.memory.store import BlackboardStore, Finding, Verdict
from newsfact.observability.events import (
    AuditLogReporter,
    Event,
    EventKind,
    MultiReporter,
    NullReporter,
)


class Collector:
    def __init__(self):
        self.events: list[Event] = []

    def emit(self, event):
        self.events.append(event)


class Boom:
    def emit(self, event):
        raise RuntimeError("sink is broken")


def make_store(reporter=None):
    return BlackboardStore(Path(tempfile.mkdtemp()) / "t.db", reporter=reporter)


def test_multireporter_isolates_a_failing_sink():
    good = Collector()
    multi = MultiReporter([Boom(), good, Boom()])

    multi.emit(Event(EventKind.NOTE, "orchestrator", "still delivered"))

    assert len(good.events) == 1
    assert good.events[0].message == "still delivered"


def test_store_emits_bb_events_only_when_attributed():
    col = Collector()
    store = make_store(reporter=col)
    cid = store.ensure_claim("c")

    store.write_finding(Finding(cid, "source_finder", [{"source_domain": "a.com"}]))  # no by=
    assert col.events == []

    store.write_finding(Finding(cid, "source_finder", [{"source_domain": "a.com"}]), by="source_finder")
    store.get_findings(cid, role="source_finder", by="cross_checker")

    kinds = [(e.kind, e.agent) for e in col.events]
    assert (EventKind.BB_WRITE, "source_finder") in kinds
    assert (EventKind.BB_READ, "cross_checker") in kinds


def test_audit_log_reporter_persists_every_event_in_order():
    store = make_store()
    reporter = MultiReporter([AuditLogReporter(store), NullReporter()])
    store.set_reporter(reporter)
    cid = store.ensure_claim("claim")

    reporter.emit(Event(EventKind.ITEM_START, "orchestrator", "start", cid))
    store.write_verdict(Verdict(cid, "corroborated", 0.9, "ok"), by="cross_checker")
    reporter.emit(Event(EventKind.ITEM_DONE, "orchestrator", "done", cid))

    trail = store.get_audit(cid)
    assert [e.kind for e in trail] == [EventKind.ITEM_START, EventKind.BB_WRITE, EventKind.ITEM_DONE]
    assert trail[1].agent == "cross_checker"


def test_audit_log_reporter_swallows_store_errors():
    class BrokenStore:
        def append_audit(self, event):
            raise RuntimeError("db locked")

    # observability must never take down the pipeline
    AuditLogReporter(BrokenStore()).emit(Event(EventKind.NOTE, "x", "y"))
