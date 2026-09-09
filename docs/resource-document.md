# Multi-Agent News Fact-Checker & Polarization Analyzer — Resource Document

## Project Summary

A multi-agent system that takes a news claim or story and does two things at once: verifies it and shows how it's being covered across the political spectrum. A **Source-Finder** agent searches news APIs/feeds for coverage; an **Opposition** agent deliberately hunts for counter-evidence or under-covered framing (not a soft "be skeptical" prompt — a hard-mandated adversarial role, per the debate literature); a **Cross-Checker** compares findings and flags agreement/conflict; a **Writer** merges everything into one report: sources checked, confidence-scored verdict (never "false" from a single source — "unverifiable" when evidence is thin), and a bias/blindspot breakdown showing which outlets (left/center/right) covered it and which side is underrepresented. A **shared memory layer** lets agents read each other's intermediate findings rather than passing state linearly, and caches previously-checked claims so repeat queries don't re-run the whole pipeline. Data comes from live news APIs/RSS (GDELT is a strong candidate — non-US-centric, includes tone data) plus an outlet-level bias/factuality table (AllSides/MBFC-style for global outlets; likely hand-curated for Indian sources, since no standardized rater exists there yet). An MCP connector exposes the news-search tool to the orchestration layer.

---

## Proposed Agent Roles

| Agent | Role |
|---|---|
| **Source-Finder** | Searches news APIs/feeds/archives for coverage of the claim or story |
| **Opposition** | Hard-mandated adversarial role — actively searches for contradicting evidence, under-covered angles, or the strongest counter-framing |
| **Cross-Checker** | Compares Source-Finder and Opposition output, flags agreement/conflict across independent sources |
| **Bias/Blindspot Analyzer** | Maps each source to an outlet-level bias/factuality rating, computes coverage spread (L/C/R), flags blindspots |
| **Writer** | Merges everything into one structured report — verdict, confidence, source list, bias breakdown, audit trail |

Orchestration pattern: Swarm-style (Source-Finder + Opposition run in parallel/adversarial debate → Cross-Checker adjudicates → Writer merges), with a deep-research loop triggered specifically when Cross-Checker finds conflicting sources.

---

## Related GitHub Repos & Existing Work

### Multi-agent fact-checking pipelines
- **`SukritDeb/Veritas`** — 3-agent pipeline (Researcher → Fact-Checker → Editor), built from raw API calls, Tavily search, cross-checks claims against raw articles (not the synthesis) to avoid hallucination compounding.
- **`saikiran1224/FactBot-AI`** — CrewAI-based, produces verdict + supporting articles + reasoning + sources-verified count.
- **`HySonLab/FactAgent`** (paper: arXiv 2506.17878) — focus on advanced evidence retrieval.
- **`anushkasingh-code/multi-agent-fact-verification`** — LangGraph 5-agent DAG: Claim Extractor → Search Retriever (Tavily + FAISS) → Fact Verifier → Contradiction Detector → Report Generator. Closest existing architecture to the Cross-Checker/conflict-detection step.
- **`nilayjain12/fake-news-agent`** — Google ADK, 5 agents; **SQLite-cached prior verdicts** (directly solves the "don't re-investigate a checked claim" requirement); own roadmap flags true agent-to-agent (A2A) communication as unbuilt.
- **Tathya** (GitHub topic `fact-checking`) — multi-source verifier including Wikidata alongside news APIs.

### Bias / polarization classifiers (non-agentic, useful as label sources or eval sets)
- **`ramybaly/Article-Bias-Prediction`** (EMNLP 2020) — reference dataset/model for left/center/right article classification, AllSides ground truth.
- **`fausa/Bias_Detection_in_Journalism`**, **`N2ITN/are-you-fake-news`**, **`Bastlynn/newscraper`** — NewsAPI/scraping + classifier, trained against AllSides/MBFC labels.
- **`ahaldar/News-bias-detector`** — lightweight, sentence-level partisan-language/sensationalism flagging (VADER + SVO extraction) — usable as a cheap interpretable signal feeding an agent, not a replacement for one.
- **`pkipsy/news-lens`** — same-story, multi-outlet side-by-side comparison (conceptually closest non-agentic prior art for the "polarization view").

### Ground News-style aggregation
- **`diazaeric1-droid/herald`** (https://github.com/diazaeric1-droid/herald) — closest working clone. RSS ingestion → TF-IDF + average-linkage story clustering → static 224-outlet bias table (AllSides/MBFC/Ground consensus) → Claude writes an impact analysis per cluster → weighted newsworthiness score (corroboration, source quality, bias-spread, etc.) → Telegram alert. Single-agent pipeline, not multi-agent — good architectural reference, not a drop-in multi-agent base.
- **MediaBias.news** — solo-dev free Ground News alternative (Medium writeup), not yet open source.
- **AllSides, Ad Fontes Media, Media Bias/Fact Check (MBFC)** — the three non-agentic rating orgs Ground News itself averages; also the closest free direct substitutes if you want a baseline to compare your system's output against.

### Adversarial / debate-based verification (underpins the Opposition agent design)
- **TED / TruEDebate** (arXiv 2505.08532) — two agent teams debate true/false, a synthesis agent adjudicates.
- **DebateCV** (arXiv 2507.19090) — two Debaters + a Moderator, beats single-agent and standard multi-agent baselines on AVeriTeC by catching misinterpretation, overlooked evidence, and speculation.
- **"Inducing Disagreement in Multi-Agent LLM Teams"** (OpenReview) — empirical finding: only a hard-mandated "you must oppose" role produces real disagreement (~99%); soft "be critical" prompts don't (~55–63%, near baseline). Directly informs how to prompt the Opposition agent.

### Shared memory / orchestration patterns
- **Blackboard architecture** — classical pattern for agents reading/writing a shared workspace instead of passing state linearly; the closest fit to "agents should interact with each other."
- **AutoGen** — group-chat multi-agent, but sequential turn-taking under the hood; own community discussion (`microsoft/autogen` Discussion #7144) acknowledges shared state across simultaneous dialogues is unsolved out of the box.
- **CrewAI** — documented "shared memory," but described in multiple write-ups as fairly static across sessions; commonly paired with Mem0 for persistence.
- **LangGraph** — shared `State` object passed through a graph; most controllable option for fine-grained read/write access per agent.
- Practical guidance (Medium, "Your AI Agents' Shared Memory Is Their Best Coordinator and Their Biggest Attack Surface"): production-safe version is **hybrid** — only verified summaries go into the shared layer, raw reasoning stays agent-local. Relevant given the governance rule against single-source certainty: a fully-open shared memory lets one hallucinating agent contaminate every other agent's context.

---

## Tools & Integrations

**MCP news connectors (existing, off-the-shelf):**
| Server | Source | Notes |
|---|---|---|
| `EventRegistry/newsapi-mcp` | NewsAPI.ai | Ships a `/news` slash-command skill automating suggest→scan→triage→retrieve |
| `berlinbra/news-api-mcp` | newsapi.org | Simple, Docker-runnable |
| `MissionSquad/mcp-gdelt` | GDELT DOC 2.0 | 65-language search, tone/sentiment per article, rolling 3-month window |
| Apify GDELT actors | GDELT | No API key, per-article tone, updated every 15 min |

**GDELT stands out** for this project specifically: non-US-centric coverage (relevant to the Indian-news angle), built-in tone/sentiment data usable as a cheap bias proxy, and no API key required for several access paths.

**Other integrations needed:**
- Outlet bias/factuality/ownership lookup (see Gaps below)
- Story/event clustering engine (TF-IDF baseline, or sentence-embedding/FAISS for cross-language robustness)
- Persistent cache/memory store (SQLite is the common choice across every reference repo above) for both "checked claims" and "seen story clusters"

---

## Datasets

- **LIAR / LIAR-style claim+verdict data** — standard benchmark for claim-verification model evaluation (short political statements labeled true/false/pants-on-fire etc.)
- **FEVER, FEVEROUS, SciFact-Open, AVeriTeC** — benchmarks used by the debate-based verification papers above; useful if you want to evaluate your Cross-Checker/Opposition setup against published baselines rather than only eyeballing outputs
- **Kaggle Indian news datasets** — named in the original problem doc but not yet identified to a specific dataset in our research; needs a follow-up search to pick a specific one before use (see Gaps)
- **AllSides / MBFC outlet-bias tables** — no clean bulk API; existing projects (HERALD) hand-curate a static JSON from these; same approach is the practical path here
- **`ramybaly/Article-Bias-Prediction`** dataset — labeled left/center/right articles, usable for evaluating an LLM-based per-article bias judge against a human-labeled baseline

---

## Gaps & Suggested Solutions

| Gap | Why it matters | Suggested solution |
|---|---|---|
| **No standardized bias/factuality rater for Indian outlets** | AllSides/MBFC/Ad Fontes are explicitly US-centric; the project's Indian-news angle has no equivalent off-the-shelf label source | Hand-curate a small outlet-bias table for major Indian outlets (à la HERALD's 224-outlet JSON), cross-checked against whatever academic/media-literacy sources exist; treat it as a v1 approximation, not a validated rating |
| **No repo implements true agent-to-agent shared memory** | Every fact-checking repo found is a linear pipeline (dict/state passed forward), even ones built on LangGraph; even fake-news-agent's own roadmap lists true A2A as unbuilt | Use the hybrid blackboard pattern: a shared store for verified intermediate artifacts (claims, sources, verdicts-so-far) that any agent can read, while each agent's raw reasoning trace stays private — LangGraph's typed `State` object is the most controllable way to implement this without full framework lock-in |
| **No existing project combines fact-checking + bias/polarization scoring** | These are two separate lineages in the wild — classifiers do bias, agent pipelines do fact-checking, nobody's merged them live | This is a genuine novelty point for the project; the Cross-Checker + Bias/Blindspot Analyzer split (above) is the proposed way to combine them without one diluting the other |
| **Opposition agent, if prompted softly, won't actually disagree** | Empirically demonstrated (Inducing Disagreement paper): soft "be skeptical" instructions barely move disagreement rates | Prompt Opposition with a hard, unconditional mandate to argue against the claim/dominant framing — not a suggestion to be critical |
| **Kaggle Indian news dataset not yet pinned down** | Named in the spec but never resolved to an actual dataset in this research | Needs a dedicated Kaggle search pass (e.g. "Indian news headlines," "Times of India dataset," etc.) before data pipeline work starts |
| **No story/event clustering benchmark identified** | Clustering quality is unvalidated in every repo surveyed (HERALD uses simple TF-IDF with no accuracy claims) | If cross-language (English + regional Indian languages) clustering matters, plan to evaluate embedding-based clustering (multilingual sentence embeddings) against TF-IDF rather than assuming TF-IDF generalizes |
| **Audit log deliverable (from the original problem spec) has no existing-repo precedent** | None of the surveyed repos implement a formal audit log of agent decisions/evidence trail | Will likely need custom design — e.g. append-only log of each agent's tool calls, sources retrieved, and verdict changes per claim, keyed to the same cache/memory store used for duplicate-claim detection |
