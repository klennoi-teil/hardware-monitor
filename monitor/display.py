"""Rich terminal dashboard for live hardware monitoring."""

from __future__ import annotations

import time
from typing import Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from monitor.sensors import (
    DiskInfo,
    GpuInfo,
    MemoryInfo,
    NetInfo,
    Snapshot,
)

#  Colour helpers 

_TEMP_OK = "green"
_TEMP_WARN = "yellow"
_TEMP_HOT = "red"


def _temp_style(celsius: Optional[float]) -> str:
    if celsius is None:
        return "dim"
    if celsius < 60:
        return _TEMP_OK
    if celsius < 80:
        return _TEMP_WARN
    return _TEMP_HOT


def _pct_style(pct: float) -> str:
    if pct < 50:
        return "green"
    if pct < 80:
        return "yellow"
    return "red"


def _format_bytes(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _format_rate(n: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB/s"


def _format_uptime(seconds: float) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    parts.append(f"{hours:02d}h{mins:02d}m{secs:02d}s")
    return " ".join(parts)


#  Dashboard builder 

class Dashboard:
    """Builds a Rich Layout from a Snapshot."""

    def __init__(self, theme: str = "auto"):
        self._console = Console()
        self._theme = theme

    def build(self, snap: Snapshot) -> Layout:
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["header"].update(self._build_header(snap))
        layout["body"].update(self._build_body(snap))
        layout["footer"].update(self._build_footer(snap))

        return layout

    #  Header 

    def _build_header(self, snap: Snapshot) -> Panel:
        """Title bar with system name and time."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snap.timestamp))
        title = Text(f"  Hardware Monitor  |  {ts}", style="bold cyan")
        subtitle = Text(
            f"CPU: {snap.cpu.name}  |  "
            f"Uptime: {_format_uptime(snap.uptime)}  |  "
            f"Processes: {snap.process_count}",
            style="dim",
        )
        return Panel(Group(title, subtitle), style="bright_blue")

    #  Body 

    def _build_body(self, snap: Snapshot) -> Columns:
        panels = [
            self._cpu_panel(snap.cpu),
            self._memory_panel(snap.memory),
            self._disk_panel(snap.disk),
            self._net_panel(snap.net),
        ]
        if snap.gpu and snap.gpu.name != "N/A":
            panels.insert(1, self._gpu_panel(snap.gpu))
        return Columns(panels, equal=False, expand=True)

    def _cpu_bar(self, pct: float, width: int = 20) -> Progress:
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=width, style="grey23", finished_style=_pct_style(pct)),
            TextColumn(f"[{_pct_style(pct)}]{pct:5.1f}%"),
            console=self._console,
        )
        progress.add_task("", total=100, completed=pct)
        return progress

    def _cpu_panel(self, cpu) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        table.add_row(f"[bold]Frequency:[/] {cpu.frequency:.0f} MHz")
        table.add_row(f"[bold]Cores:[/] {cpu.physical_cores} physical / {cpu.logical_cores} logical")

        #  Temperature 
        if cpu.temp_package is not None:
            style_pkg = _temp_style(cpu.temp_package)
            table.add_row(f"[bold]Temp:[/] [{style_pkg}]{cpu.temp_package:.1f} C[/]")
            if cpu.temp_cores:
                core_strs = ", ".join(
                    f"[{_temp_style(t)}]{t:.0f}C[/]" if t is not None else "N/A"
                    for t in cpu.temp_cores
                )
                table.add_row(f"[dim]Cores:[/] {core_strs}")
        else:
            table.add_row("[dim]Temp: N/A[/]")

        #  Usage bars 
        table.add_row("")
        table.add_row(f"[bold]Total:[/]")
        table.add_row(self._cpu_bar(cpu.usage_total))

        if cpu.usage_per_core:
            table.add_row("")
            table.add_row("[bold]Per core:[/]")
            for i, pct in enumerate(cpu.usage_per_core):
                table.add_row(self._cpu_bar(pct, width=15))

        return Panel(table, title="[bold]CPU[/]", border_style="bright_cyan")

    def _gpu_panel(self, gpu: GpuInfo) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        table.add_row(f"[bold]Model:[/] {gpu.name}")
        table.add_row(f"[bold]Usage:[/] [{_pct_style(gpu.usage)}]{gpu.usage:.0f}%[/]")
        table.add_row(self._cpu_bar(gpu.usage, width=20))

        if gpu.temp is not None:
            table.add_row(f"[bold]Temp:[/] [{_temp_style(gpu.temp)}]{gpu.temp:.0f} C[/]")
        else:
            table.add_row("[dim]Temp: N/A[/]")

        if gpu.memory_total > 0:
            mem_pct = gpu.memory_used / gpu.memory_total * 100
            table.add_row(
                f"[bold]VRAM:[/] {_format_bytes(gpu.memory_used * 1024 * 1024)}"
                f" / {_format_bytes(gpu.memory_total * 1024 * 1024)}"
                f"  [{_pct_style(mem_pct)}]{mem_pct:.0f}%[/]"
            )

        return Panel(table, title="[bold]GPU[/]", border_style="bright_magenta")

    def _memory_panel(self, mem: MemoryInfo) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        pct = mem.percent
        table.add_row(f"[bold]Usage:[/] [{_pct_style(pct)}]{pct:.1f}%[/]")
        table.add_row(self._cpu_bar(pct, width=20))
        table.add_row("")
        table.add_row(f"[bold]Total:[/]    {_format_bytes(mem.total)}")
        table.add_row(f"[bold]Used:[/]     {_format_bytes(mem.used)}")
        table.add_row(f"[bold]Available:[/] {_format_bytes(mem.available)}")

        return Panel(table, title="[bold]Memory[/]", border_style="bright_green")

    def _disk_panel(self, disk: DiskInfo) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        pct = disk.percent
        table.add_row(f"[bold]Usage:[/] [{_pct_style(pct)}]{pct:.1f}%[/]")
        table.add_row(self._cpu_bar(pct, width=20))
        table.add_row("")
        table.add_row(f"[bold]Total:[/] {_format_bytes(disk.total)}")
        table.add_row(f"[bold]Used:[/]  {_format_bytes(disk.used)}")
        table.add_row(f"[bold]Free:[/]  {_format_bytes(disk.free)}")

        return Panel(table, title="[bold]Disk[/]", border_style="bright_yellow")

    def _net_panel(self, net: NetInfo) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        table.add_row(f"[bold] Download:[/] {_format_rate(net.recv_per_sec)}")
        table.add_row(f"[bold] Upload:[/]   {_format_rate(net.sent_per_sec)}")
        table.add_row("")
        table.add_row(f"[dim]Total :[/] {_format_bytes(net.bytes_recv)}")
        table.add_row(f"[dim]Total :[/] {_format_bytes(net.bytes_sent)}")

        return Panel(table, title="[bold]Network[/]", border_style="bright_blue")

    #  Footer 

    @staticmethod
    def _build_footer(snap: Snapshot) -> Panel:
        text = Text("Press Ctrl+C to exit", style="dim")
        return Panel(Align.center(text), style="grey23")


#  Runner 

def run_dashboard(
    refresh_interval: float,
    cpu_display: str = "all",
    theme: str = "auto",
    enable_logging: bool = False,
    logger_fn=None,
) -> None:
    """
    Run the live dashboard until Ctrl+C is pressed.

    Parameters
    ----------
    refresh_interval : float
        Seconds between refreshes.
    cpu_display : str
        "all" or "total".
    theme : str
        "auto", "dark", or "light".
    enable_logging : bool
        Whether to call *logger_fn* each sample.
    logger_fn : callable or None
        Called with (Snapshot) each sample.
    """
    from monitor.sensors import SensorReader

    reader = SensorReader()
    dashboard = Dashboard(theme=theme)
    log_counter = 0

    with Live(dashboard.build(reader.snapshot()), refresh_per_second=1 / refresh_interval, screen=True) as live:
        try:
            while True:
                snap = reader.snapshot()
                live.update(dashboard.build(snap))
                log_counter += 1

                if enable_logging and logger_fn:
                    logger_fn(snap)

                time.sleep(refresh_interval)
        except KeyboardInterrupt:
            pass
