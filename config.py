"""Configuration for hardware-monitor."""

#  Dashboard refresh interval (seconds) 
REFRESH_INTERVAL = 2.0

#  Display options 
THEME = "auto"
CPU_DISPLAY_MODE = "all"

#  CSV logging options 
ENABLE_LOGGING = False
LOG_FILE = None
LOG_INTERVAL = 5.0

#  Sensor backends 
PREFER_HARDWARE_MONITOR = True

# 
#  Automation / Agent settings
# 

#  Sampling 
# How often the background agent checks sensors (seconds)
AGENT_INTERVAL = 5.0

#  Temperature thresholds (C) 
# WARNING level   first alert, icon turns yellow
# CRITICAL level  urgent alert, icon turns red
THRESHOLDS = {
    "cpu":  {"warning": 75, "critical": 85},
    "gpu":  {"warning": 80, "critical": 90},
}

#  Alert behaviour 
# Cooldown: minimum seconds between two alerts for the same sensor
ALERT_COOLDOWN = 120          # 2 minutes
# Suppress notifications between these hours (24h format, None to disable)
SILENT_HOURS_START = 23       # 11 PM
SILENT_HOURS_END = 7          # 7 AM

#  Notification style 
# "toast" = Windows native toast (requires plyer/win10toast)
# "log"   = log to file only (no popup)
NOTIFICATION_MODE = "toast"

#  System tray 
# Show a tray icon with colour-coded status
SHOW_TRAY = True

#  Auto-start 
# Register a Windows Startup entry so the agent launches on login
AUTO_START = True

#  Alert log 
# Separate from CSV data logging; records every triggered alert
ALERT_LOG_FILE = None         # None = auto: ~/Documents/hardware_alerts.log
