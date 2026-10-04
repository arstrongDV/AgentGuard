"""Audit log: SQLite (queryable, feeds the dashboard) + JSONL (append-only, grep/SIEM friendly).

Writes are tiny and local, so a synchronous sqlite3 connection behind a lock is fast enough here
(well under a millisecond per event) and keeps the dependency list short.
"""

import json
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path

from app.core.events import AuditEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    direction TEXT NOT NULL,
    decision TEXT NOT NULL,
    risk REAL NOT NULL,
    categories TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS idx_events_agent_ts ON events (agent_id, ts);
"""


class AuditStore:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "audit.db"
        self.jsonl_path = data_dir / "audit.jsonl"
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self._jsonl = self.jsonl_path.open("a", encoding="utf-8")

    def record(self, event: AuditEvent) -> None:
        payload = event.model_dump_json()
        categories = "," + ",".join(sorted({f.category for f in event.findings})) + ","
        with self._lock:
            self._db.execute(
                "INSERT INTO events (id, ts, agent_id, channel, direction, decision, risk, categories, payload) VALUES (?,?,?,?,?,?,?,?,?)",
                (event.id, event.ts, event.agent_id, event.channel, event.direction, event.decision.value, event.risk, categories, payload),
            )
            self._db.commit()
            self._jsonl.write(payload + "\n")
            self._jsonl.flush()

    def get(self, event_id: str) -> AuditEvent | None:
        with self._lock:
            row = self._db.execute("SELECT payload FROM events WHERE id = ?", (event_id,)).fetchone()
        return AuditEvent.model_validate_json(row[0]) if row else None

    def query(
        self,
        *,
        limit: int = 100,
        before_id: str | None = None,
        after_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        agent: str | None = None,
        decision: str | None = None,
        category: str | None = None,
        channel: str | None = None,
        task: str | None = None,
        ascending: bool = False,
    ) -> list[AuditEvent]:
        where, params = [], []
        if before_id:
            where.append("id < ?")
            params.append(before_id)
        if after_id:
            where.append("id > ?")
            params.append(after_id)
        if since:
            where.append("ts >= ?")
            params.append(since)
        if until:
            where.append("ts <= ?")
            params.append(until)
        if agent:
            where.append("agent_id = ?")
            params.append(agent)
        if decision:
            where.append("decision = ?")
            params.append(decision)
        if category:
            where.append("categories LIKE ?")
            params.append(f"%,{category},%")
        if channel:
            where.append("channel = ?")
            params.append(channel)
        if task:
            where.append("json_extract(payload, '$.task_id') = ?")
            params.append(task)
        sql = "SELECT payload FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY id {'ASC' if ascending else 'DESC'} LIMIT ?"  # ULIDs sort by creation time
        params.append(limit)
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [AuditEvent.model_validate_json(r[0]) for r in rows]

    def iterate(self, *, batch: int = 500, **filters: str | None) -> Iterator[AuditEvent]:
        """Oldest first, in batches, for streaming exports. Filters as in query()."""
        cursor = None
        while True:
            rows = self.query(limit=batch, after_id=cursor, ascending=True, **filters)
            yield from rows
            if len(rows) < batch:
                return
            cursor = rows[-1].id

    def close(self) -> None:
        with self._lock:
            self._db.close()
            self._jsonl.close()
