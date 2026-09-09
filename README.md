# News Fact-Checker & Polarization Analyzer

A multi-agent system that takes a news claim and (eventually) both verifies it and
shows how coverage of it splits across the political spectrum. See
[`docs/resource-document.md`](docs/resource-document.md) for the full project
brief, prior-art survey, and known gaps this project is scoping around.

## Status: v1 (partial deliverable)

v1 implements the smallest slice of the full design that still demonstrates the
core architecture: **two agents sharing a blackboard-style memory store**,
orchestrated with LangGraph.

| Agent | Implemented? | Does |
|---|---|---|
| **Source-Finder** | ✅ v1 | Queries GDELT for coverage of a claim, writes structured findings to shared memory |
| **Cross-Checker** | ✅ v1 | Reads Source-Finder's findings, asks Claude to assess agreement/conflict across independent outlets, writes a confidence-scored verdict back to shared memory |
| Opposition | ⬜ not yet | Adversarial counter-evidence search (see `docs/HANDOFF.md`) |
| Bias/Blindspot Analyzer | ⬜ not yet | Outlet-level L/C/R mapping |
| Writer | ⬜ not yet | Final structured report |

This is intentionally a partial build. `docs/HANDOFF.md` has the full state of
what's done, what's stubbed, and the recommended next steps for whoever (human
or agent) picks this up next.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full write-up.
Short version: a hybrid blackboard pattern — a SQLite-backed shared store holds
verified intermediate artifacts (claims, findings, verdicts) that any agent can
read; each agent's raw reasoning stays local. Orchestration uses LangGraph's
typed `State` object passed through a graph of agent nodes.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY (required for Cross-Checker's reasoning step)
```

GDELT's DOC 2.0 API needs no API key.

## Usage

```bash
python -m newsfact.main "Claim or headline to check"
```

This runs the Source-Finder → Cross-Checker graph once, prints a JSON result,
and caches it in `data/newsfact.db` keyed by the claim text so re-running the
same claim doesn't re-hit GDELT or the LLM.

## Tests

```bash
pytest
```

All tests run offline — GDELT HTTP calls and Claude API calls are mocked, so no
API keys are required to run the test suite.

## Project layout

```
src/newsfact/
  agents/          # one module per agent
  tools/           # external API clients (GDELT, later: bias tables, etc.)
  memory/          # shared SQLite blackboard store
  graph.py         # LangGraph wiring between agents
  main.py          # CLI entrypoint
docs/
  resource-document.md   # original project brief / research
  ARCHITECTURE.md         # design decisions and rationale
  HANDOFF.md              # current state + next steps, kept up to date every session
  sessions/               # dated session logs (see docs/sessions/README.md)
tests/
CHANGELOG.md
```

## Contributing across sessions / agents

This project is built incrementally across multiple Claude sessions. Before
starting work:

1. Read `docs/HANDOFF.md` for current state and open threads.
2. Check `CHANGELOG.md` for what changed most recently.
3. Skim the latest file in `docs/sessions/` if you need more detail on *why*
   a decision was made.

Before ending a session that changed anything non-trivial:

1. Update `CHANGELOG.md` (Keep a Changelog format, `Unreleased` section).
2. Update `docs/HANDOFF.md` if the state of "what's done / what's next" changed.
3. Add a dated file under `docs/sessions/` if the session made architectural
   decisions worth explaining to a future reader.
