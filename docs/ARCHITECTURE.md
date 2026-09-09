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
