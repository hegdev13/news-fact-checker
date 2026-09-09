# News Fact-Checker & Polarization Analyzer

A multi-agent system that takes a news claim and both verifies it and shows how
coverage of it splits across the political spectrum. See
[`docs/resource-document.md`](docs/resource-document.md) for the full project
brief, prior-art survey, and known gaps.

## Status: v2 — all five agents + live terminal dashboard

v2 completes the agent roster from the design and makes the whole pipeline
watchable in the terminal as it processes each news item.

| Agent | Status | Does |
|---|---|---|
| **Source-Finder** | ✅ | Neutral GDELT search for coverage of the claim; writes structured findings to the shared blackboard |
| **Opposition** | ✅ | **Hard-mandated adversary** — LLM generates disconfirming search angles, runs them, writes counter-evidence + a one-line counter-framing |
| **Cross-Checker** | ✅ | Adjudicates Source-Finder vs Opposition evidence into a confidence-scored verdict (`corroborated` / `disputed` / `unverifiable`, never true/false) |
| **Bias/Blindspot Analyzer** | ✅ | Maps every retrieved outlet to a bias/factuality rating, computes the L/C/R spread, flags blindspots |
| **Writer** | ✅ | Merges verdict + evidence + opposition + bias into one report; appends a deterministic audit trail |

Orchestration (LangGraph):

```
START ─┬─▶ source_finder ─┐
       └─▶ opposition ─────┴─▶ cross_checker ──(disputed & low confidence)──▶ deep_research ─┐
                                    │  ▲                                                      │
                                    │  └──────────────────────────────────────────────────────┘
                                    ▼ (else)
                               bias_analyzer ──▶ writer ──▶ END
```

Agents never hand state to each other directly — they read and write a shared
SQLite **blackboard**, and every read/write/tool-call is emitted as an event
that the live dashboard renders and the `audit_log` table persists.

## Quick start (no API keys needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m newsfact.main --demo
```

`--demo` runs the full 5-agent pipeline over three bundled sample news items
using offline fixtures for GDELT and Claude — nothing hits the network. You get
the live dashboard, three verdict paths (corroborated / disputed-with-loop /
unverifiable), a rendered report per item, and a run recap.

Add `--plain` to disable the live region and print a flat event trace (good for
piping to a file). Add `--json` for a machine-readable summary.

## Real run

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY
python -m newsfact.main "Claim or headline to check" "A second claim"
python -m newsfact.main --file path/to/claims.txt
```

With `ANTHROPIC_API_KEY` set it uses the real Anthropic API and the live GDELT
DOC 2.0 API (no GDELT key required). Results are cached in `data/newsfact.db`
keyed by claim text, so re-checking the same claim replays the stored report
instead of re-running the pipeline. `--no-cache` forces a re-run.

## Tests

```bash
pytest
```

All tests run offline — GDELT and Anthropic calls are mocked or use the demo
fixtures. No API keys required.

## Project layout

```
src/newsfact/
  agents/          source_finder, opposition, cross_checker, bias_analyzer, writer
  tools/           gdelt.py, bias_table.py
  memory/          store.py — shared SQLite blackboard (claims, findings, verdicts,
                   bias_reports, reports, audit_log)
  observability/   events.py (event model + reporter sinks), console.py (live dashboard)
  demo/            fixtures.py — offline FakeGdeltClient / FakeLLMClient
  resources/       outlet_bias.json (curated bias table), sample_claims.txt
  graph.py         LangGraph wiring for the 5-agent pipeline + deep-research loop
  main.py          CLI entrypoint
docs/
  resource-document.md   original brief / research
  ARCHITECTURE.md         design decisions and rationale
  HANDOFF.md              current state + next steps (read this first)
  sessions/               dated session logs
tests/
```

## Contributing across sessions / agents

Before starting: read `docs/HANDOFF.md`, then `CHANGELOG.md`, then the latest
`docs/sessions/` entry. Before ending a session that changed anything
non-trivial: update `CHANGELOG.md` (`Unreleased`), update `docs/HANDOFF.md` if
"what's done / what's next" moved, and add a dated `docs/sessions/` file if the
session made architectural decisions.
