# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
