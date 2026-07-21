"""Create sample database rows and a sample CSV export."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH, EXPORT_DIR, ensure_directories  # noqa: E402
from database import Database, EventRecord, NetworkSample, seed_samples  # noqa: E402
from exporter import Exporter  # noqa: E402


def build_samples() -> list[NetworkSample]:
    """Build deterministic sample records covering normal and degraded states."""

    start = datetime.now() - timedelta(minutes=30)
    samples: list[NetworkSample] = []
    for index in range(60):
        timestamp = start + timedelta(seconds=index * 30)
        ping = 32 + math.sin(index / 4) * 6
        download = 92 + math.sin(index / 5) * 8
        upload = 31 + math.cos(index / 6) * 3
        loss = 0.0
        status = "GOOD"
        if 34 <= index <= 39:
            ping = 145 + index
            download = 14
            loss = 8.0
            status = "CONGESTED"
        if 48 <= index <= 50:
            ping = None
            download = 0
            upload = 0
            loss = 12.0
            status = "OFFLINE"

        samples.append(
            NetworkSample(
                timestamp=timestamp,
                download=round(download, 2),
                upload=round(upload, 2),
                ping=None if ping is None else round(ping, 2),
                jitter=round(2.5 + abs(math.sin(index / 3)), 2),
                packet_loss=loss,
                status=status,
            )
        )
    return samples


def main() -> None:
    ensure_directories()
    if DB_PATH.exists():
        DB_PATH.unlink()
    db = Database(DB_PATH)
    samples = build_samples()
    seed_samples(db, samples)
    db.insert_event(
        EventRecord(
            timestamp=samples[34].timestamp,
            message="Sample data: congestion detected",
            status="CONGESTED",
        )
    )
    db.insert_event(
        EventRecord(
            timestamp=samples[51].timestamp,
            message="Sample data: network recovered",
            status="GOOD",
        )
    )
    Exporter(db).export_csv(None, None, EXPORT_DIR / "sample_network_export.csv")


if __name__ == "__main__":
    main()
