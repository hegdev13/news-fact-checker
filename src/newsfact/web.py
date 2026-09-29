"""FastAPI web layer for the v2 pipeline — the FactGround React UI's backend.

All routes are served under ``/api`` (the Vite dev server proxies those to this
process, see ``client/vite.config.ts``).

Endpoints
    GET  /api/health          server status + mode (demo/live) + store path
    GET  /api/reports         completed reports as lightweight feed cards
    GET  /api/reports/{cid}   full detail for one claim (verdict, bias, evidence, audit)
    POST /api/check           run the pipeline for a claim in the background
    GET  /api/check/{cid}     poll a running check; carries the detail when done
    POST /api/check/demo      run the three bundled sample claims (seeds the feed)

Like the CLI, the server runs in offline *demo* mode when no ANTHROPIC_API_KEY
is set, using the scripted GDELT/Claude fixtures so the whole app works with
zero configuration. Results are cached in the usual SQLite store (shared with
``python -m newsfact.main``), so re-checking the same claim replays the report.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from newsfact.config import load_settings
from newsfact.demo import FakeGdeltClient, FakeLLMClient
from newsfact.graph import run_pipeline
from newsfact.llm import AnthropicLLMClient
from newsfact.memory.store import BlackboardStore, Report, claim_id
from newsfact.observability.events import AuditLogReporter
from newsfact.tools.bias_table import BiasTable
from newsfact.tools.gdelt import GdeltClient

_SAMPLE_CLAIMS = Path(__file__).parent / "resources" / "sample_claims.txt"

# In-process registry of running/complete checks (claim_id -> job dict).
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
# Serialise pipeline runs: the shared SQLite store is quick but per-op connections.
_check_lock = threading.Lock()

app = FastAPI(title="newsfact API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- infrastructure ----------------------------------------------------------


def _clients_and_store() -> tuple[BlackboardStore, Any, Any, BiasTable]:
    settings = load_settings()
    store = BlackboardStore(settings.db_path)
    bias_table = BiasTable.load(settings.bias_table_path)
    if settings.anthropic_api_key:
        gdelt: Any = GdeltClient(settings.gdelt_api_base)
        llm: Any = AnthropicLLMClient(settings.anthropic_api_key, settings.model)
    else:
        gdelt, llm = FakeGdeltClient(), FakeLLMClient()
    return store, gdelt, llm, bias_table


def _open_db() -> BlackboardStore:
    settings = load_settings()
    return BlackboardStore(settings.db_path)


# --- shaping -----------------------------------------------------------------


def _card(store: BlackboardStore, report: Report) -> dict[str, Any]:
    cid = report.claim_id
    bias = store.get_bias_report(cid)
    sf = store.get_findings(cid, role="source_finder")
    opp = store.get_findings(cid, role="opposition")
    sf_articles = sf[0].articles if sf else []
    opp_articles = opp[0].articles if opp else []
    url = next((a.get("url") for a in sf_articles if a.get("url")), None)
    return {
        "claim": store.get_claim_text(cid),
        "claim_id": cid,
        "headline": report.headline,
        "verdict_label": report.verdict_label,
        "verdict_confidence": report.verdict_confidence,
        "created_at": report.created_at,
        "bias_spread": bias.spread if bias else {},
        "source_finder_count": len(sf_articles),
        "opposition_count": len(opp_articles),
        "url": url,
    }


def _detail(store: BlackboardStore, cid: str) -> dict[str, Any] | None:
    report = store.get_report(cid)
    if report is None:
        return None
    verdict = store.get_verdict(cid)
    bias = store.get_bias_report(cid)
    by_role = {
        f.role: {"articles": f.articles, "summary": f.summary}
        for f in store.get_findings(cid)
    }
    return {
        "claim": store.get_claim_text(cid),
        "claim_id": cid,
        "report": {
            "headline": report.headline,
            "body_md": report.body_md,
            "verdict_label": report.verdict_label,
            "verdict_confidence": report.verdict_confidence,
        },
        "verdict": None if verdict is None else {
            "label": verdict.label,
            "confidence": verdict.confidence,
            "reasoning": verdict.reasoning,
            "created_at": verdict.created_at,
        },
        "bias_report": None if bias is None else {
            "spread": bias.spread,
            "outlets": bias.outlets,
            "blindspots": bias.blindspots,
            "dominant_side": bias.dominant_side,
        },
        "findings": {
            "source_finder": by_role.get("source_finder", {"articles": [], "summary": ""}),
            "opposition": by_role.get("opposition", {"articles": [], "summary": ""}),
        },
        "audit_log": [
            {"ts": e.ts, "agent": e.agent, "kind": e.kind, "message": e.message, "data": e.data}
            for e in store.get_audit(cid)
        ],
        "created_at": report.created_at,
    }


# --- background jobs ---------------------------------------------------------


def _run_check(claim: str) -> dict[str, Any]:
    store, gdelt, llm, bias_table = _clients_and_store()
    reporter = AuditLogReporter(store)
    store.set_reporter(reporter)
    with _check_lock:
        run_pipeline(claim, store, gdelt, llm, bias_table, reporter)
    cid = claim_id(claim)
    detail = _detail(store, cid)
    assert detail is not None
    return detail


def _spawn_check(claim: str) -> dict[str, Any]:
    cid = claim_id(claim)
    with _jobs_lock:
        _jobs[cid] = {"claim_id": cid, "status": "running", "started_at": time.time(), "claim": claim}

    def work() -> None:
        try:
            error, detail = None, _run_check(claim)
        except Exception as exc:  # noqa: BLE001 - surface as job error, not a crash
            error, detail = str(exc), None
        with _jobs_lock:
            _jobs[cid] = {
                "claim_id": cid,
                "status": "error" if error else "done",
                "done_at": time.time(),
                "error": error,
                "detail": detail,
            }

    threading.Thread(target=work, daemon=True).start()
    return {"claim_id": cid, "status": "running"}


# --- routes ------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = load_settings()
    return {
        "status": "ok",
        "mode": "live" if settings.anthropic_api_key else "demo",
        "db_path": settings.db_path,
    }


@app.get("/api/reports")
def list_reports() -> list[dict[str, Any]]:
    store = _open_db()
    return [_card(store, r) for r in store.list_reports(limit=50)]


@app.get("/api/reports/{cid}")
def get_report(cid: str) -> dict[str, Any]:
    store = _open_db()
    detail = _detail(store, cid)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No report for claim {cid}")
    return detail


class CheckRequest(BaseModel):
    claim: str


@app.post("/api/check", status_code=202)
def start_check(req: CheckRequest) -> dict[str, Any]:
    claim = (req.claim or "").strip()
    if not claim:
        raise HTTPException(status_code=422, detail="claim must not be empty")
    return _spawn_check(claim)


@app.get("/api/check/{cid}")
def get_check(cid: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(cid)
    if job is not None:
        return job
    # Not registered in this process (fresh server, or a direct id) — fall back
    # to the store so a completed check is still retrievable.
    store = _open_db()
    detail = _detail(store, cid)
    if detail is not None:
        return {"claim_id": cid, "status": "done", "detail": detail}
    raise HTTPException(status_code=404, detail=f"No running check for {cid}")


@app.post("/api/check/demo")
def run_demo() -> dict[str, Any]:
    """Run the three bundled sample claims through the pipeline (seed the feed)."""
    claims = [
        line.strip()
        for line in _SAMPLE_CLAIMS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    store, gdelt, llm, bias_table = _clients_and_store()
    reporter = AuditLogReporter(store)
    store.set_reporter(reporter)
    ran: list[str] = []
    with _check_lock:
        for claim in claims:
            run_pipeline(claim, store, gdelt, llm, bias_table, reporter)
            ran.append(claim_id(claim))
    return {"claim_ids": ran, "count": len(ran), "claims": claims}


def main() -> None:
    import uvicorn

    port = int(__import__("os").getenv("NEWSFACT_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()