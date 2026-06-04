"""Read hardware sensor data on Windows via WMI + psutil + nvidia-smi."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


#  Data classes 

@dataclass
class CpuInfo:
    name: str = "N/A"
    usage_total: float = 0.0          # 0100 %
    usage_per_core: list[float] = field(default_factory=list)
    temp_package: Optional[float] = None   # C
    temp_cores: list[float | None] = field(default_factory=list)
    frequency: float = 0.0            # MHz
    physical_cores: int = 0
    logical_cores: int = 0


@dataclass
class GpuInfo:
    name: str = "N/A"
    usage: float = 0.0                # 0100 %
    temp: Optional[float] = None      # C
    memory_total: int = 0             # MB
    memory_used: int = 0              # MB
    memory_free: int = 0              # MB


@dataclass
class MemoryInfo:
    total: int = 0                    # bytes
    available: int = 0
    percent: float = 0.0
    used: int = 0


@dataclass
class DiskInfo:
    total: int = 0
    used: int = 0
    free: int = 0
    percent: float = 0.0


@dataclass
class NetInfo:
    bytes_sent: int = 0
    bytes_recv: int = 0
    sent_per_sec: float = 0.0
    recv_per_sec: float = 0.0


@dataclass
class Snapshot:
    timestamp: float = 0.0
    cpu: CpuInfo = field(default_factory=CpuInfo)
    gpu: Optional[GpuInfo] = field(default=None)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    disk: DiskInfo = field(default_factory=DiskInfo)
    net: NetInfo = field(default_factory=NetInfo)
    uptime: float = 0.0
    process_count: int = 0


#  Sensor backend 

class SensorReader:
    """Collects hardware sensor data from the local machine."""

    def __init__(self, prefer_hw_monitor: bool = True):
        self._prefer_hw_monitor = prefer_hw_monitor
        self._wmi_conn = None
        self._hw_wmi = None        # LibreHardwareMonitor / OHM connection
        self._prev_net = psutil.net_io_counters()
        self._prev_net_time = time.monotonic()
        self._disks = _get_mount_points()
        self._has_gpu = False
        self._nvidia_smi = _find_nvidia_smi()

        # Try to initialise WMI and hardware-monitor WMI
        self._init_wmi()

    #  initialisation helpers 

    def _init_wmi(self) -> None:
        try:
            import win32com.client
            self._wmi_conn = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
        except Exception as exc:
            logger.debug("WMI cimv2 unavailable: %s", exc)

        if self._prefer_hw_monitor:
            for namespace in (
                "root\\LibreHardwareMonitor",
                "root\\OpenHardwareMonitor",
            ):
                try:
                    self._hw_wmi = win32com.client.GetObject(f"winmgmts:\\\\.\\{namespace}")
                    logger.info("Connected to %s", namespace)
                    break
                except Exception:
                    continue

    #  Public sampling 

    def snapshot(self) -> Snapshot:
        snap = Snapshot(timestamp=time.time())

        snap.cpu = self._read_cpu()
        snap.gpu = self._read_gpu()
        snap.memory = self._read_memory()
        snap.disk = self._read_disk()
        snap.net = self._read_net()
        snap.uptime = time.time() - psutil.boot_time()
        snap.process_count = len(psutil.pids())

        return snap

    #  CPU 

    def _read_cpu(self) -> CpuInfo:
        info = CpuInfo()

        try:
            info.name = _cpu_brand()
        except Exception:
            pass

        info.physical_cores = psutil.cpu_count(logical=False) or 0
        info.logical_cores = psutil.cpu_count(logical=True) or 0
        info.usage_total = psutil.cpu_percent(interval=0)
        info.usage_per_core = psutil.cpu_percent(interval=0, percpu=True)
        info.frequency = (psutil.cpu_freq() or (0,))[0] if hasattr(psutil, "cpu_freq") else 0.0

        # Temperature: try hardware-monitor WMI first, then native ACPI
        info.temp_package, info.temp_cores = self._read_cpu_temps()

        return info

    def _read_cpu_temps(self) -> tuple[Optional[float], list[Optional[float]]]:
        """Return (package_temp, list_of_core_temps)."""
        if self._hw_wmi is not None:
            return self._read_cpu_temps_hw_wmi()
        return self._read_cpu_temps_native()

    def _read_cpu_temps_hw_wmi(self) -> tuple[Optional[float], list[Optional[float]]]:
        """Query temperatures via LibreHardwareMonitor / OpenHardwareMonitor."""
        try:
            sensors = self._hw_wmi.ExecQuery(
                "SELECT * FROM Sensor WHERE SensorType = 'Temperature' "
                "AND (Identifier LIKE '/cpu%' OR Parent LIKE '%cpu%')"
            )
        except Exception:
            return None, []

        package_temp: Optional[float] = None
        core_temps: list[Optional[float]] = []

        for s in sensors:
            name = (getattr(s, "Name", "") or "").lower()
            val = getattr(s, "Value", None)
            if val is None:
                continue
            temp = float(val)
            # "Package" / "CPU Package" / "Tctl" / "Tdie"
            if any(kw in name for kw in ("package", "tctl", "tdie", "cpu")):
                if package_temp is None:
                    package_temp = temp
            elif "core" in name:
                core_temps.append(temp)

        # If no core temps found but package temp exists, return package only
        return package_temp, core_temps

    def _read_cpu_temps_native(self) -> tuple[Optional[float], list[Optional[float]]]:
        """Fallback: use psutil sensors_temperatures or ACPI WMI."""
        # psutil sensors_temperatures  limited on Windows but worth a try
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            temps = {}

        for name, entries in temps.items():
            for entry in entries:
                if "core" in name.lower() or "cpu" in name.lower():
                    return entry.current, [entry.current]

        # Last resort: ACPI thermal zones
        try:
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            zones = wmi.ExecQuery("SELECT * FROM MSAcpi_ThermalZoneTemperature")
            for z in zones:
                temp_k = getattr(z, "CurrentTemperature", None)
                if temp_k is not None:
                    # ACPI returns tenths of Kelvin
                    celsius = (temp_k / 10.0) - 273.15
                    if 0 < celsius < 120:
                        return round(celsius, 1), []
        except Exception:
            pass

        return None, []

    #  GPU 

    def _read_gpu(self) -> Optional[GpuInfo]:
        """Try nvidia-smi first, fall back to WMI Win32_VideoController."""
        if self._nvidia_smi:
            gpu = self._read_gpu_nvidia_smi()
            if gpu is not None:
                return gpu

        gpu = self._read_gpu_wmi()
        return gpu

    def _read_gpu_nvidia_smi(self) -> Optional[GpuInfo]:
        try:
            result = subprocess.run(
                [self._nvidia_smi,
                 "--query-gpu=name,utilization.gpu,temperature.gpu,memory.total,memory.used,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            line = result.stdout.strip().splitlines()
            if not line:
                return None
            parts = [p.strip() for p in line[0].split(",")]
            info = GpuInfo()
            info.name = parts[0] if len(parts) > 0 else "N/A"
            info.usage = float(parts[1]) if len(parts) > 1 else 0.0
            info.temp = float(parts[2]) if len(parts) > 2 else None
            info.memory_total = int(parts[3]) if len(parts) > 3 else 0
            info.memory_used = int(parts[4]) if len(parts) > 4 else 0
            info.memory_free = int(parts[5]) if len(parts) > 5 else 0
            return info
        except Exception as exc:
            logger.debug("nvidia-smi error: %s", exc)
            return None

    def _read_gpu_wmi(self) -> Optional[GpuInfo]:
        try:
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
            # Query GPU info from WMI performance counters
            gpu_perf = wmi.ExecQuery(
                "SELECT * FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine"
            )
        except Exception:
            return None

        info = GpuInfo()
        for g in gpu_perf:
            util = getattr(g, "PercentUtilization", None)
            if util is not None:
                info.usage = max(info.usage, float(util))

        # Get GPU name and memory from WMI
        try:
            adapters = wmi.ExecQuery("SELECT * FROM Win32_VideoController")
            for a in adapters:
                name = getattr(a, "Name", "") or ""
                if name:
                    info.name = name
                ram = getattr(a, "AdapterRAM", None)
                if ram:
                    info.memory_total = int(ram) // (1024 * 1024)  # bytes  MB
                break
        except Exception:
            pass

        return info

    #  Memory / Disk / Net 

    @staticmethod
    def _read_memory() -> MemoryInfo:
        vm = psutil.virtual_memory()
        return MemoryInfo(
            total=vm.total, available=vm.available,
            percent=vm.percent, used=vm.used,
        )

    @staticmethod
    def _read_disk() -> DiskInfo:
        total = used = free = 0
        for mount in _get_mount_points():
            try:
                d = psutil.disk_usage(mount)
                total += d.total
                used += d.used
                free += d.free
            except PermissionError:
                continue
        percent = (used / total * 100) if total > 0 else 0.0
        return DiskInfo(total=total, used=used, free=free, percent=round(percent, 1))

    def _read_net(self) -> NetInfo:
        now = psutil.net_io_counters()
        elapsed = time.monotonic() - self._prev_net_time
        sent_per_sec = (now.bytes_sent - self._prev_net.bytes_sent) / elapsed if elapsed > 0 else 0
        recv_per_sec = (now.bytes_recv - self._prev_net.bytes_recv) / elapsed if elapsed > 0 else 0

        self._prev_net, self._prev_net_time = now, time.monotonic()

        return NetInfo(
            bytes_sent=now.bytes_sent, bytes_recv=now.bytes_recv,
            sent_per_sec=sent_per_sec, recv_per_sec=recv_per_sec,
        )


#  Module-level helpers 

def _get_mount_points() -> list[str]:
    """Return physical mount points (skip CD-ROMs)."""
    parts = psutil.disk_partitions()
    return [p.mountpoint for p in parts if "cdrom" not in p.opts.lower()]


def _cpu_brand() -> str:
    """Extract CPU brand string on Windows via WMI or environment fallback."""
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
        cpu_list = wmi.ExecQuery("SELECT * FROM Win32_Processor")
        for cpu in cpu_list:
            name = getattr(cpu, "Name", None)
            if name:
                return name.strip()
    except Exception:
        pass
    return psutil.cpu_info().brand_raw if hasattr(psutil, "cpu_info") else "Unknown"


def _find_nvidia_smi() -> Optional[str]:
    """Locate nvidia-smi on the system PATH."""
    import shutil
    return shutil.which("nvidia-smi")
