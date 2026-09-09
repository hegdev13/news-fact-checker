# Session logs

One file per work session that makes an architectural decision, not one per
commit. Name files `YYYY-MM-DD-short-slug.md`. Trivial sessions (typo fixes,
dependency bumps) don't need one — just a CHANGELOG entry.

Suggested shape for a session log:

```markdown
# 2026-09-09 — v1 scaffold

## What changed
...

## Decisions made (and why)
...

## Open questions for next session
...
```

Keep `docs/HANDOFF.md` as the single current-state source of truth; session
logs are the historical record of *why*, not a duplicate of *what's true now*.
