#!/usr/bin/env python3
"""Hardware Monitor  live terminal dashboard for PC temperature & resource tracking."""

from __future__ import annotations

import argparse
import logging
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="  Hardware Monitor  live terminal dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hardware-monitor
  hardware-monitor --interval 1 --theme dark
  hardware-monitor --log --log-interval 10
  hardware-monitor --cpu-total-only
        """,
    )

    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=2.0,
        help="Refresh interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--theme",
        choices=("auto", "dark", "light"),
        default="auto",
        help="Dashboard colour theme (default: auto)",
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

    # Merge args into a config-like dict for display
    from monitor import display
    from monitor.logger import CsvLogger

    logger_fn = None
    if args.log:
        logger_fn = CsvLogger(path=args.log_file).write
        print(f" Logging to: {logger_fn.__self__.path}", file=sys.stderr)

    display.run_dashboard(
        refresh_interval=args.interval,
        cpu_display="total" if args.cpu_total_only else "all",
        theme=args.theme,
        enable_logging=args.log,
        logger_fn=logger_fn,
    )


if __name__ == "__main__":
    main()
