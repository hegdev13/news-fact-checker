"""Live terminal dashboard for a pipeline run.

`ConsoleReporter` is an event sink (a `Reporter`) that renders the 5 agents,
the shared blackboard, and a streaming event log in a single `rich.Live`
region, then prints each finished item's report into the scrollback above it.

Use it as a context manager:

    with ConsoleReporter(Console()) as reporter:
        run_pipeline(claim, store, gdelt, llm, bias_table, reporter)

Falls back to plain line-by-line printing when `plain=True` or stdout is not a
TTY, so piping to a file still produces a readable trace.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from newsfact.observability.events import AGENTS, Event, EventKind

_AGENT_LABELS = {
    "claim_extractor": "Claim Extractor",
    "source_finder": "Source-Finder",
    "opposition": "Opposition",
    "cross_checker": "Cross-Checker",
    "bias_analyzer": "Bias/Blindspot",
    "writer": "Writer",
    "orchestrator": "Orchestrator",
}
_STATUS_ICON = {"pending": "•", "running": "▶", "done": "✓", "error": "!"}
_STATUS_STYLE = {"pending": "dim", "running": "bold yellow", "done": "bold green", "error": "bold red"}
_KIND_STYLE = {
    EventKind.AGENT_START: "yellow",
    EventKind.AGENT_DONE: "green",
    EventKind.TOOL_CALL: "cyan",
    EventKind.BB_WRITE: "magenta",
    EventKind.BB_READ: "blue",
    EventKind.NOTE: "white",
    EventKind.LOOP: "bold yellow",
    EventKind.REPORT: "bold green",
    EventKind.ERROR: "bold red",
    EventKind.ITEM_START: "bold",
    EventKind.ITEM_DONE: "bold green",
}
_LABEL_STYLE = {"corroborated": "bold green", "disputed": "bold yellow", "unverifiable": "bold red"}


class ConsoleReporter:
    def __init__(self, console: Console | None = None, plain: bool = False):
        self.console = console or Console()
        self.plain = plain or not self.console.is_terminal
        self._live: Live | None = None

        self._item_no = 0
        self._item_total = 0
        self._claim = ""
        self._agents: dict[str, dict[str, Any]] = {}
        self._bb: dict[str, str] = {}
        self._log: deque[Text] = deque(maxlen=16)
        self._reset_item_state()

    # -- lifecycle -------------------------------------------------------
    def set_total(self, total: int) -> None:
        self._item_total = total

    def __enter__(self) -> "ConsoleReporter":
        if not self.plain:
            self._live = Live(self._render(), console=self.console, refresh_per_second=12, screen=False)
            self._live.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._live is not None:
            self._live.__exit__(*exc)
            self._live = None

    # -- event sink ----------------------------------------------------
    def emit(self, event: Event) -> None:
        if event.kind == EventKind.ITEM_START:
            self._item_no += 1
            self._claim = event.message
            self._reset_item_state()
            self._rule(f"[{self._item_no}/{self._item_total or '?'}] {event.message}")
        elif event.kind == EventKind.AGENT_START:
            self._set_agent(event.agent, "running", event.message)
        elif event.kind == EventKind.AGENT_DONE:
            self._set_agent(event.agent, "done", event.message)
        elif event.kind == EventKind.ERROR:
            self._set_agent(event.agent, "error", event.message)
        elif event.kind in (EventKind.TOOL_CALL, EventKind.NOTE, EventKind.LOOP):
            self._touch_agent(event.agent, event.message)

        if event.kind in (EventKind.BB_WRITE, EventKind.BB_READ):
            self._update_blackboard(event)
        if event.kind == EventKind.REPORT:
            self._bb["report"] = event.message

        self._append_log(event)

        if event.kind == EventKind.ITEM_DONE:
            self._flush_report()

        self._refresh()

    # -- internal state ------------------------------------------------
    def _reset_item_state(self) -> None:
        self._agents = {a: {"status": "pending", "last": ""} for a in AGENTS}
        self._bb = {}
        self._log.clear()

    def _set_agent(self, role: str, status: str, last: str) -> None:
        if role not in self._agents:
            return
        self._agents[role]["status"] = status
        self._agents[role]["last"] = last

    def _touch_agent(self, role: str, last: str) -> None:
        if role in self._agents:
            if self._agents[role]["status"] == "pending":
                self._agents[role]["status"] = "running"
            self._agents[role]["last"] = last

    def _update_blackboard(self, event: Event) -> None:
        d = event.data or {}
        role = d.get("role")
        if event.kind == EventKind.BB_WRITE and event.agent == "claim_extractor":
            method = d.get("origin_method", "none")
            self._bb["source"] = (
                f"{d.get('origin_domain', 'unknown')} (via {method})" if method != "none"
                else "origin outlet not identified"
            )
        elif event.kind == EventKind.BB_WRITE and role in ("source_finder", "opposition"):
            n = d.get("article_count", d.get("total", "?"))
            self._bb[role] = f"{n} articles"
        elif event.kind == EventKind.BB_WRITE and "label" in d:
            self._bb["verdict"] = f"{d['label']} ({float(d.get('confidence', 0)):.2f})"
        elif event.kind == EventKind.BB_WRITE and "spread" in d:
            s = d["spread"]
            self._bb["bias"] = f"L/C/R {s.get('left', 0)}/{s.get('center', 0)}/{s.get('right', 0)} (+{s.get('unknown', 0)})"

    def _append_log(self, event: Event) -> None:
        style = _KIND_STYLE.get(event.kind, "white")
        line = Text.assemble(
            (f"{_AGENT_LABELS.get(event.agent, event.agent):<13} ", "dim"),
            (f"{event.kind:<11} ", style),
            (event.message, ""),
        )
        self._log.append(line)
        if self.plain:
            self.console.print(line)

    # -- rendering ---------------------------------------------------
    def _render(self) -> Group:
        header = Panel(
            Text(self._claim or "waiting…", style="bold"),
            title=f"News item {self._item_no}/{self._item_total or '?'}",
            border_style="cyan",
        )

        agents = Table(show_header=True, header_style="dim", box=None, pad_edge=False, expand=True)
        agents.add_column("", width=2)
        agents.add_column("Agent", width=14)
        agents.add_column("Last action", overflow="fold")
        for role in AGENTS:
            st = self._agents[role]["status"]
            # Claim Extractor only runs in article-input mode — hide its row in
            # claim mode (where it never emits an event and stays pending).
            if role == "claim_extractor" and st == "pending" and not self._agents[role]["last"]:
                continue
            agents.add_row(
                Text(_STATUS_ICON[st], style=_STATUS_STYLE[st]),
                Text(_AGENT_LABELS[role], style=_STATUS_STYLE[st]),
                Text(self._agents[role]["last"] or "—", style="dim" if st == "pending" else ""),
            )

        bb = Table(show_header=False, box=None, pad_edge=False, expand=True)
        bb.add_column("k", style="dim", width=14)
        bb.add_column("v", overflow="fold")
        for key in ("source", "source_finder", "opposition", "verdict", "bias", "report"):
            if key in self._bb:
                label = "Submitted src" if key == "source" else _AGENT_LABELS.get(key, key.replace("_", " "))
                bb.add_row(label, self._bb[key])
        if not self._bb:
            bb.add_row("—", "nothing written yet")

        log = Group(*self._log) if self._log else Text("…", style="dim")

        return Group(
            header,
            Panel(agents, title="Agents", border_style="dim"),
            Panel(bb, title="Shared blackboard", border_style="dim"),
            Panel(log, title="Event stream (agent ↔ blackboard)", border_style="dim"),
        )

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def _rule(self, text: str) -> None:
        target = self._live.console if self._live is not None else self.console
        target.print(Rule(text, style="cyan"))

    def _flush_report(self) -> None:
        target = self._live.console if self._live is not None else self.console
        headline = self._bb.get("report", "(no report)")
        verdict = self._bb.get("verdict", "n/a")
        target.print(Panel(
            Text.assemble((headline + "\n", "bold"), ("verdict on blackboard: ", "dim"), (verdict, "")),
            title=f"Report — item {self._item_no}", border_style="green",
        ))


def render_report_panel(headline: str, label: str, confidence: float, body_md: str) -> Panel:
    """Full final report, used for the end-of-run recap."""
    title = Text.assemble(
        (headline + "  ", "bold"),
        (f"[{label} {confidence:.0%}]", _LABEL_STYLE.get(label, "bold")),
    )
    return Panel(Markdown(body_md), title=title, border_style=_LABEL_STYLE.get(label, "cyan"), padding=(1, 2))
