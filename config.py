"""Application configuration models and persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


APP_NAME = "Network Monitor"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "settings.json"
DB_PATH = DATA_DIR / "network.db"


@dataclass(slots=True)
class Thresholds:
    """Thresholds used for network status classification."""

    ping_warning_ms: float = 100.0
    packet_loss_warning_percent: float = 5.0
    download_drop_ratio: float = 0.20
    offline_failed_pings: int = 3


@dataclass(slots=True)
class AppConfig:
    """User-configurable app settings."""

    ping_host: str = "8.8.8.8"
    ping_interval_seconds: float = 1.0
    speedtest_interval_seconds: float = 60.0
    theme: str = "dark"
    thresholds: Thresholds = field(default_factory=Thresholds)


def ensure_directories() -> None:
    """Create runtime directories if they do not exist."""

    for directory in (DATA_DIR, EXPORT_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """Load settings from disk, falling back to defaults."""

    if not CONFIG_FILE.exists():
        return AppConfig()

    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        threshold_raw: dict[str, Any] = raw.pop("thresholds", {})
        return AppConfig(
            **raw,
            thresholds=Thresholds(**threshold_raw),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return AppConfig()


def save_config(config: AppConfig) -> None:
    """Persist settings to disk."""

    CONFIG_FILE.write_text(
        json.dumps(asdict(config), indent=2),
        encoding="utf-8",
    )
