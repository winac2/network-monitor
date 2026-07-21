"""Network monitoring workers and status classification."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import logging
import queue
import statistics
import threading
import time

import psutil

from config import AppConfig
from database import EventRecord, NetworkSample

try:
    from ping3 import ping
except ImportError:  # pragma: no cover
    ping = None

try:
    import speedtest
except ImportError:  # pragma: no cover
    speedtest = None


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class MonitorState:
    """Mutable state owned by monitor workers."""

    download: float | None = None
    upload: float | None = None
    speedtest_download: float | None = None
    speedtest_upload: float | None = None
    rolling_downloads: deque[float] | None = None
    ping_history: deque[float | None] | None = None
    last_bytes_recv: int | None = None
    last_bytes_sent: int | None = None
    last_io_time: float | None = None
    failed_pings: int = 0
    status: str = "OFFLINE"

    def __post_init__(self) -> None:
        self.rolling_downloads = self.rolling_downloads or deque(maxlen=20)
        self.ping_history = self.ping_history or deque(maxlen=100)


class NetworkMonitor:
    """Coordinates ping and speed test worker threads."""

    def __init__(
        self,
        config: AppConfig,
        ui_queue: queue.Queue[object],
        db_queue: queue.Queue[object],
    ) -> None:
        self.config = config
        self.ui_queue = ui_queue
        self.db_queue = db_queue
        self.state = MonitorState()
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Start all monitor workers."""

        if self._threads:
            return
        self._threads = [
            threading.Thread(target=self._ping_loop, name="PingWorker", daemon=True),
            threading.Thread(target=self._speedtest_loop, name="SpeedtestWorker", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        """Signal workers to stop."""

        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=2)

    def update_config(self, config: AppConfig) -> None:
        """Apply changed settings."""

        self.config = config

    def _ping_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            ping_ms = self._measure_ping()
            download_mbps, upload_mbps = self._measure_live_throughput()
            sample = self._build_sample(ping_ms, download_mbps, upload_mbps)
            self.ui_queue.put(sample)
            self.db_queue.put(sample)
            elapsed = time.monotonic() - started
            sleep_for = max(0.1, self.config.ping_interval_seconds - elapsed)
            self._stop_event.wait(sleep_for)

    def _speedtest_loop(self) -> None:
        while not self._stop_event.is_set():
            download, upload = self._measure_speed_with_retry()
            with self._state_lock:
                self.state.speedtest_download = download
                self.state.speedtest_upload = upload
            self._stop_event.wait(self.config.speedtest_interval_seconds)

    def _measure_live_throughput(self) -> tuple[float, float]:
        """Return current receive/transmit throughput in Mbps."""

        try:
            counters = psutil.net_io_counters()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Network I/O counters unavailable: %s", exc)
            return 0.0, 0.0

        now = time.monotonic()
        with self._state_lock:
            if (
                self.state.last_bytes_recv is None
                or self.state.last_bytes_sent is None
                or self.state.last_io_time is None
            ):
                self.state.last_bytes_recv = counters.bytes_recv
                self.state.last_bytes_sent = counters.bytes_sent
                self.state.last_io_time = now
                return 0.0, 0.0

            elapsed = max(now - self.state.last_io_time, 0.001)
            recv_delta = max(counters.bytes_recv - self.state.last_bytes_recv, 0)
            sent_delta = max(counters.bytes_sent - self.state.last_bytes_sent, 0)
            self.state.last_bytes_recv = counters.bytes_recv
            self.state.last_bytes_sent = counters.bytes_sent
            self.state.last_io_time = now

        download_mbps = recv_delta * 8 / elapsed / 1_000_000
        upload_mbps = sent_delta * 8 / elapsed / 1_000_000
        return round(download_mbps, 2), round(upload_mbps, 2)

    def _measure_ping(self) -> float | None:
        if ping is None:
            LOGGER.warning("ping3 is unavailable")
            return None
        try:
            result = ping(self.config.ping_host, timeout=1, unit="ms")
            return float(result) if result is not None else None
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Ping failed: %s", exc)
            return None

    def _measure_speed_with_retry(self) -> tuple[float | None, float | None]:
        for attempt in range(3):
            try:
                return self._measure_speed()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Speed test failed on attempt %s: %s", attempt + 1, exc)
                self._stop_event.wait(5)
        return None, None

    def _measure_speed(self) -> tuple[float | None, float | None]:
        if speedtest is None:
            LOGGER.warning("speedtest-cli is unavailable")
            return None, None
        tester = speedtest.Speedtest()
        tester.get_best_server()
        download_mbps = tester.download() / 1_000_000
        upload_mbps = tester.upload() / 1_000_000
        return round(download_mbps, 2), round(upload_mbps, 2)

    def _build_sample(self, ping_ms: float | None, download_mbps: float, upload_mbps: float) -> NetworkSample:
        with self._state_lock:
            assert self.state.ping_history is not None
            assert self.state.rolling_downloads is not None
            self.state.ping_history.append(ping_ms)
            self.state.failed_pings = self.state.failed_pings + 1 if ping_ms is None else 0
            self.state.download = download_mbps
            self.state.upload = upload_mbps
            self.state.rolling_downloads.append(download_mbps)

            successful_pings = [value for value in self.state.ping_history if value is not None]
            jitter = statistics.pstdev(successful_pings[-10:]) if len(successful_pings) > 1 else 0.0
            packet_loss = (
                sum(1 for value in self.state.ping_history if value is None)
                / len(self.state.ping_history)
                * 100
            )
            status = self._classify_status(ping_ms, packet_loss)
            previous = self.state.status
            self.state.status = status
            sample = NetworkSample(
                timestamp=datetime.now(),
                download=download_mbps,
                upload=upload_mbps,
                ping=ping_ms,
                jitter=round(jitter, 2),
                packet_loss=round(packet_loss, 2),
                status=status,
            )

        if previous != status:
            event = EventRecord(
                timestamp=sample.timestamp,
                message=f"Network status changed from {previous} to {status}",
                status=status,
            )
            self.ui_queue.put(event)
            self.db_queue.put(event)
        return sample

    def _classify_status(self, ping_ms: float | None, packet_loss: float) -> str:
        thresholds = self.config.thresholds
        if self.state.failed_pings >= thresholds.offline_failed_pings:
            return "OFFLINE"

        congested = False
        if ping_ms is not None and ping_ms > thresholds.ping_warning_ms:
            congested = True
        if packet_loss > thresholds.packet_loss_warning_percent:
            congested = True

        if self.state.download is not None and self.state.rolling_downloads:
            rolling_average = statistics.fmean(self.state.rolling_downloads)
            if rolling_average > 0 and self.state.download < rolling_average * thresholds.download_drop_ratio:
                congested = True

        if congested:
            return "CONGESTED"
        if ping_ms is None:
            return "WARNING"
        return "GOOD"
