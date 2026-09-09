import json
import tempfile
from pathlib import Path

from newsfact.agents.writer import run_writer
from newsfact.memory.store import (
    BiasReport,
    BlackboardStore,
    Finding,
    Verdict,
)
from newsfact.observability.events import AuditLogReporter


class FakeLLM:
    def __init__(self, response):
        self._response = response

    def complete(self, system, user):
        assert "Writer agent" in system
        return self._response


def seeded_store():
    store = BlackboardStore(Path(tempfile.mkdtemp()) / "t.db")
    store.set_reporter(AuditLogReporter(store))  # so the deterministic audit trail has rows
    cid = store.ensure_claim("Claim under test")
    store.write_finding(Finding(cid, "source_finder", [{"title": "S1", "source_domain": "a.com"}]), by="source_finder")
    store.write_finding(Finding(cid, "opposition", [{"title": "O1", "source_domain": "b.com"}], summary="counter view"), by="opposition")
    store.write_verdict(Verdict(cid, "disputed", 0.55, "outlets conflict"), by="cross_checker")
    store.write_bias_report(BiasReport(cid, {"left": 1, "center": 0, "right": 1, "unknown": 0},
                                       [{"domain": "a.com"}], ["Left/right split"], "balanced"))
    return store, cid


def test_writer_persists_report_with_verdict_and_audit_trail():
    store, cid = seeded_store()
    llm = FakeLLM(json.dumps({"headline": "Outlets disagree on Claim", "body_md": "**Verdict**\nDisputed."}))

    report = run_writer("Claim under test", cid, store, llm)

    assert report.headline == "Outlets disagree on Claim"
    assert report.verdict_label == "disputed"
    assert report.verdict_confidence == 0.55
    assert "Audit trail" in report.body_md  # deterministic trail appended, not from the LLM
    assert store.get_report(cid).headline == report.headline


def test_writer_uses_deterministic_fallback_when_llm_output_unusable():
    store, cid = seeded_store()
    report = run_writer("Claim under test", cid, store, FakeLLM("garbage not json"))

    assert report.verdict_label == "disputed"
    assert "disputed" in report.body_md.lower()
    assert "counter view" in report.body_md  # opposition summary carried into the fallback


def test_writer_never_emits_binary_true_false_label():
    store, cid = seeded_store()
    report = run_writer("Claim under test", cid, store,
                        FakeLLM(json.dumps({"headline": "h", "body_md": "b"})))
    assert report.verdict_label in {"corroborated", "disputed", "unverifiable"}
