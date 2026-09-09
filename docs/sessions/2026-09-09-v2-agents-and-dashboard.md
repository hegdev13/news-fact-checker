# 2026-09-09 — v2: all five agents + live terminal dashboard

## What changed

Went from the v1 2-agent slice to the full five-agent design, plus an
observability layer that streams the whole run to the terminal.

- Added **Opposition** (hard-mandated adversary; LLM makes disconfirming search
  angles → GDELT → counter-evidence + counter-framing on the blackboard).
- Added **Bias/Blindspot Analyzer** (mechanical; curated 42-outlet
  `resources/outlet_bias.json` → L/C/R spread + blindspot flags).
- Added **Writer** (LLM merges verdict + both evidence sets + bias report;
  deterministic audit-trail section appended from `audit_log`).
- Rewired `graph.py`: parallel `source_finder ∥ opposition → cross_checker`,
  a bounded (`max 1`) deep-research loop back to `cross_checker` on
  low-confidence `disputed`, then `bias_analyzer → writer`.
- Cross-Checker now adjudicates *both* evidence roles.
- Added `observability/` — `Event`/`Reporter` model, `MultiReporter`,
  `AuditLogReporter`, and `ConsoleReporter` (a `rich.Live` dashboard: item,
  agents, shared blackboard, event stream).
- Store: `summary` column on `findings` (+ migration), new `bias_reports` /
  `reports` / `audit_log` tables, `merge_finding`, `append_audit`/`get_audit`,
  optional reporter that emits `bb_read`/`bb_write` on attributed calls.
- Added `demo/fixtures.py` (offline `FakeGdeltClient`/`FakeLLMClient`) so the
  full pipeline + dashboard run with no keys: `python -m newsfact.main --demo`.
- CLI: batch claims / `--file`, `--demo`, `--plain`, `--no-cache`, `--keep-db`,
  `--json`, end-of-run report panels + recap.
- 24 new tests (44 total), still fully offline.

## Decisions made (and why)

- **Kept the stack** (LangGraph + SQLite + terminal). Fan-out/fan-in already
  expresses SF∥Opposition→CrossChecker; conditional edges express the loop;
  the audit log is one more table in the existing DB. No reason to add
  infrastructure for a milestone whose goal is "agents present + communicating
  + visible in terminal". Web UI stays v3.
- **Two reporter channels, one config point.** Agents/graph take a `reporter`;
  the store also holds one and emits `bb_*` events. `main.py` gives both the
  same `MultiReporter`; `run_pipeline` falls back to `store.reporter` so callers
  don't wire it twice. This is what makes "shared blackboard" *watchable*
  rather than just architecturally true.
- **Evidence stays GDELT-sourced even for Opposition.** Its LLM call only
  produces search angles + a framing sentence — never article content — so the
  hybrid-blackboard "no hallucination propagation" invariant holds.
- **Deep-research loop deliberately minimal** (1 pass, keyword-broadened query,
  `merge` not overwrite). Enough to demonstrate the loop exists and is bounded;
  widening it is a named HANDOFF item, not this session's job.
- **Offline demo is scripted, not smart.** `FakeLLMClient` branches on the
  agent's system prompt and recognises the three sample claims to hit all
  verdict paths. It's a visibility harness, not a model simulator — flagged as
  such in HANDOFF so nobody mistakes the demo output for real behaviour.
- **Outlet bias table shipped as a v1-quality approximation** (~42 outlets;
  Indian rows hand-guessed — no standardized rater exists, resource doc Gap #1).
  Format is stable and overridable via `NEWSFACT_BIAS_TABLE`; the data needs a
  dedicated research pass.

## Open questions for next session

- Same as v1: no live GDELT/Anthropic call has been made. First key'd session
  should smoke-test `tools/gdelt.py::_parse_response` against a real response.
- Should Source-Finder get its own query-shaping LLM call (Opposition already
  has one)? Likely yes for recall.
- Is 1 deep-research pass enough, or should the loop target the specific
  conflict Cross-Checker names and allow more passes?
- The Indian-outlet ratings need real sourcing before the bias output is
  presentable.
