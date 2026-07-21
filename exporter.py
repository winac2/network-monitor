"""Export samples and compute statistics."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import statistics
from typing import Any

import pandas as pd

from database import Database, NetworkSample


class Exporter:
    """CSV/XLSX exporter for selected date ranges."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def export_csv(self, start: datetime | None, end: datetime | None, path: Path) -> Path:
        """Export samples to CSV."""

        frame = self._frame(start, end)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return path

    def export_xlsx(self, start: datetime | None, end: datetime | None, path: Path) -> Path:
        """Export samples to XLSX."""

        frame = self._frame(start, end)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_excel(path, index=False)
        return path

    def _frame(self, start: datetime | None, end: datetime | None) -> pd.DataFrame:
        records = [asdict(sample) for sample in self.db.fetch_samples(start, end)]
        return pd.DataFrame.from_records(records)


def calculate_statistics(samples: list[NetworkSample]) -> dict[str, Any]:
    """Calculate summary statistics for network samples."""

    values = {
        "download": [sample.download for sample in samples if sample.download is not None],
        "upload": [sample.upload for sample in samples if sample.upload is not None],
        "ping": [sample.ping for sample in samples if sample.ping is not None],
        "jitter": [sample.jitter for sample in samples],
        "packet_loss": [sample.packet_loss for sample in samples],
    }

    output: dict[str, Any] = {}
    for name, series in values.items():
        if not series:
            output[name] = {"average": None, "minimum": None, "maximum": None, "median": None, "p95": None}
            continue
        sorted_series = sorted(series)
        p95_index = min(len(sorted_series) - 1, int(len(sorted_series) * 0.95))
        output[name] = {
            "average": round(statistics.fmean(series), 2),
            "minimum": round(min(series), 2),
            "maximum": round(max(series), 2),
            "median": round(statistics.median(series), 2),
            "p95": round(sorted_series[p95_index], 2),
        }

    offline_seconds = 0.0
    previous: NetworkSample | None = None
    for sample in samples:
        if previous is not None and previous.status == "OFFLINE":
            offline_seconds += (sample.timestamp - previous.timestamp).total_seconds()
        previous = sample
    output["downtime_duration_seconds"] = round(offline_seconds, 2)
    return output
