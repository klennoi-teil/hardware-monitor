"""GUI window — real-time hardware monitor with CustomTkinter + matplotlib."""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

import customtkinter as ctk
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from monitor.sensors import SensorReader, Snapshot

matplotlib.use("Agg")  # non-interactive backend for embedding


# ── Colour helpers ───────────────────────────────────────────────────────

_COL_OK = "#22c55e"
_COL_WARN = "#eab308"
_COL_CRIT = "#ef4444"

_THRESHOLDS = {
    "cpu":  {"warning": 75, "critical": 85},
    "gpu":  {"warning": 80, "critical": 90},
}


def _temp_colour(c: Optional[float], warn: float, crit: float) -> str:
    if c is None:
        return "#888888"
    if c >= crit:
        return _COL_CRIT
    if c >= warn:
        return _COL_WARN
    return _COL_OK


def _pct_colour(p: float) -> str:
    if p >= 80:
        return _COL_CRIT
    if p >= 50:
        return _COL_WARN
    return _COL_OK


# ── GUI Window ───────────────────────────────────────────────────────────

class MonitorWindow(ctk.CTk):
    """Main GUI window with real-time hardware monitoring."""

    def __init__(self, interval: float = 2.0) -> None:
        super().__init__()

        self._interval = interval
        self._reader = SensorReader()
        self._last_snap: Optional[Snapshot] = None

        # Temperature history: {name: deque(maxlen=60)}
        self._history: dict[str, deque] = {
            "cpu": deque(maxlen=60),
            "gpu": deque(maxlen=60),
        }
        self._time_history: deque = deque(maxlen=60)

        # ── Window setup ─────────────────────────────────────────────
        self.title("Hardware Monitor")
        self.geometry("720x520")
        self.minsize(640, 460)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Main container ───────────────────────────────────────────
        main = ctk.CTkFrame(self, corner_radius=12)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)  # chart row expands

        # ── Header ───────────────────────────────────────────────────
        self._header = ctk.CTkLabel(
            main, text="Hardware Monitor  |  Waiting for data...",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._header.grid(row=0, column=0, sticky="w", padx=8, pady=(4, 8))

        # ── Sensor cards row ─────────────────────────────────────────
        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        cards.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._cpu_card = self._make_card(cards, "CPU", 0)
        self._gpu_card = self._make_card(cards, "GPU", 1)
        self._mem_card = self._make_card(cards, "Memory", 2)
        self._disk_card = self._make_card(cards, "Disk", 3)

        # ── Temperature chart ────────────────────────────────────────
        self._chart_frame = ctk.CTkFrame(main, corner_radius=8)
        self._chart_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 6))
        self._chart_frame.grid_rowconfigure(0, weight=1)
        self._chart_frame.grid_columnconfigure(0, weight=1)

        self._fig, self._ax = plt.subplots(figsize=(8, 2.2), dpi=90)
        self._fig.patch.set_facecolor("#1a1a2e")
        self._ax.set_facecolor("#1a1a2e")
        self._ax.set_title("Temperature History  (last 60 samples)",
                           fontsize=9, color="#aaaaaa", pad=6)
        self._ax.set_ylabel("deg C", fontsize=8, color="#888888")
        self._ax.tick_params(colors="#888888", labelsize=7)
        self._ax.grid(alpha=0.15, color="#555555")
        self._fig.tight_layout(pad=0.6)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self._chart_frame)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self._cpu_line, = self._ax.plot([], [], label="CPU", color=_COL_OK, lw=1.8)
        self._gpu_line, = self._ax.plot([], [], label="GPU", color="#a855f7", lw=1.8)
        self._ax.legend(loc="upper left", fontsize=7, labelcolor="#cccccc",
                        framealpha=0.3)

        # ── Status bar ───────────────────────────────────────────────
        self._status = ctk.CTkLabel(
            main, text="Initializing...",
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self._status.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 2))

        # ── Start update loop ───────────────────────────────────────
        self._running = True
        self.after(200, self._update)

        # Handle close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Card builder ─────────────────────────────────────────────────

    @staticmethod
    def _make_card(parent: ctk.CTkFrame, title: str, col: int) -> dict:
        frame = ctk.CTkFrame(parent, corner_radius=8)
        frame.grid(row=0, column=col, sticky="nsew", padx=4, pady=2)
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(frame, text=title,
                             font=ctk.CTkFont(size=13, weight="bold"))
        label.grid(row=0, column=0, pady=(4, 0))

        temp = ctk.CTkLabel(frame, text="--°C",
                            font=ctk.CTkFont(size=22, weight="bold"))
        temp.grid(row=1, column=0)

        bar = ctk.CTkProgressBar(frame, height=12, corner_radius=4)
        bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 0))
        bar.set(0)

        pct = ctk.CTkLabel(frame, text="--%",
                           font=ctk.CTkFont(size=11))
        pct.grid(row=3, column=0, pady=(0, 4))

        extra = ctk.CTkLabel(frame, text="",
                             font=ctk.CTkFont(size=9))
        extra.grid(row=4, column=0, pady=(0, 4))

        return {"frame": frame, "temp": temp, "bar": bar, "pct": pct, "extra": extra}

    # ── Update loop ──────────────────────────────────────────────────

    def _update(self) -> None:
        if not self._running:
            return

        try:
            snap = self._reader.snapshot()
            self._last_snap = snap
            self._update_header(snap)
            self._update_cpu(snap)
            self._update_gpu(snap)
            self._update_mem(snap)
            self._update_disk(snap)
            self._update_chart(snap)
            self._update_status(snap)
        except Exception as exc:
            self._status.configure(text=f"Error: {exc}")

        self.after(int(self._interval * 1000), self._update)

    # ── Section updaters ─────────────────────────────────────────────

    def _update_header(self, snap: Snapshot) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime(snap.timestamp))
        cpu_name = snap.cpu.name.split()[:2] if snap.cpu.name != "N/A" else ""
        cpu_short = " ".join(cpu_name) if cpu_name else "CPU"
        self._header.configure(text=f"Hardware Monitor  |  {ts}  |  {cpu_short}")

    def _update_cpu(self, snap: Snapshot) -> None:
        c = self._cpu_card
        temp = snap.cpu.temp_package
        warn, crit = _THRESHOLDS["cpu"]["warning"], _THRESHOLDS["cpu"]["critical"]

        temp_text = f"{temp:.0f}C" if temp is not None else "--C"
        col = _temp_colour(temp, warn, crit)
        c["temp"].configure(text=temp_text, text_color=col)

        pct = snap.cpu.usage_total
        c["bar"].set(pct / 100.0)
        c["bar"].configure(progress_color=_pct_colour(pct))
        c["pct"].configure(text=f"{pct:.1f}%")

        freq = snap.cpu.frequency
        extra = f"{freq:.0f} MHz  |  {snap.cpu.physical_cores}C/{snap.cpu.logical_cores}T" if freq else ""
        c["extra"].configure(text=extra)

    def _update_gpu(self, snap: Snapshot) -> None:
        c = self._gpu_card
        gpu = snap.gpu
        warn, crit = _THRESHOLDS["gpu"]["warning"], _THRESHOLDS["gpu"]["critical"]

        if gpu and gpu.name != "N/A":
            temp = gpu.temp
            temp_text = f"{temp:.0f}C" if temp is not None else "--C"
            col = _temp_colour(temp, warn, crit)
            c["temp"].configure(text=temp_text, text_color=col)

            pct = gpu.usage
            c["bar"].set(pct / 100.0)
            c["bar"].configure(progress_color=_pct_colour(pct))
            c["pct"].configure(text=f"{pct:.1f}%")

            if gpu.memory_total > 0:
                vram_pct = gpu.memory_used / gpu.memory_total * 100
                extra = f"VRAM: {gpu.memory_used}/{gpu.memory_total} MB"
            else:
                extra = ""
            c["extra"].configure(text=extra)
        else:
            c["temp"].configure(text="N/A", text_color="#888888")
            c["bar"].set(0)
            c["pct"].configure(text="--%")
            c["extra"].configure(text="")

    def _update_mem(self, snap: Snapshot) -> None:
        c = self._mem_card
        pct = snap.memory.percent
        c["temp"].configure(text=f"{pct:.1f}%", text_color=_pct_colour(pct))
        c["bar"].set(pct / 100.0)
        c["bar"].configure(progress_color=_pct_colour(pct))
        # Show used/total in GB
        used_gb = snap.memory.used / (1024**3)
        total_gb = snap.memory.total / (1024**3)
        c["pct"].configure(text=f"{used_gb:.1f} / {total_gb:.1f} GB")

    def _update_disk(self, snap: Snapshot) -> None:
        c = self._disk_card
        pct = snap.disk.percent
        c["temp"].configure(text=f"{pct:.1f}%", text_color=_pct_colour(pct))
        c["bar"].set(pct / 100.0)
        c["bar"].configure(progress_color=_pct_colour(pct))
        used_gb = snap.disk.used / (1024**3)
        total_gb = snap.disk.total / (1024**3)
        c["pct"].configure(text=f"{used_gb:.1f} / {total_gb:.1f} GB")

    # ── Chart ────────────────────────────────────────────────────────

    def _update_chart(self, snap: Snapshot) -> None:
        now = time.monotonic()
        self._time_history.append(now)

        cpu_t = snap.cpu.temp_package
        self._history["cpu"].append(cpu_t if cpu_t is not None else None)

        gpu_t = snap.gpu.temp if snap.gpu else None
        self._history["gpu"].append(gpu_t if gpu_t is not None else None)

        # Build X axis: seconds relative to newest point
        if len(self._time_history) >= 2:
            base = self._time_history[-1]
            xs = [t - base for t in self._time_history]
        else:
            xs = list(range(len(self._time_history)))

        cpu_y = [t if t is not None else None for t in self._history["cpu"]]
        gpu_y = [t if t is not None else None for t in self._history["gpu"]]

        self._cpu_line.set_data(xs, cpu_y)
        self._gpu_line.set_data(xs, gpu_y)

        self._ax.relim()
        self._ax.autoscale_view(True, True, True)
        self._ax.set_xlim(xs[-1] - 65, xs[-1] + 5) if xs else None

        self._canvas.draw_idle()

    # ── Status ───────────────────────────────────────────────────────

    def _update_status(self, snap: Snapshot) -> None:
        uptime = time.time() - snap.uptime
        up_str = f"{int(uptime // 3600):02d}h{int(uptime % 3600 // 60):02d}m"
        self._status.configure(
            text=f"Uptime: {up_str}  |  Processes: {snap.process_count}  |  Refresh: {self._interval}s"
        )

    # ── Close ────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self._running = False
        self.destroy()


def run_gui(interval: float = 2.0) -> None:
    """Launch the GUI monitor window."""
    app = MonitorWindow(interval=interval)
    app.mainloop()
