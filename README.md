# 🖥️ Hardware Monitor

Live terminal dashboard + background automation agent for monitoring PC hardware temperatures and resource usage on Windows.

## Features

### Dashboard
- **CPU** — Usage total & per-core, temperature, frequency, core count
- **GPU** — Usage, temperature, VRAM (NVIDIA via nvidia-smi, or WMI fallback)
- **Memory** — Total, used, available, percentage
- **Disk** — Usage across all physical mount points
- **Network** — Real-time upload/download rates
- **Temperature** — Via LibreHardwareMonitor / OpenHardwareMonitor WMI, or native ACPI
- **Colour-coded** — Green/yellow/red thresholds at 60°C / 80°C and 50% / 80% usage

### Automation Agent (new)
- **Background monitoring** — Runs silently, samples sensors every N seconds
- **Toast notifications** — Windows native popup when CPU/GPU exceeds thresholds
- **System tray icon** — Green ✓ / yellow ⚠ / red 🚨 at a glance
- **Smart cooldown** — Won't spam; respects silent hours (11 PM – 7 AM)
- **Auto-start** — Registers itself to launch with Windows
- **Alert log** — Every triggered alert is timestamped in ~/Documents/hardware_alerts.log

## Requirements

- Windows 10/11
- Python 3.10+
- (Recommended) [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) — run it **as Administrator** for full sensor data (CPU package temp, fan speeds, etc.)

## Quick Start

### 1. Install dependencies

powershell
python -m pip install -r requirements.txt


### 2. Dashboard (interactive)

powershell
python main.py


### 3. Automation agent (background)

powershell
# One-time install + auto-start
.\install_automation.ps1

# Or manually:
python monitor_agent.py                          # with tray icon
python monitor_agent.py --no-tray               # headless (no icon)
python monitor_agent.py --interval 10           # sample every 10s
python monitor_agent.py --install               # register auto-start
python monitor_agent.py --uninstall             # remove auto-start
python monitor_agent.py --status                # check install status


### 4. Quick launcher

powershell
.\run.ps1               # dashboard
.\run.ps1 -Agent        # background agent
.\run.ps1 -Install      # install auto-start
.\run.ps1 -Status       # check status


## Usage — Dashboard

powershell
# Default 2-second refresh
python main.py

# 1-second refresh, dark theme
python main.py -i 1 --theme dark

# Enable CSV logging
python main.py --log

# Custom log path & interval
python main.py --log --log-file C:\data\temps.csv --log-interval 10

# CPU total only (hide per-core bars)
python main.py --cpu-total-only

# See all options
python main.py --help


## Usage — Agent

powershell
# Run with defaults (tray icon + toast notifications)
python monitor_agent.py

# Headless (for servers or when you don't want a tray icon)
python monitor_agent.py --no-tray --notify log

# Install/uninstall auto-start
python monitor_agent.py --install
python monitor_agent.py --uninstall


## Configuration

Edit [config.py](config.py) to customise:

| Setting | Default | Description |
|---|---|---|
| AGENT_INTERVAL | 5.0 | Sampling interval (seconds) |
| THRESHOLDS.cpu.warning | 75°C | CPU warning threshold |
| THRESHOLDS.cpu.critical | 85°C | CPU critical threshold |
| THRESHOLDS.gpu.warning | 80°C | GPU warning threshold |
| THRESHOLDS.gpu.critical | 90°C | GPU critical threshold |
| ALERT_COOLDOWN | 120 | Seconds between same alert |
| SILENT_HOURS_START | 23 | Suppress alerts after (24h) |
| SILENT_HOURS_END | 7 | Resume alerts at (24h) |
| NOTIFICATION_MODE | "toast" | "toast" or "log" |
| SHOW_TRAY | True | Show system tray icon |
| AUTO_START | True | Register startup entry |

## Temperature Sensors

The monitor tries backends in this order:

1. **LibreHardwareMonitor WMI** — most complete; run LibreHardwareMonitor as Administrator first
2. **OpenHardwareMonitor WMI** — fallback if Libre is not installed
3. **Native ACPI** — MSAcpi_ThermalZoneTemperature (limited, often only a single zone)

## Logs

- **Data log** (--log): ~/Documents/hardware_monitor_YYYYMMDD_HHMMSS.csv
- **Alert log** (auto): ~/Documents/hardware_alerts.log
