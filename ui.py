"""CustomTkinter user interface."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import platform
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from config import AppConfig, EXPORT_DIR, save_config
from database import Database, EventRecord, NetworkSample
from exporter import Exporter, calculate_statistics
from graph import LiveCharts
from monitor import NetworkMonitor
from notifications import Notifier


STATUS_COLORS = {
    "GOOD": "#2f9e44",
    "WARNING": "#f08c00",
    "CONGESTED": "#c92a2a",
    "OFFLINE": "#868e96",
}


class NetworkMonitorApp(ctk.CTk):
    """Main application window."""

    def __init__(
        self,
        config: AppConfig,
        database: Database,
        monitor: NetworkMonitor,
        ui_queue: queue.Queue[object],
    ) -> None:
        super().__init__()
        self.config_data = config
        self.database = database
        self.monitor = monitor
        self.ui_queue = ui_queue
        self.exporter = Exporter(database)
        self.notifier = Notifier(enabled=self.config_data.desktop_notifications_enabled)
        self.kpis: dict[str, ctk.CTkLabel] = {}
        self.status_label: ctk.CTkLabel | None = None
        self.event_log: ctk.CTkTextbox | None = None
        self.stats_box: ctk.CTkTextbox | None = None
        self.charts: LiveCharts | None = None
        self.current_page = ""
        self.latest_sample: NetworkSample | None = None
        self.content = ctk.CTkFrame(self, corner_radius=0)

        ctk.set_appearance_mode(self.config_data.theme)
        ctk.set_default_color_theme("blue")
        self.title("Network Monitor")
        self.geometry("1280x820")
        self.minsize(980, 680)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_layout()
        self._show_dashboard()
        self.monitor.start()
        self.after(250, self._poll_queue)
        self.after(1000, self._tick_clock)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=180, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="Network Monitor", font=ctk.CTkFont(size=18, weight="bold")).pack(
            padx=16,
            pady=(24, 20),
            anchor="w",
        )

        buttons: list[tuple[str, Callable[[], None]]] = [
            ("Dashboard", self._show_dashboard),
            ("History", self._show_history),
            ("Statistics", self._show_statistics),
            ("Settings", self._show_settings),
        ]
        for text, command in buttons:
            ctk.CTkButton(sidebar, text=text, anchor="w", command=command).pack(fill="x", padx=16, pady=6)

        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _clear_content(self) -> None:
        self.kpis.clear()
        self.status_label = None
        self.event_log = None
        self.stats_box = None
        self.charts = None
        for child in self.content.winfo_children():
            child.destroy()

    def _show_dashboard(self) -> None:
        self._clear_content()
        self.current_page = "dashboard"
        page = ctk.CTkFrame(self.content, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(page, corner_radius=8)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for index in range(7):
            top.grid_columnconfigure(index, weight=1, uniform="kpi")

        cards = [
            ("Download", "download", "0.00 Mbps"),
            ("Upload", "upload", "0.00 Mbps"),
            ("Ping", "ping", "-- ms"),
            ("Jitter", "jitter", "-- ms"),
            ("Packet Loss", "packet_loss", "0.00%"),
            ("Status", "status", "OFFLINE"),
            ("Time", "time", datetime.now().strftime("%H:%M:%S")),
        ]
        for column, (title, key, value) in enumerate(cards):
            card = ctk.CTkFrame(top, corner_radius=8)
            card.grid(row=0, column=column, sticky="nsew", padx=6, pady=8)
            ctk.CTkLabel(card, text=title, text_color="#9aa0a6").pack(anchor="w", padx=12, pady=(10, 2))
            label = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=18, weight="bold"))
            label.pack(anchor="w", padx=12, pady=(0, 10))
            self.kpis[key] = label
            if key == "status":
                self.status_label = label

        body = ctk.CTkFrame(page, corner_radius=8)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        chart_holder = ctk.CTkFrame(body, corner_radius=8)
        chart_holder.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        chart_holder.grid_rowconfigure(1, weight=1)
        chart_holder.grid_columnconfigure(0, weight=1)
        self.charts = LiveCharts(chart_holder)
        self.charts.toolbar.grid(row=0, column=0, sticky="ew")
        self.charts.widget().grid(row=1, column=0, sticky="nsew")

        log_holder = ctk.CTkFrame(body, corner_radius=8)
        log_holder.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        log_holder.grid_rowconfigure(1, weight=1)
        log_holder.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_holder, text="Event Log", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0,
            column=0,
            sticky="w",
            padx=12,
            pady=(12, 6),
        )
        self.event_log = ctk.CTkTextbox(log_holder, wrap="word")
        self.event_log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._load_recent_events()
        if self.latest_sample is not None:
            self._apply_sample(self.latest_sample)

    def _show_history(self) -> None:
        self._clear_content()
        self.current_page = "history"
        page = ctk.CTkFrame(self.content, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        controls = ctk.CTkFrame(page, corner_radius=8)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkButton(controls, text="Export Last 24h CSV", command=self._export_csv).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(controls, text="Export Last 24h XLSX", command=self._export_xlsx).pack(side="left", padx=10, pady=10)

        text = ctk.CTkTextbox(page, wrap="none")
        text.grid(row=2, column=0, sticky="nsew")
        text.insert("end", "Timestamp\tDownload\tUpload\tPing\tJitter\tLoss\tStatus\n")
        for sample in self.database.fetch_samples(limit=500):
            text.insert(
                "end",
                f"{sample.timestamp:%Y-%m-%d %H:%M:%S}\t{sample.download}\t{sample.upload}\t"
                f"{sample.ping}\t{sample.jitter}\t{sample.packet_loss}\t{sample.status}\n",
            )
        text.configure(state="disabled")

    def _show_statistics(self) -> None:
        self._clear_content()
        self.current_page = "statistics"
        page = ctk.CTkFrame(self.content, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        ctk.CTkButton(page, text="Refresh", command=self._refresh_statistics).grid(row=0, column=0, sticky="w")
        self.stats_box = ctk.CTkTextbox(page)
        self.stats_box.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self._refresh_statistics()

    def _show_settings(self) -> None:
        self._clear_content()
        self.current_page = "settings"
        page = ctk.CTkFrame(self.content, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        page.grid_columnconfigure(1, weight=1)

        entries: dict[str, ctk.CTkEntry] = {}
        rows = [
            ("Ping host", "ping_host", self.config_data.ping_host),
            ("Ping interval seconds", "ping_interval_seconds", self.config_data.ping_interval_seconds),
            ("Speed test interval seconds", "speedtest_interval_seconds", self.config_data.speedtest_interval_seconds),
            ("Ping threshold ms", "ping_warning_ms", self.config_data.thresholds.ping_warning_ms),
            ("Packet loss threshold %", "packet_loss_warning_percent", self.config_data.thresholds.packet_loss_warning_percent),
            ("Download drop ratio", "download_drop_ratio", self.config_data.thresholds.download_drop_ratio),
        ]
        for row, (label, key, value) in enumerate(rows):
            ctk.CTkLabel(page, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=8)
            entry = ctk.CTkEntry(page)
            entry.insert(0, str(value))
            entry.grid(row=row, column=1, sticky="ew", pady=8)
            entries[key] = entry

        theme = ctk.CTkSegmentedButton(page, values=["dark", "light"])
        theme.set(self.config_data.theme)
        theme.grid(row=len(rows), column=1, sticky="w", pady=8)
        ctk.CTkLabel(page, text="Theme").grid(row=len(rows), column=0, sticky="w", pady=8)
        notifications_enabled = tk.BooleanVar(value=self.config_data.desktop_notifications_enabled)
        notification_state = "disabled" if platform.system() == "Windows" else "normal"
        ctk.CTkCheckBox(
            page,
            text="Desktop notifications",
            variable=notifications_enabled,
            state=notification_state,
        ).grid(row=len(rows) + 1, column=1, sticky="w", pady=8)

        def save() -> None:
            try:
                self.config_data.ping_host = entries["ping_host"].get().strip() or "8.8.8.8"
                self.config_data.ping_interval_seconds = float(entries["ping_interval_seconds"].get())
                self.config_data.speedtest_interval_seconds = float(entries["speedtest_interval_seconds"].get())
                self.config_data.thresholds.ping_warning_ms = float(entries["ping_warning_ms"].get())
                self.config_data.thresholds.packet_loss_warning_percent = float(
                    entries["packet_loss_warning_percent"].get()
                )
                self.config_data.thresholds.download_drop_ratio = float(entries["download_drop_ratio"].get())
                self.config_data.desktop_notifications_enabled = (
                    notifications_enabled.get() and platform.system() != "Windows"
                )
                self.config_data.theme = theme.get()
            except ValueError:
                messagebox.showerror("Invalid settings", "Numeric settings must contain valid numbers.")
                return
            save_config(self.config_data)
            ctk.set_appearance_mode(self.config_data.theme)
            self.notifier.enabled = self.config_data.desktop_notifications_enabled
            self.monitor.update_config(self.config_data)
            messagebox.showinfo("Settings saved", "Settings were saved and applied.")

        ctk.CTkButton(page, text="Save Settings", command=save).grid(row=len(rows) + 2, column=1, sticky="w", pady=16)

    def _poll_queue(self) -> None:
        while True:
            try:
                item = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, NetworkSample):
                self._apply_sample(item)
            elif isinstance(item, EventRecord):
                self._append_event(item)
        if self.winfo_exists():
            self.after(250, self._poll_queue)

    def _apply_sample(self, sample: NetworkSample) -> None:
        self.latest_sample = sample
        self._set_kpi("download", f"{sample.download or 0:.2f} Mbps")
        self._set_kpi("upload", f"{sample.upload or 0:.2f} Mbps")
        self._set_kpi("ping", "-- ms" if sample.ping is None else f"{sample.ping:.1f} ms")
        self._set_kpi("jitter", f"{sample.jitter:.2f} ms")
        self._set_kpi("packet_loss", f"{sample.packet_loss:.2f}%")
        if self.status_label is not None:
            try:
                if self.status_label.winfo_exists():
                    self.status_label.configure(text=sample.status, text_color=STATUS_COLORS.get(sample.status, "#ffffff"))
            except tk.TclError:
                self.status_label = None
        if self.charts is not None:
            try:
                if self.charts.widget().winfo_exists():
                    self.charts.add_sample(sample)
            except tk.TclError:
                self.charts = None
        self.notifier.handle_status(sample.status)

    def _set_kpi(self, key: str, value: str) -> None:
        label = self.kpis.get(key)
        if label is None:
            return
        try:
            if label.winfo_exists():
                label.configure(text=value)
        except tk.TclError:
            self.kpis.pop(key, None)

    def _append_event(self, event: EventRecord) -> None:
        if self.event_log is None:
            return
        try:
            if self.event_log.winfo_exists():
                self.event_log.insert("end", f"{event.timestamp:%H:%M:%S}  {event.status}  {event.message}\n")
                self.event_log.see("end")
        except tk.TclError:
            self.event_log = None

    def _load_recent_events(self) -> None:
        if self.event_log is None:
            return
        for event in reversed(self.database.fetch_recent_events(50)):
            self._append_event(event)

    def _tick_clock(self) -> None:
        self._set_kpi("time", datetime.now().strftime("%H:%M:%S"))
        if self.winfo_exists():
            self.after(1000, self._tick_clock)

    def _export_csv(self) -> None:
        self._export("csv")

    def _export_xlsx(self) -> None:
        self._export("xlsx")

    def _export(self, extension: str) -> None:
        end = datetime.now()
        start = end - timedelta(days=1)
        default = EXPORT_DIR / f"network_export_{end:%Y%m%d_%H%M%S}.{extension}"
        path = filedialog.asksaveasfilename(
            defaultextension=f".{extension}",
            initialfile=default.name,
            filetypes=[(extension.upper(), f"*.{extension}")],
        )
        if not path:
            return
        if extension == "csv":
            self.exporter.export_csv(start, end, Path(path))
        else:
            self.exporter.export_xlsx(start, end, Path(path))
        messagebox.showinfo("Export complete", f"Saved {path}")

    def _refresh_statistics(self) -> None:
        if self.stats_box is None:
            return
        try:
            if not self.stats_box.winfo_exists():
                self.stats_box = None
                return
        except tk.TclError:
            self.stats_box = None
            return
        samples = self.database.fetch_samples()
        stats = calculate_statistics(samples)
        self.stats_box.configure(state="normal")
        self.stats_box.delete("1.0", "end")
        for metric, values in stats.items():
            self.stats_box.insert("end", f"{metric}\n")
            if isinstance(values, dict):
                for label, value in values.items():
                    self.stats_box.insert("end", f"  {label}: {value}\n")
            else:
                self.stats_box.insert("end", f"  {values}\n")
            self.stats_box.insert("end", "\n")
        self.stats_box.configure(state="disabled")

    def _close(self) -> None:
        self.monitor.stop()
        self.destroy()
