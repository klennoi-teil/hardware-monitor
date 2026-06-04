#!/usr/bin/env python3
"""Hardware Monitor Agent  background temperature monitoring with alerts."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="  Hardware Monitor Agent  background temp alerts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  monitor-agent                    # run with defaults
  monitor-agent --no-tray          # headless (no system tray icon)
  monitor-agent --interval 10      # sample every 10 seconds
  monitor-agent --install          # register Windows auto-start
  monitor-agent --uninstall        # remove auto-start
        """,
    )

    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=None,
        help="Sampling interval in seconds (overrides config)",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Run without system tray icon (headless)",
    )
    parser.add_argument(
        "--notify",
        choices=("toast", "log"),
        default=None,
        help="Notification mode (overrides config)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Register Windows auto-start (Startup folder)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove Windows auto-start entry",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show whether agent is installed & exit",
    )

    return parser.parse_args()


def _install_autostart() -> None:
    """Create a shortcut in the Windows Startup folder."""
    # Use a .bat launcher in Startup folder
    from win32com.client import Dispatch

    startup = Path(os.environ.get(
        "APPDATA",
        str(Path.home() / "AppData" / "Roaming"),
    )) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    startup.mkdir(parents=True, exist_ok=True)

    # Create a .bat launcher for the agent
    py_exe = sys.executable
    agent_script = os.path.abspath(__file__)
    bat_path = startup / "HardwareMonitorAgent.bat"

    with open(bat_path, "w") as f:
        f.write(f'@echo off\n"{py_exe}" "{agent_script}" --no-tray\n')

    print(f"[OK] Auto-start installed: {bat_path}")
    print("   Agent will launch silently on next login.")


def _uninstall_autostart() -> None:
    startup = Path(os.environ.get(
        "APPDATA",
        str(Path.home() / "AppData" / "Roaming"),
    )) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    bat_path = startup / "HardwareMonitorAgent.bat"
    if bat_path.exists():
        bat_path.unlink()
        print(f"[OK] Auto-start removed: {bat_path}")
    else:
        print("[INFO]  No auto-start entry found.")


def _show_status() -> None:
    startup = Path(os.environ.get(
        "APPDATA",
        str(Path.home() / "AppData" / "Roaming"),
    )) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    bat_path = startup / "HardwareMonitorAgent.bat"
    if bat_path.exists():
        print(f"[OK] Agent is installed as auto-start: {bat_path}")
    else:
        print("[INFO]  Agent is NOT installed as auto-start.")
    print(f"   Python: {sys.executable}")
    print(f"   Script: {os.path.abspath(__file__)}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()

    # Handle lifecycle commands that exit immediately
    if args.status:
        _show_status()
        return
    if args.install:
        _install_autostart()
        return
    if args.uninstall:
        _uninstall_autostart()
        return

    # Normal run: import config and start agent
    try:
        import config as cfg
    except ImportError:
        # When run from project root
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import config as cfg

    from monitor.agent import MonitorAgent

    agent = MonitorAgent(
        interval=args.interval if args.interval is not None else cfg.AGENT_INTERVAL,
        thresholds=cfg.THRESHOLDS,
        alert_cooldown=cfg.ALERT_COOLDOWN,
        silent_start=cfg.SILENT_HOURS_START,
        silent_end=cfg.SILENT_HOURS_END,
        notify_mode=args.notify if args.notify else cfg.NOTIFICATION_MODE,
        show_tray=not args.no_tray and cfg.SHOW_TRAY,
        alert_log=cfg.ALERT_LOG_FILE,
        theme=cfg.THEME,
    )

    agent.start()


if __name__ == "__main__":
    main()
