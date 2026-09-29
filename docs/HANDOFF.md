# Handoff / Current State

_Last updated: 2026-09-29, v3 session (web UI: FactGround + FastAPI layer)._

Read this first, before `CHANGELOG.md` or the session logs, if you're picking
this project up fresh (human or agent).

## What exists right now (v3)

The full v2 pipeline plus a browser UI on top:

All five agents from the design, orchestrated with LangGraph, communicating
only through the shared SQLite blackboard:

```
START ─┬─▶ source_finder ─┐
       └─▶ opposition ─────┴─▶ cross_checker ──(disputed & confidence < 0.6
                                    │  ▲          & passes < 1)──▶ deep_research ─┐
                                    │  └─────────────────────────────────────────┘
                                    ▼ (else)
                               bias_analyzer ──▶ writer ──▶ END
```

- **Source-Finder** — neutral GDELT search → `findings` row, `role=source_finder`.
- **Opposition** — LLM makes disconfirming search angles, runs them → `findings`
  row, `role=opposition`, with a `summary` counter-framing.
- **Cross-Checker** — reads both roles, LLM adjudicates → `verdicts` row
  (`corroborated`/`disputed`/`unverifiable`; <2 distinct domains across *both*
  sets short-circuits to `unverifiable` with no LLM call).
- **deep_research** — only on low-confidence `disputed`, max 1 pass: re-runs
  Source-Finder + Opposition with broadened queries, `merge_finding`s the
  results, loops back to Cross-Checker.
- **Bias/Blindspot Analyzer** — maps every retrieved outlet via
  `tools/bias_table.py` → `bias_reports` row (L/C/R spread, blindspot notes,
  dominant side). No LLM.
- **Writer** — reads verdict + both findings + bias report, LLM composes the
  report, deterministic audit-trail section appended from `audit_log` →
  `reports` row (also the "already checked" cache).

- **Observability**: every agent start/finish, tool call, and blackboard
  read/write is an `Event` (`observability/events.py`). `main.py` fans events to a
  `ConsoleReporter` (live `rich` dashboard) and an `AuditLogReporter` (→
  `audit_log` table). The store emits `bb_read`/`bb_write` when a call is
  attributed with `by=<agent>`.
- **Web API** (`web.py`) — FastAPI layer, routes under `/api`: health, the
  completed-report feed, per-claim detail, an async `POST /api/check` (pipeline
  runs in a background thread, poll via `GET /api/check/{cid}`), and a
  `POST /api/check/demo` that seeds the feed with the three sample claims.
  Run it with `newsfact-server` or `uvicorn newsfact.web:app`.
- **FactGround UI** (`client/`) — Vite + React + TypeScript + Tailwind v4
  dashboard. Story feed built from real reports (verdict → credibility/score,
  L/C/R bias meter from `bias_reports`, blindspot warnings, per-outlet source
  cards, claim-level verification from verdict + opposition framing, and a
  "Pipeline Audit Trail" tab rendered from `audit_log`). Searching runs the
  real pipeline through the async job flow with polling. If the API is
  unreachable it falls back to a local sample feed so the UI still renders.

**Runs offline**: `python -m newsfact.main --demo` uses `demo/fixtures.py`
(scripted GDELT + Claude) — full pipeline, full dashboard, no keys, no network.
Three bundled sample claims hit all three verdict paths. With `ANTHROPIC_API_KEY`
set it auto-switches to the real clients.

**Still no live API call has been made** (env kept stubbed by request). The code
is written against the real GDELT and Anthropic APIs but only exercised via
mocks/fixtures. **First thing a session with keys should do:** run one real
claim (`python -m newsfact.main "<claim>"`) and sanity-check the GDELT
response-shape assumptions in `tools/gdelt.py::_parse_response` before trusting
anything downstream.

## What's NOT built yet (in priority order)

1. **Indian-outlet bias table is a stub.** `resources/outlet_bias.json` has ~42
   outlets with hand-guessed ratings for the Indian ones (no standardized rater
   exists — resource doc Gap #1). Needs a real research pass before the bias
   output is trustworthy. Format is stable; just needs better data (or point
   `NEWSFACT_BIAS_TABLE` at your own file).
2. **Query-shaping LLM call for Source-Finder.** It currently searches the raw
   claim string. A cheap LLM call to turn the claim into a good GDELT query
   would materially improve recall. Opposition already does this for its side.
3. **Verdict calibration.** Cross-Checker's confidence is one uncalibrated LLM
   float. Resource doc names LIAR/FEVER/AVeriTeC for evaluation if this needs to
   be defensible.
4. **Deep-research loop is minimal.** One pass, query broadened by appending
   keywords. Could be smarter (target the specific point of conflict
   Cross-Checker identified) and allow >1 pass with better stop conditions.
5. **GDELT client has no rate limiting / backoff.** Fine for CLI batch use;
   revisit before any high-volume mode.
6. **Story/event clustering** — still not needed (claim-at-a-time / small batch,
   not a "what's trending" feed).
7. ~~**Web UI — v3, deliberately not started.**~~ **Built as of 2026-09-29**:
   FactGround dashboard (`client/`) + FastAPI layer (`web.py`). Next UI gaps:
   streaming progress (SSE/WebSocket) for long checks instead of polling, a
   rendered-markdown view of the Writer report (`body_md` is returned but not
   yet displayed), and multi-claim batch submission.

## Known rough edges

- `tools/gdelt.py::_parse_response` assumptions are still unverified against a
  real GDELT response (see above).
- The demo `FakeLLMClient` is scripted by keyword, not smart — it recognises the
  three bundled sample claims and falls back to a generic corroborated result
  for anything else. It exists to make the pipeline *visible*, not to simulate
  real model behaviour.
- `ConsoleReporter` falls back to plain line printing when stdout isn't a TTY or
  `--plain` is passed; the live region is only exercised interactively.
- `NEWSFACT_MODEL` defaults to `claude-sonnet-4-5` in `config.py` — bump if a
  newer default is preferred by the time you read this.

## Conventions to keep following

- Agents write only *structured, verified* artifacts to the blackboard — never
  raw LLM reasoning traces. Keep this when adding/altering agents.
- Verdict labels stay `corroborated` / `disputed` / `unverifiable`. No binary
  true/false anywhere, including the Writer's prose.
- Any new agent takes an optional `reporter` and emits `AGENT_START` /
  `TOOL_CALL` / `AGENT_DONE` (plus `NOTE`s), and passes `by=<role>` on every
  store read/write so it shows up in the dashboard and audit log.
- Keep the pipeline runnable with `--demo` and no keys. If you add an agent that
  needs a new external call, add a fake for it in `demo/fixtures.py`.
- Update this file's "What exists" / "What's NOT built yet" when you finish or
  start an agent. Update `CHANGELOG.md` `Unreleased` as you go. Add a dated
  `docs/sessions/` file for real design decisions.
