"""SQLite-backed shared blackboard store.

Hybrid blackboard pattern (see docs/ARCHITECTURE.md): only verified,
structured artifacts are written here — each agent's raw reasoning trace
stays local to that agent. Any agent can read anything another agent wrote
via this store; nothing is passed linearly hand-to-hand.

Tables:
  claims       - one row per distinct claim string (hash-keyed id)
  findings     - Source-Finder's and Opposition's evidence for a claim
  verdicts     - Cross-Checker's adjudication for a claim
  bias_reports - Bias/Blindspot Analyzer's L/C/R spread + blindspot flags
  reports      - Writer's final merged report for a claim
  audit_log    - append-only event trail (every bb read/write, tool call, etc.)

This also doubles as the "don't re-investigate a checked claim" cache: check
`get_report()` (or `get_verdict()`) before running the graph at all.

Every read/write can be attributed to a calling agent via the `by=` argument;
when it is set and a reporter is attached, the store emits a `bb_read` /
`bb_write` event so the pipeline's inter-agent communication is observable.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from newsfact.observability.events import Event, EventKind, NullReporter, Reporter


def claim_id(claim_text: str) -> str:
    """Stable id for a claim string, used as the primary key everywhere."""
    normalized = " ".join(claim_text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Finding:
    claim_id: str
    role: str  # "source_finder" | "opposition"
    articles: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""  # short structured gloss (e.g. Opposition's counter-framing)
    created_at: float = field(default_factory=time.time)


@dataclass
class Verdict:
    claim_id: str
    label: str  # "corroborated" | "disputed" | "unverifiable"
    confidence: float
    reasoning: str
    created_at: float = field(default_factory=time.time)


@dataclass
class BiasReport:
    claim_id: str
    spread: dict[str, int]        # {"left": n, "center": n, "right": n, "unknown": n}
    outlets: list[dict[str, Any]]  # per-domain [{domain, name, bias, factuality, country, count}]
    blindspots: list[str]         # human-readable blindspot notes
    dominant_side: str            # "left" | "center" | "right" | "balanced" | "none"
    created_at: float = field(default_factory=time.time)


@dataclass
class Report:
    claim_id: str
    headline: str
    verdict_label: str
    verdict_confidence: float
    body_md: str
    created_at: float = field(default_factory=time.time)


SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    claim_id TEXT NOT NULL,
    role TEXT NOT NULL,
    articles_json TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (claim_id, role),
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE TABLE IF NOT EXISTS verdicts (
    claim_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE TABLE IF NOT EXISTS bias_reports (
    claim_id TEXT PRIMARY KEY,
    spread_json TEXT NOT NULL,
    outlets_json TEXT NOT NULL,
    blindspots_json TEXT NOT NULL,
    dominant_side TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE TABLE IF NOT EXISTS reports (
    claim_id TEXT PRIMARY KEY,
    headline TEXT NOT NULL,
    verdict_label TEXT NOT NULL,
    verdict_confidence REAL NOT NULL,
    body_md TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT,
    ts REAL NOT NULL,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_claim ON audit_log (claim_id, id);
"""


class BlackboardStore:
    """Thin wrapper around a SQLite file implementing the shared store."""

    def __init__(self, db_path: str | Path, reporter: Reporter | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._reporter: Reporter = reporter or NullReporter()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def set_reporter(self, reporter: Reporter) -> None:
        self._reporter = reporter

    @property
    def reporter(self) -> Reporter:
        return self._reporter

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Additive migrations for stores created by an older schema version."""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
        if "summary" not in cols:
            conn.execute("ALTER TABLE findings ADD COLUMN summary TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _emit(self, kind: str, agent: str, message: str, cid: str | None, **data: Any) -> None:
        self._reporter.emit(Event(kind=kind, agent=agent, message=message, claim_id=cid, data=data))

    # --- claims -----------------------------------------------------
    def ensure_claim(self, claim_text: str) -> str:
        cid = claim_id(claim_text)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO claims (id, text, created_at) VALUES (?, ?, ?)",
                (cid, claim_text, time.time()),
            )
        return cid

    def get_claim_text(self, cid: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT text FROM claims WHERE id = ?", (cid,)).fetchone()
        return row[0] if row else None

    # --- findings -----------------------------------------------------
    def write_finding(self, finding: Finding, by: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO findings (claim_id, role, articles_json, summary, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(claim_id, role) DO UPDATE SET
                       articles_json = excluded.articles_json,
                       summary = excluded.summary,
                       created_at = excluded.created_at""",
                (
                    finding.claim_id,
                    finding.role,
                    json.dumps(finding.articles),
                    finding.summary,
                    finding.created_at,
                ),
            )
        if by is not None:
            self._emit(
                EventKind.BB_WRITE, by,
                f"wrote {len(finding.articles)} article(s) as '{finding.role}'",
                finding.claim_id, role=finding.role, article_count=len(finding.articles),
            )

    def merge_finding(self, finding: Finding, by: str | None = None) -> Finding:
        """Union `finding.articles` into any existing row for the same
        (claim_id, role), de-duplicating on url (falling back to title). Used by
        the deep-research loop so a second evidence pass augments rather than
        replaces the first."""
        existing = self.get_findings(finding.claim_id, role=finding.role)
        merged: list[dict[str, Any]] = list(existing[0].articles) if existing else []
        seen = {(a.get("url") or a.get("title") or "").strip().lower() for a in merged}
        added = 0
        for a in finding.articles:
            key = (a.get("url") or a.get("title") or "").strip().lower()
            if key and key in seen:
                continue
            seen.add(key)
            merged.append(a)
            added += 1
        summary = finding.summary or (existing[0].summary if existing else "")
        row = Finding(claim_id=finding.claim_id, role=finding.role, articles=merged, summary=summary)
        self.write_finding(row)
        if by is not None:
            self._emit(
                EventKind.BB_WRITE, by,
                f"merged +{added} new article(s) into '{finding.role}' ({len(merged)} total)",
                finding.claim_id, role=finding.role, added=added, total=len(merged),
            )
        return row

    def get_findings(self, cid: str, role: str | None = None, by: str | None = None) -> list[Finding]:
        query = "SELECT claim_id, role, articles_json, summary, created_at FROM findings WHERE claim_id = ?"
        params: list[Any] = [cid]
        if role is not None:
            query += " AND role = ?"
            params.append(role)
        query += " ORDER BY role"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        findings = [
            Finding(claim_id=r[0], role=r[1], articles=json.loads(r[2]), summary=r[3], created_at=r[4])
            for r in rows
        ]
        if by is not None:
            total = sum(len(f.articles) for f in findings)
            scope = f"role='{role}'" if role else "all roles"
            self._emit(
                EventKind.BB_READ, by,
                f"read findings ({scope}): {len(findings)} row(s), {total} article(s)",
                cid, roles=[f.role for f in findings], article_count=total,
            )
        return findings

    # --- verdicts -----------------------------------------------------
    def write_verdict(self, verdict: Verdict, by: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO verdicts (claim_id, label, confidence, reasoning, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(claim_id) DO UPDATE SET
                       label = excluded.label,
                       confidence = excluded.confidence,
                       reasoning = excluded.reasoning,
                       created_at = excluded.created_at""",
                (
                    verdict.claim_id,
                    verdict.label,
                    verdict.confidence,
                    verdict.reasoning,
                    verdict.created_at,
                ),
            )
        if by is not None:
            self._emit(
                EventKind.BB_WRITE, by,
                f"wrote verdict '{verdict.label}' (confidence {verdict.confidence:.2f})",
                verdict.claim_id, label=verdict.label, confidence=verdict.confidence,
            )

    def get_verdict(self, cid: str, by: str | None = None) -> Verdict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT claim_id, label, confidence, reasoning, created_at FROM verdicts WHERE claim_id = ?",
                (cid,),
            ).fetchone()
        verdict = None if row is None else Verdict(
            claim_id=row[0], label=row[1], confidence=row[2], reasoning=row[3], created_at=row[4]
        )
        if by is not None:
            self._emit(
                EventKind.BB_READ, by,
                "read verdict: " + (f"'{verdict.label}'" if verdict else "none yet"),
                cid,
            )
        return verdict

    # --- bias reports -----------------------------------------------------
    def write_bias_report(self, report: BiasReport, by: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO bias_reports
                       (claim_id, spread_json, outlets_json, blindspots_json, dominant_side, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(claim_id) DO UPDATE SET
                       spread_json = excluded.spread_json,
                       outlets_json = excluded.outlets_json,
                       blindspots_json = excluded.blindspots_json,
                       dominant_side = excluded.dominant_side,
                       created_at = excluded.created_at""",
                (
                    report.claim_id,
                    json.dumps(report.spread),
                    json.dumps(report.outlets),
                    json.dumps(report.blindspots),
                    report.dominant_side,
                    report.created_at,
                ),
            )
        if by is not None:
            self._emit(
                EventKind.BB_WRITE, by,
                f"wrote bias report: dominant={report.dominant_side}, "
                f"{len(report.blindspots)} blindspot note(s)",
                report.claim_id, spread=report.spread, dominant_side=report.dominant_side,
            )

    def get_bias_report(self, cid: str, by: str | None = None) -> BiasReport | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT claim_id, spread_json, outlets_json, blindspots_json, dominant_side, created_at
                   FROM bias_reports WHERE claim_id = ?""",
                (cid,),
            ).fetchone()
        report = None if row is None else BiasReport(
            claim_id=row[0],
            spread=json.loads(row[1]),
            outlets=json.loads(row[2]),
            blindspots=json.loads(row[3]),
            dominant_side=row[4],
            created_at=row[5],
        )
        if by is not None:
            self._emit(EventKind.BB_READ, by, "read bias report", cid)
        return report

    # --- reports -----------------------------------------------------
    def write_report(self, report: Report, by: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reports
                       (claim_id, headline, verdict_label, verdict_confidence, body_md, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(claim_id) DO UPDATE SET
                       headline = excluded.headline,
                       verdict_label = excluded.verdict_label,
                       verdict_confidence = excluded.verdict_confidence,
                       body_md = excluded.body_md,
                       created_at = excluded.created_at""",
                (
                    report.claim_id,
                    report.headline,
                    report.verdict_label,
                    report.verdict_confidence,
                    report.body_md,
                    report.created_at,
                ),
            )
        if by is not None:
            self._emit(EventKind.BB_WRITE, by, "wrote final report", report.claim_id)

    def get_report(self, cid: str, by: str | None = None) -> Report | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT claim_id, headline, verdict_label, verdict_confidence, body_md, created_at
                   FROM reports WHERE claim_id = ?""",
                (cid,),
            ).fetchone()
        report = None if row is None else Report(
            claim_id=row[0],
            headline=row[1],
            verdict_label=row[2],
            verdict_confidence=row[3],
            body_md=row[4],
            created_at=row[5],
        )
        if by is not None:
            self._emit(EventKind.BB_READ, by, "read prior report (cache)", cid)
        return report

    # --- audit log -----------------------------------------------------
    def append_audit(self, event: Event) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (claim_id, ts, agent, kind, message, data_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.claim_id,
                    event.ts,
                    event.agent,
                    event.kind,
                    event.message,
                    json.dumps(event.data, default=str),
                ),
            )

    def get_audit(self, cid: str) -> list[Event]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT claim_id, ts, agent, kind, message, data_json FROM audit_log WHERE claim_id = ? ORDER BY id",
                (cid,),
            ).fetchall()
        return [
            Event(
                claim_id=r[0], ts=r[1], agent=r[2], kind=r[3], message=r[4],
                data=json.loads(r[5]) if r[5] else {},
            )
            for r in rows
        ]
