"""Observability layer: the event stream every agent and the shared store emit,
plus the sinks that consume it (the live terminal dashboard and the append-only
audit log).

This is what makes the multi-agent pipeline *visible*: agents don't just talk to
each other through the blackboard, every read and write on that blackboard —
plus every agent start/finish and every external tool call — is published as an
`Event` that the console renders live and the audit log persists.
"""
from newsfact.observability.events import (
    AuditLogReporter,
    Event,
    EventKind,
    MultiReporter,
    NullReporter,
    Reporter,
)

__all__ = [
    "AuditLogReporter",
    "Event",
    "EventKind",
    "MultiReporter",
    "NullReporter",
    "Reporter",
]
