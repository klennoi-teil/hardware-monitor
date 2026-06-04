"""CSV logging for hardware monitor snapshots."""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Optional

from monitor.sensors import Snapshot


class CsvLogger:
    """Appends hardware metric snapshots to a CSV file."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = Path(path or _default_log_path())
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._header_written = self._path.exists() and self._path.stat().st_size > 0
        self._file = open(self._path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)

    #  Context manager 

    def __enter__(self) -> "CsvLogger":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    #  Logging 

    def write(self, snap: Snapshot) -> None:
        row = [
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snap.timestamp)),
            f"{snap.cpu.usage_total:.1f}",
            snap.cpu.temp_package if snap.cpu.temp_package is not None else "",
            snap.gpu.name if snap.gpu else "",
            f"{snap.gpu.usage:.1f}" if snap.gpu else "",
            snap.gpu.temp if snap.gpu and snap.gpu.temp is not None else "",
            f"{snap.memory.percent:.1f}",
            f"{snap.disk.percent:.1f}",
        ]

        if not self._header_written:
            self._writer.writerow([
                "timestamp", "cpu_usage_pct", "cpu_temp_c",
                "gpu_name", "gpu_usage_pct", "gpu_temp_c",
                "memory_pct", "disk_pct",
            ])
            self._header_written = True

        self._writer.writerow(row)
        self._file.flush()

    @property
    def path(self) -> Path:
        return self._path


def _default_log_path() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return str(Path.home() / "Documents" / f"hardware_monitor_{ts}.csv")
