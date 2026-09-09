import tempfile
from pathlib import Path

from newsfact.agents.bias_analyzer import run_bias_analyzer
from newsfact.memory.store import BlackboardStore, Finding
from newsfact.tools.bias_table import BiasTable

TABLE = BiasTable({
    "left1.com": {"name": "Left One", "bias": "left", "factuality": "mostly-factual", "country": "US"},
    "left2.com": {"name": "Left Two", "bias": "center-left", "factuality": "high", "country": "US"},
    "center1.com": {"name": "Center One", "bias": "center", "factuality": "very-high", "country": "US"},
    "right1.com": {"name": "Right One", "bias": "right", "factuality": "low", "country": "US"},
})


def make_store():
    return BlackboardStore(Path(tempfile.mkdtemp()) / "t.db")


def _write(store, cid, role, domains):
    store.write_finding(Finding(claim_id=cid, role=role,
                                articles=[{"title": d, "source_domain": d} for d in domains]))


def test_computes_lcr_spread_across_both_evidence_roles():
    store = make_store()
    cid = store.ensure_claim("c")
    _write(store, cid, "source_finder", ["left1.com", "center1.com"])
    _write(store, cid, "opposition", ["right1.com"])

    report = run_bias_analyzer(cid, store, TABLE)

    assert report.spread == {"left": 1, "center": 1, "right": 1, "unknown": 0}
    assert report.dominant_side == "balanced"
    assert any("Low-factuality" in n for n in report.blindspots)


def test_flags_missing_side_as_blindspot():
    store = make_store()
    cid = store.ensure_claim("c2")
    _write(store, cid, "source_finder", ["left1.com", "left2.com"])

    report = run_bias_analyzer(cid, store, TABLE)

    assert report.spread["right"] == 0
    assert report.dominant_side == "left"
    assert any("Right-of-center blindspot" in n for n in report.blindspots)


def test_unrated_domains_go_to_unknown_bucket():
    store = make_store()
    cid = store.ensure_claim("c3")
    _write(store, cid, "source_finder", ["who.knows", "center1.com"])

    report = run_bias_analyzer(cid, store, TABLE)

    assert report.spread["unknown"] == 1
    assert report.spread["center"] == 1
    # persisted for the Writer to read back
    assert store.get_bias_report(cid).dominant_side == report.dominant_side


def test_bundled_table_loads_and_has_indian_outlets():
    table = BiasTable.load()
    assert len(table) > 20
    assert table.lookup("thehindu.com").country == "IN"
    assert table.lookup("www.foxnews.com").side == "right"  # www. stripped
