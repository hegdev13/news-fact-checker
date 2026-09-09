# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.2.1] — 2026-09-09 — "v2.1: article-input mode"

### Added
- **Claim Extractor agent** (`agents/claim_extractor.py`) — front-end for
  "here is an article, check it": one LLM call extracts the central checkable
  claim (+ up to two secondary claims); that primary claim becomes the
  `claim_id` the existing 5-agent pipeline runs on, unchanged. Falls back to a
  headline heuristic if the LLM output is unusable.
- **Source identification** (`tools/source_id.py`) — "find the source": maps a
  submitted article to its publishing outlet from an accompanying URL, the
  first URL in the body, or a byline / "(Reuters)"-style credit matched against
  the bias table. Pure/offline — a URL is parsed, never fetched.
- **`source_docs` table** + `SourceDoc` dataclass — persists the submitted
  article's origin outlet (domain, name, bias, factuality, country, how it was
  identified), byline, extracted claims, and an excerpt, keyed by the extracted
  primary claim's id.
- **`run_article_pipeline()`** (`graph.py`) — article mode orchestration:
  Claim Extractor → the normal `build_graph` pipeline on the extracted claim.
- CLI: `--article PATH` (`-` = stdin, bare flag = bundled sample),
  `--article-text TEXT`, `--article-url URL`. Recap tags article runs
  "(from article)".
- `resources/sample_article.txt` — bundled sample for `--demo --article`.
- Tests: `test_source_id.py`, `test_claim_extractor.py`,
  `test_article_pipeline.py` (15 new, still fully offline; 59 total).

### Changed
- **Bias/Blindspot Analyzer** now folds the submitting outlet into the L/C/R
  spread (deduped by domain, tagged `origin`) and adds origin-specific
  blindspot notes — most importantly "No independent outlet corroborates the
  submitted article — only its own publisher carries this claim."
- **Writer** prepends a deterministic **Source of the submitted article**
  section (outlet + bias/factuality + how identified + extracted claims) when a
  `SourceDoc` exists, and passes `submitted_article` in its LLM payload.
- **Console dashboard** — `claim_extractor` added to the agent roster (its row
  shows only in article mode); a "Submitted src" line appears on the
  blackboard panel.
- `demo/fixtures.py` — `FakeLLMClient` gains a `Claim Extractor agent` branch.
- `pyproject.toml` / `__init__.py` — version `0.2.1`.

### Notes
- Article mode always runs the full pipeline (no pre-run report-cache
  short-circuit, since the `claim_id` isn't known until extraction); the report
  is still cached for later claim-mode lookups.
- Still no live GDELT / Anthropic call this session — env kept stubbed.

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
