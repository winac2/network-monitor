# Network Monitor Desktop App -- Specification

## Goal

Build a production-quality Python desktop application that monitors
Internet performance in real time and helps detect network congestion.

## Tech Stack

-   Python 3.12+
-   CustomTkinter
-   Matplotlib
-   psutil
-   ping3
-   speedtest-cli
-   pandas
-   sqlite3
-   threading
-   queue
-   openpyxl

## Project Structure

``` text
NetworkMonitor/
├── main.py
├── ui.py
├── monitor.py
├── graph.py
├── database.py
├── exporter.py
├── config.py
├── requirements.txt
├── data/network.db
├── exports/
└── logs/
```

## Functional Requirements

### Dashboard

Display: - Download speed (Mbps) - Upload speed (Mbps) - Ping (ms) -
Jitter (ms) - Packet loss (%) - Status badge
(GOOD/WARNING/CONGESTED/OFFLINE) - Current time

### Sampling

-   Ping every 1 second.
-   Jitter calculated from recent ping history.
-   Packet loss over last 100 pings.
-   Download/upload test every 60 seconds in a background thread.
-   UI must never freeze.

### Charts

Three live charts: 1. Download 2. Upload 3. Ping

Requirements: - Show last 10 minutes. - Zoom/Pan support. - Red
background while status == CONGESTED.

### Congestion Detection

Rules: - Ping \> 100 ms - Packet loss \> 5% - Download \< 20% of rolling
average - Three consecutive failed pings =\> OFFLINE

### Data Storage

SQLite table:

    id INTEGER PRIMARY KEY
    timestamp DATETIME
    download REAL
    upload REAL
    ping REAL
    jitter REAL
    packet_loss REAL
    status TEXT

### Export

Export selected range to: - CSV - XLSX

### Statistics

Show: - Average - Minimum - Maximum - Median - 95th percentile -
Downtime duration

### Settings

Configurable: - Ping host - Sampling interval - Speed test interval -
Congestion thresholds - Dark/Light mode

### Notifications

Desktop notification when: - Network offline - Congestion detected -
Network recovered

### Threading

Separate threads for: - Ping - Speed test - Database logging

Use Queue to communicate with UI.

### UI

Use CustomTkinter. Responsive layout. Dark mode by default.

Sidebar: - Dashboard - History - Statistics - Settings

Main page: - KPI cards - Live charts - Event log

### Logging

Use Python logging. Rotate log files.

### Error Handling

-   Retry failed speed tests.
-   Continue operation if DNS/ping target unavailable.
-   Never crash because of network errors.

### Code Quality

-   Type hints.
-   Docstrings.
-   Modular architecture.
-   PEP8.
-   No global mutable state where avoidable.

### Deliverables

Produce a complete runnable project with: - All source files -
requirements.txt - README.md - Sample SQLite database - Sample exported
CSV - PyInstaller build specification

The application should run after:

``` bash
pip install -r requirements.txt
python main.py
```
