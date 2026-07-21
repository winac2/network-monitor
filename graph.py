"""Matplotlib live chart widgets."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Deque

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure

from database import NetworkSample


class LiveCharts:
    """Three live time-series charts embedded in a Tk container."""

    def __init__(self, parent: object) -> None:
        self.samples: Deque[NetworkSample] = deque(maxlen=1200)
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.axes = [
            self.figure.add_subplot(311),
            self.figure.add_subplot(312),
            self.figure.add_subplot(313),
        ]
        self.lines = [
            self.axes[0].plot([], [], color="#2f80ed", linewidth=1.8)[0],
            self.axes[1].plot([], [], color="#27ae60", linewidth=1.8)[0],
            self.axes[2].plot([], [], color="#eb5757", linewidth=1.8)[0],
        ]
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.toolbar = NavigationToolbar2Tk(self.canvas, parent, pack_toolbar=False)
        self._configure_axes()

    def widget(self) -> object:
        """Return the Tk canvas widget."""

        return self.canvas.get_tk_widget()

    def add_sample(self, sample: NetworkSample) -> None:
        """Add one sample and redraw charts."""

        self.samples.append(sample)
        self._trim_to_window()
        self._redraw(sample.status)

    def _configure_axes(self) -> None:
        labels = ("Download Mbps", "Upload Mbps", "Ping ms")
        for axis, label in zip(self.axes, labels, strict=True):
            axis.set_ylabel(label)
            axis.grid(True, alpha=0.25)
            axis.xaxis.set_major_formatter(DateFormatter("%H:%M"))
        self.axes[-1].set_xlabel("Time")
        self.figure.tight_layout(pad=1.2)

    def _trim_to_window(self) -> None:
        cutoff = datetime.now() - timedelta(minutes=10)
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()

    def _redraw(self, status: str) -> None:
        times = [sample.timestamp for sample in self.samples]
        series = [
            [sample.download for sample in self.samples],
            [sample.upload for sample in self.samples],
            [sample.ping for sample in self.samples],
        ]
        background = "#3b1717" if status == "CONGESTED" else "#1f1f1f"
        self.figure.patch.set_facecolor(background)

        for axis, line, values in zip(self.axes, self.lines, series, strict=True):
            axis.set_facecolor(background)
            axis.tick_params(colors="#d6d6d6")
            axis.yaxis.label.set_color("#d6d6d6")
            axis.xaxis.label.set_color("#d6d6d6")
            axis.title.set_color("#d6d6d6")
            line.set_data(times, values)
            axis.relim()
            axis.autoscale_view()
            if times:
                axis.set_xlim(max(times[-1] - timedelta(minutes=10), times[0]), times[-1])

        self.canvas.draw_idle()
