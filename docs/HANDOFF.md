# Handoff / Current State

_Last updated: 2026-09-09, initial v1 build session._

Read this first, before `CHANGELOG.md` or the session logs, if you're picking
this project up fresh (human or agent).

## What exists right now

A working v1 slice: **Source-Finder → Cross-Checker**, orchestrated with
LangGraph, sharing state through a SQLite blackboard store. Runnable via
`python -m newsfact.main "<claim>"`. Fully tested offline (all external calls
mocked) — see `tests/`.

No live end-to-end run has been done this session (no API keys were provided).
The code is written against the real GDELT API and real Anthropic API, but has
only been verified via mocked tests, not a live call. **First thing a new
session with API keys should do: run one real claim through the CLI and sanity
check the output** before building further on top of it.

## What's NOT built yet (in priority order)

1. **Opposition agent** — the adversarial counter-evidence agent. This is the
   project's actual differentiator per the resource doc (the "hard-mandated
   disagreement" design, citing the Inducing Disagreement paper). Should run
   in parallel with Source-Finder against the same claim, write its findings
   to a separate `findings` row (or a `role` column distinguishing
   source_finder/opposition rows — recommend adding a `role` column rather
   than a new table). Cross-Checker's prompt will need to change from
   "assess agreement across Source-Finder's results" to "adjudicate between
   Source-Finder's and Opposition's results."
2. **Bias/Blindspot Analyzer agent** — needs the outlet bias table gap closed
   first (see below). Once that exists, this is a relatively mechanical
   agent: map each article's outlet to a bias label, compute L/C/R spread,
   flag if one side is missing entirely.
3. **Writer agent** — merges verdict + bias breakdown into the final
   structured report described in the resource doc. Straightforward once (1)
   and (2) exist; low-value to build before them since there isn't much to
   merge yet.
4. **Indian-outlet bias table** — hand-curated JSON, à la HERALD's 224-outlet
   table. Blocks (2). Needs a dedicated research pass, not just coding.
5. **Deep-research loop on conflict** — the resource doc calls for a loop
   that re-triggers when Cross-Checker finds conflicting sources. Needs (1)
   to exist first (nothing to loop on with only one evidence source). Once
   Opposition exists, this is a conditional edge in `graph.py` back into a
   "gather more evidence" node.
6. **Formal audit log** — append-only log of tool calls/sources/verdict
   changes per claim. No existing-repo precedent per the resource doc; will
   need custom design. Natural extension of the `findings`/`verdicts` tables
   already in `memory/store.py` — could be a fourth `audit_log` table keyed
   the same way.
7. **Story/event clustering** — only matters once the system handles more
   than one claim/story at a time (e.g. a "what's trending" mode rather than
   "check this specific claim"). Not needed for the current claim-at-a-time
   CLI.

## Known rough edges

- `src/newsfact/tools/gdelt.py` has not been exercised against the live GDELT
  endpoint — the response-shape assumptions in `_parse_response` are based on
  GDELT's documented JSON schema, not a captured real response. Worth a
  smoke test with a real API call early.
- Cross-Checker's confidence score is currently a single float from one LLM
  call with no calibration/eval against a labeled dataset. The resource doc
  names LIAR/FEVER/AVeriTeC as benchmarks if this needs to be validated later.
- No rate limiting / backoff on the GDELT client. Fine for CLI single-claim
  use; would need it before any batch/loop use.
- `NEWSFACT_MODEL` defaults to `claude-sonnet-4-5` in `config.py` — bump this
  if a newer default model is preferred by the time you read this.

## Conventions to keep following

- Every agent writes only *structured, verified* output to the shared store
  (see `docs/ARCHITECTURE.md` § Shared memory) — never raw LLM reasoning
  traces. Keep this invariant when adding Opposition/Bias/Writer.
- Verdict labels are constrained to `corroborated` / `disputed` /
  `unverifiable` — no binary true/false. Keep this when Writer starts
  consuming verdicts too.
- Update this file's "What exists" / "What's NOT built yet" sections whenever
  you finish or start a agent, so the list above stays accurate rather than
  aspirational.
- Add a dated file to `docs/sessions/` for any session that makes a real
  design decision (not every session — see `docs/sessions/README.md`).
- Update `CHANGELOG.md`'s `Unreleased` section as you go, not just at the end.
