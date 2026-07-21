# Network Monitor

Python desktop application for real-time Internet performance monitoring and congestion detection.

## Features

- Live dashboard for current download throughput, upload throughput, ping, jitter, packet loss, status, and current time
- Background ping, live network I/O, and speed test workers so the UI remains responsive
- SQLite storage for samples and events
- Matplotlib charts with pan/zoom toolbar and a congestion background state
- CSV and XLSX export for recent history
- Statistics view with average, minimum, maximum, median, 95th percentile, and downtime duration
- Configurable host, intervals, thresholds, and theme
- Rotating log files under `logs/`

## Run

```bash
pip install -r requirements.txt
python main.py
```

The app writes runtime data to:

- `data/network.db`
- `exports/`
- `logs/network_monitor.log`

## Build

```bash
pyinstaller NetworkMonitor.spec
```

## Notes

The dashboard download/upload values are live interface throughput in Mbps, calculated from byte counters. Speed tests can take time and depend on network availability. If `ping3`, `speedtest-cli`, or desktop notifications are unavailable, the app logs the failure and keeps running.
