"""SQLite-backed shared blackboard store.

Hybrid blackboard pattern (see docs/ARCHITECTURE.md): only verified,
structured artifacts are written here — each agent's raw reasoning trace
stays local to that agent. Any agent can read anything another agent wrote
via this store; nothing is passed linearly hand-to-hand.

Three tables:
  claims    - one row per distinct claim string (hash-keyed id)
  findings  - Source-Finder's (and later, Opposition's) output for a claim
  verdicts  - Cross-Checker's output for a claim

This also doubles as the "don't re-investigate a checked claim" cache: check
`get_verdict()` before running the graph at all.
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


def claim_id(claim_text: str) -> str:
    """Stable id for a claim string, used as the primary key everywhere."""
    normalized = " ".join(claim_text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Finding:
    claim_id: str
    role: str  # "source_finder" today; "opposition" once that agent exists
    articles: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class Verdict:
    claim_id: str
    label: str  # "corroborated" | "disputed" | "unverifiable"
    confidence: float
    reasoning: str
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
"""


class BlackboardStore:
    """Thin wrapper around a SQLite file implementing the shared store."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- claims -----------------------------------------------------
    def ensure_claim(self, claim_text: str) -> str:
        cid = claim_id(claim_text)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO claims (id, text, created_at) VALUES (?, ?, ?)",
                (cid, claim_text, time.time()),
            )
        return cid

    # --- findings -----------------------------------------------------
    def write_finding(self, finding: Finding) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO findings (claim_id, role, articles_json, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(claim_id, role) DO UPDATE SET
                       articles_json = excluded.articles_json,
                       created_at = excluded.created_at""",
                (
                    finding.claim_id,
                    finding.role,
                    json.dumps(finding.articles),
                    finding.created_at,
                ),
            )

    def get_findings(self, cid: str, role: str | None = None) -> list[Finding]:
        query = "SELECT claim_id, role, articles_json, created_at FROM findings WHERE claim_id = ?"
        params: list[Any] = [cid]
        if role is not None:
            query += " AND role = ?"
            params.append(role)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            Finding(claim_id=r[0], role=r[1], articles=json.loads(r[2]), created_at=r[3])
            for r in rows
        ]

    # --- verdicts -----------------------------------------------------
    def write_verdict(self, verdict: Verdict) -> None:
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

    def get_verdict(self, cid: str) -> Verdict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT claim_id, label, confidence, reasoning, created_at FROM verdicts WHERE claim_id = ?",
                (cid,),
            ).fetchone()
        if row is None:
            return None
        return Verdict(claim_id=row[0], label=row[1], confidence=row[2], reasoning=row[3], created_at=row[4])
