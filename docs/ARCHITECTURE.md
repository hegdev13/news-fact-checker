# Architecture & Design Decisions

> The sections below describe v1 (the 2-agent slice). **v2 additions —
> Opposition, Bias/Blindspot Analyzer, Writer, the deep-research loop, the
> observability layer, and the offline demo — are under "# v2 additions" near
> the end. v2.1 (article-input mode + Claim Extractor) is under
> "# v2.1 additions" at the very end.**

# Architecture & Design Decisions (v1)

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | The resource document's own survey singles this out as "the most controllable option for fine-grained read/write access per agent" via its typed `State` object — closest fit to the blackboard pattern without full framework lock-in (AutoGen's turn-taking and CrewAI's static shared memory were both flagged as weaker fits). |
| LLM | **Anthropic Claude** (`anthropic` SDK) | This project runs inside the Claude ecosystem already; no reason to add a second model provider for v1. Model name is configurable via `NEWSFACT_MODEL` env var. |
| News source | **GDELT DOC 2.0 API** | Per the resource doc: non-US-centric (matters for the Indian-news angle), ships tone/sentiment per article usable as a cheap bias proxy, and needs no API key. Avoids a signup blocker for v1. |
| Shared memory | **SQLite** | Used by nearly every reference repo surveyed (`nilayjain12/fake-news-agent`, HERALD, etc.) for exactly this purpose: caching prior verdicts and avoiding re-running the pipeline for a previously-checked claim. Zero infra, ships in the stdlib. |
| Packaging | `pyproject.toml` + `setuptools`, installable with `pip install -e .` | Standard modern Python packaging; avoids a bare `requirements.txt` with no installable package. |
| Tests | `pytest` + `pytest-mock` | All external calls (GDELT HTTP, Anthropic API) are mocked so the suite runs offline and without API keys — important since this is a public/portfolio-adjacent repo other agents/sessions will pick up without necessarily having keys configured. |

## Why only 2 agents in v1

The full design calls for 5 agents (Source-Finder, Opposition, Cross-Checker,
Bias/Blindspot Analyzer, Writer) running in a swarm/adversarial pattern. For
v1 we deliberately built the smallest pair that:

1. Demonstrates the actual architectural bet of this project — agents reading
   from a **shared** store rather than passing state linearly in a fixed
   pipeline (the gap the resource doc flags as unsolved in every surveyed repo).
2. Produces a real, inspectable output (a confidence-scored verdict + the
   evidence behind it) rather than a stub.

Source-Finder + Cross-Checker was chosen over the alternatives considered:

- *Source-Finder + Opposition* would demonstrate the adversarial design
  first, but produces no verdict on its own — you'd need Cross-Checker
  anyway to make sense of two competing evidence sets.
- *Source-Finder + Writer* would produce a polished report fastest, but
  skips the conflict-detection mechanic entirely, which is the part with
  the least existing-repo precedent per the resource doc's own gap analysis.

Source-Finder + Cross-Checker gives a working seam of the actual novel
mechanic (independent-source agreement/conflict detection off a shared
store) with a real, usable output. Opposition, the Bias/Blindspot Analyzer,
and Writer are the natural next additions — see `docs/HANDOFF.md`.

## Shared memory: hybrid blackboard

Per the resource doc's own recommendation (citing the "Shared Memory Is Their
Best Coordinator and Biggest Attack Surface" guidance): the shared store only
ever holds **verified, structured artifacts** — the claim record, the list of
articles Source-Finder found (title/outlet/url/date/tone), and Cross-Checker's
verdict. Each agent's raw prompt/reasoning trace is not written to the shared
store; only its structured output is. This limits how far one agent's
hallucination can propagate into another agent's context.

Concretely, `src/newsfact/memory/store.py` exposes three tables:

- `claims` — one row per claim string (hash-keyed), created on first sight.
- `findings` — Source-Finder's output for a claim: a JSON blob of articles.
- `verdicts` — Cross-Checker's output for a claim: verdict label, confidence
  score, reasoning summary, timestamp.

`main.py` checks `verdicts` for an existing row before running the graph at
all — this is the "don't re-investigate a checked claim" requirement from the
resource doc, implemented the same way `nilayjain12/fake-news-agent` does it.

## Orchestration graph

```
        ┌───────────────┐        ┌───────────────┐
 claim →│ source_finder │──────→│ cross_checker │──→ verdict
        └───────────────┘        └───────────────┘
              writes                  reads
           `findings`              `findings`,
                                    writes `verdicts`
```

A single linear LangGraph `StateGraph` with two nodes. This is intentionally
not yet the "swarm/parallel + deep-research loop on conflict" pattern from the
full spec — that requires the Opposition agent to exist first (there's nothing
to run in parallel with only one evidence-gathering agent). The graph is
structured so adding a parallel `opposition` node and a conditional edge back
into a "deep research" loop is additive, not a rewrite — see `docs/HANDOFF.md`
for the concrete plan.

## Verdict semantics

Per the resource doc's governance rule ("never 'false' from a single source —
'unverifiable' when evidence is thin"), Cross-Checker's prompt constrains it to
one of: `corroborated`, `disputed`, `unverifiable`. It is explicitly instructed
never to output a binary true/false, and never to treat a single outlet as
sufficient for `corroborated`.

## Known limitations (carried over from the resource doc's Gaps table)

- No Indian-outlet bias table yet (blocks the Bias/Blindspot Analyzer).
- No story/event clustering (not needed yet — v1 checks one claim at a time,
  doesn't cluster multiple stories).
- No formal audit log yet — `findings`/`verdicts` rows are timestamped but
  there's no append-only trail of intermediate tool calls per claim.
- GDELT's rolling ~3-month window means very old claims will return sparse or
  no results — Cross-Checker should (and does) fall back to `unverifiable`
  rather than misreport this as "no coverage anywhere."

---

# v2 additions

v2 completes the five-agent roster and makes the pipeline observable. The core
v1 bet is unchanged: agents coordinate through a shared SQLite blackboard, not
by passing state linearly.

## The five agents

| Agent | LLM? | Reads | Writes |
|---|---|---|---|
| Source-Finder | no | claim | `findings(role=source_finder)` |
| Opposition | yes | claim | `findings(role=opposition)` + `summary` counter-framing |
| Cross-Checker | yes | both `findings` roles | `verdicts` |
| Bias/Blindspot Analyzer | no | both `findings` roles | `bias_reports` |
| Writer | yes | `verdicts`, both `findings`, `bias_reports`, `audit_log` | `reports` |

### Opposition: hard-mandated, not "be skeptical"

Per the resource doc and the *Inducing Disagreement* finding it cites, soft
"be critical" prompts barely move disagreement rates; only an unconditional
"you MUST argue against this" role produces real opposition. The system prompt
in `agents/opposition.py` reflects that — it is instructed not to hedge, not to
balance, not to concede. Its LLM call only produces *search angles* +
a one-sentence counter-framing; the evidence itself still comes from GDELT, so a
hallucinated angle can't become a hallucinated source.

### Cross-Checker adjudicates two sets, not one

v1 asked "do Source-Finder's results agree?". v2 asks "adjudicate Source-Finder
vs Opposition". The `<2 distinct domains` short-circuit now counts domains
across *both* roles combined. Opposition's `counter_framing` is passed as "an
argument to weigh, not fact".

### Deep-research loop

`graph.py` routes `cross_checker → deep_research` only when the verdict is
`disputed` **and** confidence `< 0.6` **and** `research_passes < 1`. The
`deep_research` node re-runs Source-Finder + Opposition with broadened queries
and `merge_finding`s (union + dedupe on url) rather than overwriting, then loops
back to Cross-Checker. Bounded to one extra pass for v2 — deliberately
conservative; widening this is a known next step (HANDOFF #4).

### Bias/Blindspot Analyzer + the outlet table

Mechanical. `tools/bias_table.py` loads `resources/outlet_bias.json` (42
outlets: AllSides/MBFC-consensus for US/UK/global, hand-curated for Indian
outlets since no standardized rater exists — resource doc Gap #1, and this is
explicitly a v1-quality approximation). Fine-grained bias values collapse to
L/C/R buckets; the analyzer computes the spread, the dominant side, and
blindspot notes (missing side, no center/wire source, heavy skew,
low-factuality sources in the pool). `NEWSFACT_BIAS_TABLE` overrides the file.

## Shared store: two new artifact tables + an audit trail

`memory/store.py` gains `bias_reports` and `reports` (same one-row-per-claim,
upsert shape as `verdicts`), plus `audit_log` — an **append-only** table
(`id INTEGER PRIMARY KEY AUTOINCREMENT`, keyed by `claim_id`) holding every
event. `reports` doubles as the duplicate-claim cache (`main.py` checks
`get_report()` before running the graph). `findings` gains a `summary` column
with an in-place `ALTER TABLE` migration for older DB files.

The store takes an optional `Reporter`. When a read/write is attributed to an
agent (`by="cross_checker"` etc.) it emits a `bb_read` / `bb_write` event — this
is what turns "agents share a blackboard" into something you can watch. Internal
/ test calls omit `by=` and stay silent.

## Observability layer (`observability/`)

- `events.py` — `Event` (kind, agent, message, claim_id, data, ts); `EventKind`
  string constants (serialize cleanly into `audit_log` and across a future
  process boundary); `Reporter` protocol; `NullReporter` (default everywhere),
  `MultiReporter` (fan-out; a failing sink never breaks the others or the run),
  `AuditLogReporter` (persists to the store).
- `console.py` — `ConsoleReporter`, a `rich.Live` region with four panels:
  the current news item, the five agents + status, the shared-blackboard
  contents, and a streaming event log. Finished items are printed to scrollback
  above the live region. Falls back to flat line printing when stdout isn't a
  TTY or `--plain` is set.

Both `main.py` and the graph share one `MultiReporter([ConsoleReporter,
AuditLogReporter])`; it's set on the store, and `run_pipeline` falls back to the
store's reporter so callers configure observability once.

## Offline demo (`demo/fixtures.py`)

`FakeGdeltClient` and `FakeLLMClient` are scripted (not smart): they recognise
keywords from the three bundled sample claims to exercise the corroborated /
disputed-with-loop / unverifiable paths, and fall back to a generic
multi-outlet corroborated result otherwise. `FakeLLMClient` branches on which
agent's system prompt it was handed. Purpose: make the full pipeline + dashboard
runnable and visible with zero credentials. `main.py` selects the fakes when
`--demo` is passed or `ANTHROPIC_API_KEY` is unset.

## Why still LangGraph, still SQLite, still terminal

No stack change in v2. LangGraph's fan-out/fan-in expresses Source-Finder ∥
Opposition → Cross-Checker directly, and conditional edges express the loop.
SQLite already had the "cache checked claims" job; the audit log is one more
table in the same file. The web UI is v3 by explicit request — v2's job was
"all agents present, communicating, and the process visible in the terminal".

---

# v2.1 additions — article-input mode

v2.1 adds a front-end: submit a whole article instead of a claim string. The
5-agent pipeline downstream is unchanged — a new **Claim Extractor** agent
turns the article into the primary claim the graph already knows how to check.

## Claim Extractor (`agents/claim_extractor.py`)

Two jobs in one turn:

1. **Find the source** — `tools/source_id.py::identify_source(text, url, table)`
   returns an `OriginGuess`: it tries an explicit `--article-url`, then the
   first URL in the body (parsed for its domain, **never fetched**), then a
   byline / `(Reuters)`-style credit / bare outlet-name match against the bias
   table's outlet names. `method` is `"url"` / `"byline"` / `"none"`.
2. **Extract the claim** — one LLM call → `{primary_claim, secondary_claims[],
   article_summary}`. Falls back to a first-substantial-line headline heuristic
   if the response is unusable. `store.ensure_claim(primary_claim)` yields the
   `claim_id` everything else keys off.

It writes one `source_docs` row (origin outlet + bias/factuality/country + how
identified + byline + extracted claims + excerpt), keyed by that `claim_id`.

## Two graph entry points (`graph.py`)

`build_graph` and the node functions are untouched. The invoke + ITEM_DONE
logic is factored into `_invoke_graph`, and there are now two front doors:

- `run_pipeline(claim, …)` — claim mode, as before.
- `run_article_pipeline(article, …, url=None)` — emits ITEM_START, runs
  `run_claim_extractor`, then `_invoke_graph` on the extracted primary claim.

The dashboard shows a `claim_extractor` row only in article mode (it never
emits an event in claim mode); a "Submitted src" line appears on the
blackboard panel.

## Downstream agents that now read `source_docs`

- **Bias/Blindspot Analyzer** — folds the origin outlet into `per_domain`
  (deduped by domain, tagged `"origin": True`), so it joins the L/C/R spread.
  Adds origin-specific notes via `_origin_notes()`: names the outlet + its
  rating, and — crucially — flags "No independent outlet corroborates the
  submitted article" when every retrieved domain is the origin domain (or there
  are none).
- **Writer** — `_source_md()` prepends a deterministic **Source of the
  submitted article** section (outlet, bias/factuality, identification method,
  extracted primary + secondary claims) so the "find the source" result is
  always present and accurate regardless of the LLM; `submitted_article` is
  also included in the LLM payload.

## Deliberate limits (see docs/HANDOFF.md "What's NOT built")

Source ID is a heuristic string/URL match, not resolution — it can't see
wire copy republished under a local masthead, and byline matching misses
unlisted outlets. Only the single primary claim is run; secondary claims are
recorded but not checked. Article mode always runs the full pipeline (no
report-cache pre-check — the `claim_id` isn't known until after extraction).
