#!/usr/bin/env python3
"""Hardware Monitor — live terminal dashboard & GUI window."""

from __future__ import annotations

import argparse
import logging
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hardware Monitor — live terminal dashboard & GUI window",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hardware-monitor                  # terminal dashboard
  hardware-monitor --gui            # GUI window
  hardware-monitor -i 1 --theme dark
  hardware-monitor --gui -i 3      # GUI with 3s refresh
  hardware-monitor --log --log-interval 10
        """,
    )

    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=2.0,
        help="Refresh interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the GUI window instead of terminal dashboard",
    )
    parser.add_argument(
        "--theme",
        choices=("auto", "dark", "light"),
        default="auto",
        help="Terminal dashboard colour theme (default: auto)",
    )
    parser.add_argument(
        "--cpu-total-only",
        action="store_true",
        help="Show only total CPU usage, not per-core",
    )
    parser.add_argument(
        "-l", "--log",
        action="store_true",
        help="Enable CSV logging to ~/Documents/",
    )
    parser.add_argument(
        "--log-interval",
        type=float,
        default=5.0,
        help="Logging sample interval in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Full path to the CSV log file",
    )
    parser.add_argument(
        "--no-hw-monitor",
        action="store_true",
        help="Skip LibreHardwareMonitor/OpenHardwareMonitor WMI, use native sensors only",
    )

    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    args = _parse_args()

    if args.gui:
        from monitor.gui import run_gui
        run_gui(interval=args.interval)
        return

    from monitor import display
    from monitor.logger import CsvLogger

    logger_fn = None
    if args.log:
        logger_fn = CsvLogger(path=args.log_file).write
        print(f"Logging to: {logger_fn.__self__.path}", file=sys.stderr)

    display.run_dashboard(
        refresh_interval=args.interval,
        cpu_display="total" if args.cpu_total_only else "all",
        theme=args.theme,
        enable_logging=args.log,
        logger_fn=logger_fn,
    )


if __name__ == "__main__":
    main()
