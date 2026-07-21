"""SQLite storage for network samples and event history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import queue
import sqlite3
import threading
from typing import Iterable


@dataclass(slots=True)
class NetworkSample:
    """Single network measurement."""

    timestamp: datetime
    download: float | None
    upload: float | None
    ping: float | None
    jitter: float
    packet_loss: float
    status: str


@dataclass(slots=True)
class EventRecord:
    """Network state transition or notable warning."""

    timestamp: datetime
    message: str
    status: str


class Database:
    """Small SQLite wrapper used by UI, exporter, and logger thread."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.initialize()

    def initialize(self) -> None:
        """Create database tables."""

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME,
                    download REAL,
                    upload REAL,
                    ping REAL,
                    jitter REAL,
                    packet_loss REAL,
                    status TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME,
                    message TEXT,
                    status TEXT
                )
                """
            )

    def insert_sample(self, sample: NetworkSample) -> None:
        """Insert one sample."""

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO samples
                (timestamp, download, upload, ping, jitter, packet_loss, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample.timestamp.isoformat(timespec="seconds"),
                    sample.download,
                    sample.upload,
                    sample.ping,
                    sample.jitter,
                    sample.packet_loss,
                    sample.status,
                ),
            )

    def insert_event(self, event: EventRecord) -> None:
        """Insert one event log row."""

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (timestamp, message, status)
                VALUES (?, ?, ?)
                """,
                (
                    event.timestamp.isoformat(timespec="seconds"),
                    event.message,
                    event.status,
                ),
            )

    def fetch_samples(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[NetworkSample]:
        """Fetch samples ordered by timestamp ascending."""

        clauses: list[str] = []
        params: list[object] = []
        if start is not None:
            clauses.append("timestamp >= ?")
            params.append(start.isoformat(timespec="seconds"))
        if end is not None:
            clauses.append("timestamp <= ?")
            params.append(end.isoformat(timespec="seconds"))

        query = "SELECT timestamp, download, upload, ping, jitter, packet_loss, status FROM samples"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            NetworkSample(
                timestamp=datetime.fromisoformat(row[0]),
                download=row[1],
                upload=row[2],
                ping=row[3],
                jitter=row[4] or 0.0,
                packet_loss=row[5] or 0.0,
                status=row[6],
            )
            for row in rows
        ]

    def fetch_recent_events(self, limit: int = 100) -> list[EventRecord]:
        """Fetch recent events newest first."""

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, message, status
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            EventRecord(
                timestamp=datetime.fromisoformat(row[0]),
                message=row[1],
                status=row[2],
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)


class DatabaseWriter(threading.Thread):
    """Background database writer fed by a queue."""

    def __init__(self, db: Database, write_queue: queue.Queue[object]) -> None:
        super().__init__(daemon=True)
        self.db = db
        self.write_queue = write_queue
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self.write_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if isinstance(item, NetworkSample):
                    self.db.insert_sample(item)
                elif isinstance(item, EventRecord):
                    self.db.insert_event(item)
            finally:
                self.write_queue.task_done()

    def stop(self) -> None:
        self._stop_event.set()


def seed_samples(db: Database, samples: Iterable[NetworkSample]) -> None:
    """Insert seed data."""

    for sample in samples:
        db.insert_sample(sample)
