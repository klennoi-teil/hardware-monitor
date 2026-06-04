"""Background monitoring agent  headless loop with optional tray icon."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


#  Agent 

class MonitorAgent:
    """
    Background agent that continuously samples sensors, evaluates alerts,
    and (optionally) maintains a colour-coded system tray icon.
    """

    def __init__(
        self,
        interval: float = 5.0,
        thresholds: Optional[dict] = None,
        alert_cooldown: float = 120.0,
        silent_start: Optional[int] = 23,
        silent_end: Optional[int] = 7,
        notify_mode: str = "toast",
        show_tray: bool = True,
        alert_log: Optional[str] = None,
        theme: str = "auto",
    ):
        self._interval = interval
        self._show_tray = show_tray
        self._running = False
        self._paused = False

        # Lazy imports to keep startup fast
        from monitor.sensors import SensorReader
        from monitor.alert import AlertEngine

        self._reader = SensorReader()
        self._alert_engine = AlertEngine(
            thresholds=thresholds or {},
            cooldown=alert_cooldown,
            silent_start=silent_start,
            silent_end=silent_end,
            notify_mode=notify_mode,
            alert_log=alert_log,
        )

        # Last snapshot (for tray tooltip, dashboard launch)
        self._last_snap = None

        # Tray icon (lazy)
        self._tray_icon = None
        self._tray_thread: Optional[threading.Thread] = None

    #  Lifecycle 

    def start(self) -> None:
        """Start the monitoring loop. Blocks until stop() or KeyboardInterrupt."""
        self._running = True

        logger.info(
            "MonitorAgent started  (interval=%ss, tray=%s)",
            self._interval, self._show_tray,
        )

        # Launch tray icon in a daemon thread
        if self._show_tray:
            self._start_tray()

        # Main sampling loop
        try:
            while self._running:
                if not self._paused:
                    try:
                        snap = self._reader.snapshot()
                        self._last_snap = snap
                        self._alert_engine.evaluate(snap)
                        self._update_tray()
                    except Exception as exc:
                        logger.error("Sampling error: %s", exc)
                time.sleep(self._interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        self._running = False
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self._alert_engine.close()
        logger.info("MonitorAgent stopped")

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def status_text(self) -> str:
        level = self._alert_engine.overall_level
        levels = self._alert_engine.current_levels

        parts = []
        for sensor, lvl in sorted(levels.items()):
            parts.append(f"{sensor.upper()}={lvl.value.upper()}")
        status = " | ".join(parts) if parts else "All OK"

        cpu_pct = ""
        gpu_pct = ""
        if self._last_snap:
            cpu_pct = f"CPU:{self._last_snap.cpu.usage_total:.0f}%"
            gpu_pct = f" GPU:{self._last_snap.gpu.usage:.0f}%" if self._last_snap.gpu else ""

        return f"Hardware Monitor    {status}  ({cpu_pct}{gpu_pct})"

    @property
    def overall_level(self):
        return self._alert_engine.overall_level

    #  Tray (pystray) 

    def _start_tray(self) -> None:
        try:
            from PIL import Image, ImageDraw
            import pystray

            icon_size = 64

            def _make_icon(level):
                """Create a coloured circle icon."""
                im = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(im)

                colour = {
                    "ok": (34, 197, 94),       # green
                    "warning": (234, 179, 8),  # yellow
                    "critical": (239, 68, 68), # red
                }.get(level.value, (128, 128, 128))

                draw.ellipse([4, 4, icon_size - 4, icon_size - 4], fill=colour)
                return im

            def _on_open(icon, item):
                self._launch_dashboard()

            def _on_view_alerts(icon, item):
                self._open_alert_log()

            def _on_open_config(icon, item):
                self._open_config()

            def _on_quit(icon, item):
                self._running = False
                icon.stop()

            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", _on_open, default=True),
                pystray.MenuItem("View Alerts", _on_view_alerts),
                pystray.MenuItem("Open Config", _on_open_config),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", _on_quit),
            )

            icon = pystray.Icon(
                "hardware_monitor",
                _make_icon(self._alert_engine.overall_level),
                self.status_text,
                menu,
            )

            self._tray_icon = icon

            # pystray.run() blocks  run it in a daemon thread
            t = threading.Thread(target=icon.run, daemon=True)
            t.start()
            self._tray_thread = t

            logger.info("Tray icon started")

        except ImportError as exc:
            logger.warning("Tray icon unavailable: %s (install pystray + pillow)", exc)
        except Exception as exc:
            logger.warning("Tray icon failed: %s", exc)

    def _update_tray(self) -> None:
        if self._tray_icon is None:
            return
        try:
            from PIL import ImageDraw, Image

            level = self._alert_engine.overall_level
            colour = {
                "ok": (34, 197, 94),
                "warning": (234, 179, 8),
                "critical": (239, 68, 68),
            }.get(level.value, (128, 128, 128))

            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            draw.ellipse([4, 4, 60, 60], fill=colour)
            self._tray_icon.icon = im
            self._tray_icon.title = self.status_text
        except Exception:
            pass

    #  Helper actions 

    def _launch_dashboard(self) -> None:
        """Open the terminal dashboard in a new window."""
        try:
            import subprocess
            script = os.path.join(os.path.dirname(__file__), "..", "main.py")
            subprocess.Popen(
                [sys.executable, os.path.abspath(script)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as exc:
            logger.warning("Cannot launch dashboard: %s", exc)

    def _open_alert_log(self) -> None:
        """Open the alert log file in the default text editor."""
        try:
            import os
            os.startfile(str(self._alert_engine._alert_log))
        except Exception as exc:
            logger.warning("Cannot open alert log: %s", exc)

    def _open_config(self) -> None:
        """Open config.py in the default editor."""
        try:
            import os
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
            os.startfile(os.path.abspath(config_path))
        except Exception as exc:
            logger.warning("Cannot open config: %s", exc)



