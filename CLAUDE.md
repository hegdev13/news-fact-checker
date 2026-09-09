# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Orientation

Read `docs/HANDOFF.md` first — it is the living source of truth for what exists, what doesn't, and why. Then `CHANGELOG.md` (`Unreleased` + latest version) and the newest file in `docs/sessions/`. Per-version status summaries are at repo root (`v1.md`, `v2.md`). The original project brief / prior-art survey is `docs/resource-document.md`.

The repo root is `news-fact-checker/` (its own git repo); the parent `Agentic-AI-Project/` only holds the brief.

## Commands

Setup (Python 3.11+ required — the repo's `.venv` is 3.11):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the pipeline:

```bash
python -m newsfact.main --demo            # full run, offline fixtures, live dashboard, no keys needed
python -m newsfact.main --demo --plain    # flat event trace instead of the live region (pipe-friendly)
python -m newsfact.main --demo --json     # + machine-readable summary at the end
python -m newsfact.main "claim one" "claim two"     # real run (needs ANTHROPIC_API_KEY) or auto-demo if unset
python -m newsfact.main --file path/to/claims.txt   # one claim per line, # comments allowed
```

Tests (all offline — GDELT/Anthropic mocked or faked, no keys):

```bash
pytest                                   # whole suite
pytest tests/test_graph_v2.py            # one file
pytest tests/test_graph_v2.py::test_deep_research_loop_fires_on_low_confidence_disputed   # one test
pytest -k opposition                     # by keyword
```

There is no linter/formatter/type-checker configured. `pytest-mock` is available but tests mostly use hand-written fakes.

## Architecture

A five-agent news fact-checker. Agents **never pass state to each other directly** — they read and write a shared SQLite "blackboard", and every read/write/tool-call is emitted as an event that a live terminal dashboard renders and an append-only `audit_log` table persists. This blackboard-not-pipeline design is the project's core bet; preserve it.

### Orchestration (`src/newsfact/graph.py`, LangGraph)

```
START ─┬─▶ source_finder ─┐
       └─▶ opposition ─────┴─▶ cross_checker ──(disputed & confidence < 0.6 & passes < 1)──▶ deep_research ─┐
                                    │  ▲                                                                     │
                                    │  └─────────────────────────────────────────────────────────────────────┘
                                    ▼ (else)
                               bias_analyzer ──▶ writer ──▶ END
```

`run_pipeline()` is the entry point. Infrastructure (store, clients, bias table, reporter) is closed over by node functions, not threaded through `GraphState`; `GraphState` carries only plumbing (claim text/id, loop counter) + the final verdict.

### Agents (`src/newsfact/agents/`)

| Agent | LLM? | Reads (blackboard) | Writes |
|---|---|---|---|
| `source_finder` | no | claim | `findings` role=`source_finder` |
| `opposition` | yes | claim | `findings` role=`opposition` (+ `summary` counter-framing) |
| `cross_checker` | yes | both `findings` roles | `verdicts` |
| `bias_analyzer` | no | both `findings` roles | `bias_reports` |
| `writer` | yes | `verdicts`, both `findings`, `bias_reports`, `audit_log` | `reports` |

Conventions every agent follows (keep them when adding/editing agents):
- Write only **structured, verified artifacts** to the blackboard — never raw LLM reasoning traces.
- Verdict labels are exactly `corroborated` / `disputed` / `unverifiable` — no binary true/false anywhere, including the Writer's prose. A single source domain is never enough for `corroborated`; `< 2` distinct domains across *both* evidence roles short-circuits Cross-Checker to `unverifiable` with no LLM call.
- Opposition is a **hard-mandated adversary** (per the "Inducing Disagreement" finding in the resource doc): its prompt forbids hedging/balancing/conceding. Its LLM call only produces *search angles* — evidence still comes from GDELT, so a bad angle can't become a fabricated source.
- Take an optional `reporter`, emit `AGENT_START` / `TOOL_CALL` / `NOTE` / `AGENT_DONE`, and pass `by=<role>` on every store read/write so it shows up in the dashboard and audit log.
- Never crash the pipeline: LLM/GDELT failures degrade to a safe fallback (empty finding, `unverifiable`, deterministic report).

### Shared store (`src/newsfact/memory/store.py`)

SQLite, one file. Tables: `claims`, `findings` (PK `claim_id, role`), `verdicts`, `bias_reports`, `reports`, `audit_log` (append-only, autoincrement). `reports` doubles as the "already checked this claim" cache — `main.py` calls `get_report()` before running the graph. `merge_finding()` unions+dedupes (used by the deep-research loop instead of overwrite). Schema changes need an additive `ALTER TABLE` in `_migrate()` for existing DB files. The store holds an optional `Reporter` and emits `bb_read`/`bb_write` only when a call is attributed via `by=`.

### Observability (`src/newsfact/observability/`)

`events.py` — `Event` + `EventKind` (string constants, not an Enum, so they serialize into `audit_log` cleanly); `Reporter` protocol; `NullReporter` (default everywhere), `MultiReporter` (fan-out; a failing sink never breaks others or the run), `AuditLogReporter` (persists to the store). `console.py` — `ConsoleReporter`, a `rich.Live` dashboard (item / agents+status / blackboard contents / event stream), falls back to flat line printing when stdout isn't a TTY or `--plain`. `main.py` builds one `MultiReporter([ConsoleReporter, AuditLogReporter])`, sets it on the store, and `run_pipeline` falls back to `store.reporter` so observability is configured once.

### Offline demo (`src/newsfact/demo/fixtures.py`)

`FakeGdeltClient` / `FakeLLMClient` are **scripted, not smart**: they recognise keywords from the three claims in `resources/sample_claims.txt` to exercise the corroborated / disputed-with-loop / unverifiable paths, and fall back to a generic corroborated result otherwise. `FakeLLMClient` branches on which agent's system prompt it was handed. This is a visibility harness, not a model simulator. `main.py` selects the fakes when `--demo` is passed or `ANTHROPIC_API_KEY` is unset. **If you add an agent that needs a new external call, add a fake for it here** so `--demo` keeps working keyless.

### External clients / data

`tools/gdelt.py` — GDELT DOC 2.0 (no key). Its `_parse_response` assumptions have **never been checked against a live response** — smoke-test this first in any session that has real keys. `tools/bias_table.py` + `resources/outlet_bias.json` — curated 42-outlet bias/factuality table; the Indian-outlet ratings are hand-guessed placeholders (no standardized rater exists). `NEWSFACT_BIAS_TABLE` overrides the file. `llm.py` — shared `LLMClient` protocol + `AnthropicLLMClient` (also re-exported from `agents/cross_checker.py` for back-compat). Config is centralized in `config.py`; no other module reads `os.environ`.

## Constraints for this project

- API-key env vars are intentionally kept as **stubs** — do not wire real credentials unless asked.
- v2 is **terminal-only**. The web UI is v3 and is deliberately not started.
- Keep the whole pipeline runnable via `--demo` with no keys and no network.
- When you finish/start an agent or make a design decision: update `docs/HANDOFF.md`, `CHANGELOG.md` (`Unreleased`), and add a dated `docs/sessions/` file for real decisions.
