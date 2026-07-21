"""Desktop notification wrapper with graceful fallback."""

from __future__ import annotations

import logging

try:
    from plyer import notification
except ImportError:  # pragma: no cover
    notification = None


LOGGER = logging.getLogger(__name__)


class Notifier:
    """Sends state-change notifications without making UI code depend on plyer."""

    def __init__(self) -> None:
        self._last_status = ""

    def handle_status(self, status: str) -> None:
        """Notify only when entering meaningful network states."""

        if status == self._last_status:
            return
        previous = self._last_status
        self._last_status = status

        if status == "OFFLINE":
            self.send("Network offline", "Three consecutive pings failed.")
        elif status == "CONGESTED":
            self.send("Network congestion detected", "Latency, packet loss, or throughput crossed a threshold.")
        elif previous in {"OFFLINE", "CONGESTED"} and status == "GOOD":
            self.send("Network recovered", "Connection quality is back to normal.")

    def send(self, title: str, message: str) -> None:
        """Send a desktop notification if the optional dependency is available."""

        if notification is None:
            LOGGER.info("%s: %s", title, message)
            return
        try:
            notification.notify(title=title, message=message, app_name="Network Monitor", timeout=5)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Notification failed: %s", exc)
