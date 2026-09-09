# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Orientation

Read `docs/HANDOFF.md` first — it is the living source of truth for what exists, what doesn't, and why. Then `CHANGELOG.md` (`Unreleased` + latest version) and the newest file in `docs/sessions/`. Per-version status summaries are at repo root (`v1.md`, `v2.md`, `v2.1.md`). The original project brief / prior-art survey is `docs/resource-document.md`.

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

# article-input mode (v2.1): submit a whole article, not a claim
python -m newsfact.main --demo --article                       # bundled sample article
python -m newsfact.main --article path/to/article.txt
python -m newsfact.main --article - --article-url https://outlet.example/story   # article on stdin
python -m newsfact.main --article-text "Full article text..."
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

A news fact-checker: five core agents, plus a v2.1 **Claim Extractor** front-end for article-input mode. Agents **never pass state to each other directly** — they read and write a shared SQLite "blackboard", and every read/write/tool-call is emitted as an event that a live terminal dashboard renders and an append-only `audit_log` table persists. This blackboard-not-pipeline design is the project's core bet; preserve it.

### Orchestration (`src/newsfact/graph.py`, LangGraph)

```
                       (article mode only)
article ─▶ claim_extractor ─▶ primary claim ─┐
                                             ▼
claim ─────────────────────────────▶ START ─┬─▶ source_finder ─┐
                                            └─▶ opposition ─────┴─▶ cross_checker ──(disputed & conf < 0.6 & passes < 1)──▶ deep_research ─┐
                                                                        │  ▲                                                                │
                                                                        │  └────────────────────────────────────────────────────────────────┘
                                                                        ▼ (else)
                                                                   bias_analyzer ──▶ writer ──▶ END
```

Two entry points, both closing infrastructure (store, clients, bias table, reporter) over the node functions rather than threading it through `GraphState`: `run_pipeline(claim, …)` (claim mode) and `run_article_pipeline(article, …, url=None)` (article mode — runs `run_claim_extractor` first, then the same graph on the extracted primary claim). Shared invoke logic is in `_invoke_graph`. `GraphState` carries only plumbing (claim text/id, loop counter) + the final verdict.

### Agents (`src/newsfact/agents/`)

| Agent | LLM? | Reads (blackboard) | Writes |
|---|---|---|---|
| `claim_extractor` | yes | — (raw article + optional URL) | `source_docs` (article mode only; keyed by the extracted primary claim's id) |
| `source_finder` | no | claim | `findings` role=`source_finder` |
| `opposition` | yes | claim | `findings` role=`opposition` (+ `summary` counter-framing) |
| `cross_checker` | yes | both `findings` roles | `verdicts` |
| `bias_analyzer` | no | both `findings` roles, `source_docs` | `bias_reports` |
| `writer` | yes | `verdicts`, both `findings`, `bias_reports`, `source_docs`, `audit_log` | `reports` |

`claim_extractor` also "finds the source": `tools/source_id.py::identify_source()` maps the article to its publishing outlet from an explicit `--article-url`, the first URL in the body, or a byline/`(Reuters)`-style credit matched against the bias-table outlet names. Pure/offline — a URL is parsed for its domain, never fetched. In article mode `bias_analyzer` folds the origin outlet into the L/C/R spread and flags "no independent outlet corroborates this"; `writer` prepends a deterministic **Source of the submitted article** section.

Conventions every agent follows (keep them when adding/editing agents):
- Write only **structured, verified artifacts** to the blackboard — never raw LLM reasoning traces.
- Verdict labels are exactly `corroborated` / `disputed` / `unverifiable` — no binary true/false anywhere, including the Writer's prose. A single source domain is never enough for `corroborated`; `< 2` distinct domains across *both* evidence roles short-circuits Cross-Checker to `unverifiable` with no LLM call.
- Opposition is a **hard-mandated adversary** (per the "Inducing Disagreement" finding in the resource doc): its prompt forbids hedging/balancing/conceding. Its LLM call only produces *search angles* — evidence still comes from GDELT, so a bad angle can't become a fabricated source.
- Take an optional `reporter`, emit `AGENT_START` / `TOOL_CALL` / `NOTE` / `AGENT_DONE`, and pass `by=<role>` on every store read/write so it shows up in the dashboard and audit log.
- Never crash the pipeline: LLM/GDELT failures degrade to a safe fallback (empty finding, `unverifiable`, deterministic report).

### Shared store (`src/newsfact/memory/store.py`)

SQLite, one file. Tables: `claims`, `findings` (PK `claim_id, role`), `verdicts`, `bias_reports`, `reports`, `audit_log` (append-only, autoincrement), `source_docs` (article-input mode; PK `claim_id`). `reports` doubles as the "already checked this claim" cache — `main.py` calls `get_report()` before running the graph in **claim mode only** (article mode can't pre-check: the `claim_id` isn't known until extraction). `merge_finding()` unions+dedupes (used by the deep-research loop instead of overwrite). Schema changes need an additive `ALTER TABLE` in `_migrate()` for existing DB files (new tables just use `CREATE TABLE IF NOT EXISTS`). The store holds an optional `Reporter` and emits `bb_read`/`bb_write` only when a call is attributed via `by=`.

### Observability (`src/newsfact/observability/`)

`events.py` — `Event` + `EventKind` (string constants, not an Enum, so they serialize into `audit_log` cleanly); `Reporter` protocol; `NullReporter` (default everywhere), `MultiReporter` (fan-out; a failing sink never breaks others or the run), `AuditLogReporter` (persists to the store). `console.py` — `ConsoleReporter`, a `rich.Live` dashboard (item / agents+status / blackboard contents / event stream), falls back to flat line printing when stdout isn't a TTY or `--plain`. `main.py` builds one `MultiReporter([ConsoleReporter, AuditLogReporter])`, sets it on the store, and `run_pipeline` falls back to `store.reporter` so observability is configured once.

### Offline demo (`src/newsfact/demo/fixtures.py`)

`FakeGdeltClient` / `FakeLLMClient` are **scripted, not smart**: they recognise keywords from the three claims in `resources/sample_claims.txt` (and the bundled `resources/sample_article.txt`) to exercise the corroborated / disputed-with-loop / unverifiable paths, and fall back to a generic corroborated result otherwise. `FakeLLMClient` branches on which agent's system prompt it was handed (Claim Extractor / Opposition / Cross-Checker / Writer). This is a visibility harness, not a model simulator. `main.py` selects the fakes when `--demo` is passed or `ANTHROPIC_API_KEY` is unset. **If you add an agent that needs a new external call, add a fake for it here** so `--demo` keeps working keyless.

### External clients / data

`tools/gdelt.py` — GDELT DOC 2.0 (no key). Its `_parse_response` assumptions have **never been checked against a live response** — smoke-test this first in any session that has real keys. `tools/bias_table.py` + `resources/outlet_bias.json` — curated 42-outlet bias/factuality table; the Indian-outlet ratings are hand-guessed placeholders (no standardized rater exists). `NEWSFACT_BIAS_TABLE` overrides the file. `llm.py` — shared `LLMClient` protocol + `AnthropicLLMClient` (also re-exported from `agents/cross_checker.py` for back-compat). Config is centralized in `config.py`; no other module reads `os.environ`.

## Constraints for this project

- API-key env vars are intentionally kept as **stubs** — do not wire real credentials unless asked.
- v2 is **terminal-only**. The web UI is v3 and is deliberately not started.
- Keep the whole pipeline runnable via `--demo` with no keys and no network.
- When you finish/start an agent or make a design decision: update `docs/HANDOFF.md`, `CHANGELOG.md` (`Unreleased`), and add a dated `docs/sessions/` file for real decisions.
