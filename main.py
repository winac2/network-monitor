"""Application entry point."""

from __future__ import annotations

import queue

from config import DB_PATH, ensure_directories, load_config
from database import Database, DatabaseWriter
from logging_config import configure_logging
from monitor import NetworkMonitor
from ui import NetworkMonitorApp


def main() -> None:
    """Start the Network Monitor desktop app."""

    ensure_directories()
    configure_logging()
    config = load_config()
    database = Database(DB_PATH)
    ui_queue: queue.Queue[object] = queue.Queue()
    db_queue: queue.Queue[object] = queue.Queue()
    db_writer = DatabaseWriter(database, db_queue)
    db_writer.start()
    monitor = NetworkMonitor(config, ui_queue, db_queue)
    app = NetworkMonitorApp(config, database, monitor, ui_queue)
    try:
        app.mainloop()
    finally:
        monitor.stop()
        db_writer.stop()


if __name__ == "__main__":
    main()
