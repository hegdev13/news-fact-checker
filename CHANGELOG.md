# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added — v3: web UI
- **FastAPI web layer** (`web.py`) — routes under `/api`: health, completed-report
  feed (`GET /api/reports`), full per-claim detail (`GET /api/reports/{cid}`),
  async single-claim checks (`POST /api/check` + `GET /api/check/{cid}` polling,
  pipeline runs in a background thread), and `POST /api/check/demo` to seed the
  feed with the bundled sample claims. Runs offline in demo mode with no API key.
  New `newsfact-server` console script and `web` extra (`fastapi`, `uvicorn`).
- **FactGround React UI** (`client/`, new) — Vite + React 19 + TypeScript + Tailwind
  v4 dashboard: story feed from real reports, L/C/R bias meter, claim-level
  verification, per-outlet source cards, blindspot warnings, and a Pipeline Audit
  Trail tab rendered from `audit_log`. Search submits the claim to the backend and
  polls the job; falls back to a local sample feed when the API is unreachable.
- `BlackboardStore.list_reports()` — newest-first completed-report feed for the UI.
- Docs: README quick-start for the web stack; HANDOFF updated.

## [0.2.0] — 2026-09-09 — "v2: all five agents + live terminal dashboard"

### Added
- **Opposition agent** (`agents/opposition.py`) — hard-mandated adversary: LLM
  generates disconfirming search angles, runs them against GDELT, writes
  counter-evidence + a one-line counter-framing to the blackboard as a
  `role="opposition"` finding.
- **Bias/Blindspot Analyzer agent** (`agents/bias_analyzer.py`) — maps every
  retrieved outlet to a bias/factuality rating, computes the L/C/R spread, and
  flags blindspots (missing side, low-factuality sources, heavy skew). No LLM.
- **Writer agent** (`agents/writer.py`) — merges verdict + both evidence sets +
  bias report into a structured report; appends a deterministic audit trail
  built from the `audit_log` table (not the LLM). Persists a `Report` that also
  serves as the "already checked" cache entry.
- **Observability layer** (`observability/`) — an `Event` model, a `Reporter`
  protocol with `Null`/`Multi`/`AuditLog` sinks, and `ConsoleReporter`: a
  `rich.Live` dashboard showing the 5 agents, the shared blackboard, and a
  streaming event log per news item.
- **`audit_log` table** — append-only trail of every agent start/finish, tool
  call, and blackboard read/write, keyed by claim (the resource doc's audit-log
  deliverable).
- **Offline demo** (`demo/fixtures.py`) — `FakeGdeltClient` / `FakeLLMClient`
  so the full pipeline + dashboard run with no API keys: `python -m
  newsfact.main --demo`.
- `tools/bias_table.py` + `resources/outlet_bias.json` — curated 42-outlet
  bias/factuality table (US/UK/global + hand-curated Indian outlets).
- `resources/sample_claims.txt` — three sample news items exercising the
  corroborated / disputed-with-loop / unverifiable paths.
- `llm.py` — shared `LLMClient` protocol + `AnthropicLLMClient` (was private to
  Cross-Checker; still re-exported from there for compatibility).
- CLI: batch input (multiple claims or `--file`), `--demo`, `--plain`,
  `--no-cache`, `--keep-db`, `--json`; end-of-run report panels + recap table.
- Tests: `test_opposition.py`, `test_bias_analyzer.py`, `test_writer.py`,
  `test_observability.py`, `test_store_v2.py`, `test_graph_v2.py` (44 total,
  still fully offline).

### Changed
- **Graph** (`graph.py`) — was linear Source-Finder → Cross-Checker; now
  parallel Source-Finder ∥ Opposition → Cross-Checker → (bounded deep-research
  loop on low-confidence `disputed`) → Bias/Blindspot Analyzer → Writer.
- **Cross-Checker** now adjudicates *both* evidence roles (Source-Finder and
  Opposition) rather than only Source-Finder; the <2-distinct-domain
  short-circuit now counts domains across both sets.
- **`BlackboardStore`** — added `summary` column to `findings` (+ in-place
  migration for older DBs), `bias_reports` / `reports` / `audit_log` tables,
  `merge_finding()` for the loop, `append_audit()` / `get_audit()`, an optional
  `reporter` that emits `bb_read` / `bb_write` events when a read/write is
  attributed to an agent via `by=`.
- `run_pipeline()` signature gains optional `bias_table` and `reporter`
  (both default sensibly; falls back to the store's reporter). v1 call sites
  and tests unchanged.
- Default model bumped note: `NEWSFACT_MODEL` still `claude-sonnet-4-5`.
- `pyproject.toml` — version `0.2.0`, added `rich`, package-data for
  `resources/*`.

### Notes
- Still no live GDELT / Anthropic call made this session (env kept stubbed by
  request). First live-key task is unchanged — see `docs/HANDOFF.md`.
- Web UI is explicitly deferred to v3; v2 is terminal-only.

## [0.1.0]

### Added
- Initial project scaffold: `pyproject.toml`, `.gitignore`, `.env.example`.
- `docs/resource-document.md` — copy of the original project brief/research doc.
- `docs/ARCHITECTURE.md` — design decisions for v1 (tech stack, blackboard pattern, orchestration).
- `docs/HANDOFF.md` — living state doc for cross-session/cross-agent handoff.
- `src/newsfact/memory/store.py` — SQLite-backed shared blackboard store (claims, findings, verdicts, cache lookups).
- `src/newsfact/tools/gdelt.py` — GDELT DOC 2.0 API client (no key required).
- `src/newsfact/agents/source_finder.py` — Source-Finder agent: queries GDELT for a claim, writes findings to shared store.
- `src/newsfact/agents/cross_checker.py` — Cross-Checker agent: reads findings, uses Claude to assess agreement/conflict, writes confidence-scored verdict.
- `src/newsfact/graph.py` — LangGraph wiring: Source-Finder → Cross-Checker.
- `src/newsfact/main.py` — CLI entrypoint with claim-level caching.
- Test suite (`tests/`) covering store, GDELT client, and graph — all mocked, runs offline.

### Notes
- v1 deliberately implements only 2 of the 5 agents in the full design
  (Source-Finder, Cross-Checker). Opposition, Bias/Blindspot Analyzer, and
  Writer are scoped in `docs/HANDOFF.md` but not built yet.
- Indian-outlet bias table, story/event clustering, and the formal audit log
  are gaps carried over from the resource document and are still open.
