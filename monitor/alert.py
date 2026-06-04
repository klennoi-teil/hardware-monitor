"""Alert engine  threshold checking, notifications, cooldown management."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


#  Alert levels 

class AlertLevel(Enum):
    OK = "ok"
    WARNING = "WARNING"
    CRITICAL = "critical"

    def __lt__(self, other: "AlertLevel") -> bool:
        order = [AlertLevel.OK, AlertLevel.WARNING, AlertLevel.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: "AlertLevel") -> bool:
        return self == other or self.__lt__(other)


#  Alert event data 

@dataclass
class AlertEvent:
    timestamp: float = 0.0
    sensor: str = ""               # e.g. "cpu", "gpu"
    label: str = ""                # e.g. "CPU Package", "GPU Core"
    level: AlertLevel = AlertLevel.WARNING
    temp: float = 0.0
    threshold: float = 0.0
    message: str = ""


#  Alert engine 

class AlertEngine:
    """Checks thresholds, manages cooldowns, fires notifications."""

    def __init__(
        self,
        thresholds: dict,
        cooldown: float = 120.0,
        silent_start: Optional[int] = 23,
        silent_end: Optional[int] = 7,
        notify_mode: str = "toast",
        alert_log: Optional[str] = None,
    ):
        self._thresholds = thresholds
        self._cooldown = cooldown
        self._silent_start = silent_start
        self._silent_end = silent_end
        self._notify_mode = notify_mode

        # Track last alert time per sensor+level to enforce cooldown
        self._last_alert: dict[str, float] = {}

        # Track current highest level per sensor (for tray icon)
        self._current_levels: dict[str, AlertLevel] = {}

        # Overall highest level across all sensors
        self._overall_level = AlertLevel.OK

        # Alert log file
        if alert_log:
            self._alert_log = Path(alert_log)
        else:
            self._alert_log = Path.home() / "Documents" / "hardware_alerts.log"
        self._alert_log.parent.mkdir(parents=True, exist_ok=True)

        # Notification backend
        self._notifier = _load_notifier(notify_mode)

    #  Public API 

    def evaluate(self, snap) -> list[AlertEvent]:
        """
        Evaluate a Snapshot against thresholds.
        Returns list of new AlertEvent objects (empty if no thresholds exceeded).
        Updates internal state for cooldown and current level tracking.
        """
        events: list[AlertEvent] = []
        self._current_levels.clear()

        #  CPU 
        cpu_cfg = self._thresholds.get("cpu", {})
        cpu_warn = cpu_cfg.get("warning", 75)
        cpu_crit = cpu_cfg.get("critical", 85)

        if snap.cpu.temp_package is not None:
            level = self._classify(snap.cpu.temp_package, cpu_warn, cpu_crit)
            self._current_levels["cpu"] = level
            ev = self._maybe_alert("cpu", "CPU Package", level, snap.cpu.temp_package)
            if ev:
                events.append(ev)
        elif snap.cpu.temp_cores:
            # Use max core temp
            valid = [t for t in snap.cpu.temp_cores if t is not None]
            if valid:
                max_core = max(valid)
                level = self._classify(max_core, cpu_warn, cpu_crit)
                self._current_levels["cpu"] = level
                ev = self._maybe_alert("cpu", "CPU Core", level, max_core)
                if ev:
                    events.append(ev)

        #  GPU 
        if snap.gpu and snap.gpu.temp is not None:
            gpu_cfg = self._thresholds.get("gpu", {})
            gpu_warn = gpu_cfg.get("warning", 80)
            gpu_crit = gpu_cfg.get("critical", 90)
            level = self._classify(snap.gpu.temp, gpu_warn, gpu_crit)
            self._current_levels["gpu"] = level
            ev = self._maybe_alert("gpu", f"GPU ({snap.gpu.name})", level, snap.gpu.temp)
            if ev:
                events.append(ev)

        #  Overall level 
        all_levels = list(self._current_levels.values())
        if AlertLevel.CRITICAL in all_levels:
            self._overall_level = AlertLevel.CRITICAL
        elif AlertLevel.WARNING in all_levels:
            self._overall_level = AlertLevel.WARNING
        else:
            self._overall_level = AlertLevel.OK

        return events

    @property
    def overall_level(self) -> AlertLevel:
        return self._overall_level

    @property
    def current_levels(self) -> dict[str, AlertLevel]:
        return dict(self._current_levels)

    def close(self) -> None:
        pass

    #  Internals 

    def _classify(self, temp: float, warn: float, crit: float) -> AlertLevel:
        if temp >= crit:
            return AlertLevel.CRITICAL
        if temp >= warn:
            return AlertLevel.WARNING
        return AlertLevel.OK

    def _maybe_alert(
        self, sensor: str, label: str, level: AlertLevel, temp: float
    ) -> Optional[AlertEvent]:
        """Return AlertEvent only if cooldown has elapsed and level is not OK."""
        if level == AlertLevel.OK:
            return None

        threshold = (
            self._thresholds.get(sensor, {}).get("critical", 999)
            if level == AlertLevel.CRITICAL
            else self._thresholds.get(sensor, {}).get("warning", 999)
        )

        # Cooldown check: same sensor at same-or-higher level
        key = f"{sensor}_{level.value}"
        last = self._last_alert.get(key, 0.0)
        if time.time() - last < self._cooldown:
            return None

        # Silent hours check
        if self._is_silent_hours():
            logger.debug("Suppressing alert during silent hours (%s %s)", sensor, level.value)
            # Still track that we "would have" alerted
            self._last_alert[key] = time.time()
            return None

        # Build event
        ev = AlertEvent(
            timestamp=time.time(),
            sensor=sensor,
            label=label,
            level=level,
            temp=temp,
            threshold=threshold,
            message=self._format_msg(label, level, temp, threshold),
        )

        # Fire notification
        self._fire_notification(ev)
        self._log_alert(ev)
        self._last_alert[key] = time.time()

        return ev

    def _format_msg(
        self, label: str, level: AlertLevel, temp: float, threshold: float
    ) -> str:
        prefix = "WARNING" if level == AlertLevel.WARNING else "CRITICAL"
        return f"{prefix}: {label} at {temp:.0f}C (threshold {threshold:.0f}C)"

    def _fire_notification(self, ev: AlertEvent) -> None:
        if self._notifier:
            try:
                self._notifier(ev)
            except Exception as exc:
                logger.warning("Notification failed: %s", exc)

    def _log_alert(self, ev: AlertEvent) -> None:
        """Append alert to the persistent log file."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ev.timestamp))
        line = f"[{ts}] {ev.message}\n"
        try:
            with open(self._alert_log, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            logger.warning("Cannot write alert log: %s", exc)

    def _is_silent_hours(self) -> bool:
        if self._silent_start is None or self._silent_end is None:
            return False
        now_h = time.localtime().tm_hour
        if self._silent_start <= self._silent_end:
            # e.g. 23-7: crosses midnight
            return now_h >= self._silent_start or now_h < self._silent_end
        else:
            return self._silent_start <= now_h < self._silent_end


#  Notification backends 

def _load_notifier(mode: str):
    """Return a callable notify(ev) or None."""
    if mode == "log":
        return None

    # Try win10toast
    try:
        from win10toast import ToastNotifier

        toaster = ToastNotifier()

        def _win10toast(ev: AlertEvent) -> None:
            title = "Hardware Monitor"
            if ev.level == AlertLevel.CRITICAL:
                title = "!! " + title
            elif ev.level == AlertLevel.WARNING:
                title = "!! " + title
            toaster.show_toast(
                title,
                ev.message,
                duration=8,
                threaded=True,
            )

        logger.info("Using win10toast notification backend")
        return _win10toast
    except ImportError:
        pass

    logger.warning("No notification backend available; alerts will be log-only")
    return None


