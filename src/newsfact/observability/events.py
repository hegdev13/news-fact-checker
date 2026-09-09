"""Event model + reporter sinks.

An `Event` is a single observable thing that happened in the pipeline. Agents
and the `BlackboardStore` construct events and hand them to a `Reporter`; the
reporter decides what to do with them (draw them, persist them, ignore them).

Design notes
------------
* Reporters must never raise. A broken dashboard or a locked audit-log DB should
  degrade the run to "less visible", never crash the fact-check.
* `Reporter` is a runtime-checkable Protocol so tests can pass a bare object
  with an `emit` method, and so `NullReporter()` is a valid default argument
  everywhere without importing a concrete class.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# --- event kinds -------------------------------------------------------------
# Kept as plain string constants (not an Enum) so events serialize to the audit
# log and cross a future process/HTTP boundary without custom encoders.


class EventKind:
    ITEM_START = "item_start"        # began processing one news item / claim
    ITEM_DONE = "item_done"          # finished one news item (report written or cache hit)
    AGENT_START = "agent_start"      # an agent began its turn
    AGENT_DONE = "agent_done"        # an agent finished its turn
    TOOL_CALL = "tool_call"          # an agent called an external tool (GDELT, bias table, LLM)
    BB_WRITE = "bb_write"            # an artifact was written to the shared blackboard
    BB_READ = "bb_read"             # an agent read an artifact from the shared blackboard
    NOTE = "note"                    # free-text progress note from an agent
    LOOP = "loop"                    # the deep-research loop (re)triggered
    REPORT = "report"               # the final report for an item is ready
    ERROR = "error"                  # a non-fatal error the pipeline recovered from


AGENTS = (
    "claim_extractor",   # article-input mode only (v2.1); skipped in claim mode
    "source_finder",
    "opposition",
    "cross_checker",
    "bias_analyzer",
    "writer",
)


@dataclass(frozen=True)
class Event:
    kind: str
    agent: str                      # one of AGENTS, or "orchestrator"
    message: str
    claim_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


# --- reporter protocol + sinks --------------------------------------------------


@runtime_checkable
class Reporter(Protocol):
    def emit(self, event: Event) -> None: ...


class NullReporter:
    """Default sink: drops every event. Used everywhere a reporter is optional."""

    def emit(self, event: Event) -> None:  # noqa: D401 - trivial
        return None


class MultiReporter:
    """Fan an event out to several sinks. One sink raising never stops the others."""

    def __init__(self, sinks: list[Reporter]):
        self._sinks = list(sinks)

    def add(self, sink: Reporter) -> None:
        self._sinks.append(sink)

    def emit(self, event: Event) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:  # noqa: BLE001 - observability must not break the run
                continue


class AuditLogReporter:
    """Persists every event as an append-only row in the shared store's
    `audit_log` table — the formal audit trail called for in the resource doc
    (append-only log of each agent's tool calls, sources retrieved, and verdict
    changes per claim, keyed to the same store used for duplicate detection)."""

    def __init__(self, store: Any):
        self._store = store

    def emit(self, event: Event) -> None:
        try:
            self._store.append_audit(event)
        except Exception:  # noqa: BLE001
            return None
