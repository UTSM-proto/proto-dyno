from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .controller import ControlStatus, DynoController
from .dl24 import DL24Error, DL24Load, find_candidates
from .safety import SafetyLimits


class DynoApp(tk.Tk):
    def __init__(self, port: str | None, limits: SafetyLimits):
        super().__init__()
        self.title("proto-dyno DL24 Load Slider")
        self.minsize(600, 420)
        self.limits = limits
        self.port_var = tk.StringVar(value=port or "")
        self.status_var = tk.StringVar(value="Disconnected")
        self.mode_var = tk.StringVar(value="cc-fallback")
        self.voltage_var = tk.StringVar(value="-- V")
        self.current_var = tk.StringVar(value="-- A")
        self.power_var = tk.StringVar(value="-- W")
        self.temp_var = tk.StringVar(value="-- C")
        self.output_var = tk.StringVar(value="stopped")
        self.target_current_var = tk.StringVar(value="0.000 A")
        self.slider_var = tk.DoubleVar(value=0.0)
        self.event_queue: queue.Queue[ControlStatus | str | Exception] = queue.Queue()
        self.controller: DynoController | None = None
        self.worker_stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.refresh_ports()
        self.after(100, self.drain_events)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)

        ttk.Label(root, text="Device").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(root, textvariable=self.port_var, state="normal")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Refresh", command=self.refresh_ports).grid(row=0, column=2)
        ttk.Button(root, text="Connect", command=self.connect).grid(row=0, column=3, padx=(8, 0))

        ttk.Separator(root).grid(row=1, column=0, columnspan=4, sticky="ew", pady=12)

        slider_frame = ttk.Frame(root)
        slider_frame.grid(row=2, column=0, columnspan=4, sticky="ew")
        slider_frame.columnconfigure(0, weight=1)
        ttk.Label(slider_frame, text="Road Load Request").grid(row=0, column=0, sticky="w")
        self.slider_label = ttk.Label(slider_frame, text="0.0 W")
        self.slider_label.grid(row=0, column=1, sticky="e")
        slider = ttk.Scale(
            slider_frame,
            variable=self.slider_var,
            from_=0,
            to=self.limits.max_power_w,
            orient="horizontal",
            command=self.on_slider,
        )
        slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        button_frame = ttk.Frame(root)
        button_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=12)
        ttk.Button(button_frame, text="Enable Load", command=self.enable_load).grid(row=0, column=0)
        ttk.Button(button_frame, text="Stop Load", command=self.stop_load).grid(row=0, column=1, padx=8)

        telemetry = ttk.LabelFrame(root, text="Telemetry", padding=10)
        telemetry.grid(row=4, column=0, columnspan=4, sticky="nsew")
        for idx in range(4):
            telemetry.columnconfigure(idx, weight=1)
        self._metric(telemetry, 0, "Voltage", self.voltage_var)
        self._metric(telemetry, 1, "Current", self.current_var)
        self._metric(telemetry, 2, "Power", self.power_var)
        self._metric(telemetry, 3, "Temperature", self.temp_var)

        state = ttk.Frame(root)
        state.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        ttk.Label(state, text="State:").grid(row=0, column=0, sticky="w")
        ttk.Label(state, textvariable=self.output_var).grid(row=0, column=1, sticky="w", padx=(4, 20))
        ttk.Label(state, text="Target current:").grid(row=0, column=2, sticky="w")
        ttk.Label(state, textvariable=self.target_current_var).grid(row=0, column=3, sticky="w", padx=(4, 20))
        ttk.Label(state, text="Mode:").grid(row=0, column=4, sticky="w")
        ttk.Label(state, textvariable=self.mode_var).grid(row=0, column=5, sticky="w", padx=(4, 0))

        warning = (
            "Software clamp defaults: 50 W, 3 A, 36 V max, 2.5 V min, 70 C max. "
            "Advertised DL24 limits are not safe continuous dyno limits."
        )
        ttk.Label(root, text=warning, wraplength=560, foreground="#8a4b00").grid(
            row=6, column=0, columnspan=4, sticky="ew", pady=(12, 0)
        )
        ttk.Label(root, textvariable=self.status_var).grid(row=7, column=0, columnspan=4, sticky="ew", pady=(12, 0))

    def _metric(self, parent: ttk.Frame, column: int, label: str, variable: tk.StringVar) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="ew", padx=6)
        ttk.Label(frame, text=label).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, textvariable=variable, font=("", 16, "bold")).grid(row=1, column=0, sticky="w")

    def refresh_ports(self) -> None:
        candidates = find_candidates()
        self.port_combo["values"] = [candidate.label() for candidate in candidates]
        if not self.port_var.get() and candidates:
            self.port_var.set(candidates[0].port)

    def selected_port(self) -> str:
        raw = self.port_var.get().strip()
        if " - " in raw:
            raw = raw.split(" - ", 1)[0].strip("* ")
        return raw

    def connect(self) -> None:
        port = self.selected_port()
        if not port:
            messagebox.showerror("No device", "Select or enter a serial port first.")
            return
        self.disconnect_existing()
        try:
            load = DL24Load(port=port)
            load.set_cutoff_voltage_v(self.limits.min_voltage_v)
            load.stop()
        except Exception as exc:
            messagebox.showerror("Connection failed", str(exc))
            return
        self.controller = DynoController(load, self.limits)
        self.worker_stop.clear()
        self.worker = threading.Thread(target=self.worker_loop, name="dl24-poll", daemon=True)
        self.worker.start()
        self.status_var.set(f"Connected to {port}; load disabled")

    def disconnect_existing(self) -> None:
        self.worker_stop.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=1.5)
        if self.controller:
            try:
                self.controller.stop("Disconnect")
                self.controller.load.close()
            except Exception:
                pass
        self.controller = None

    def worker_loop(self) -> None:
        assert self.controller is not None
        interval_ms = 1.0 / self.limits.update_rate_hz
        while not self.worker_stop.wait(interval_ms):
            try:
                fault = self.controller.check_telemetry_timeout()
                if fault:
                    self.event_queue.put(fault)
                self.event_queue.put(self.controller.poll_once())
            except (DL24Error, OSError, ValueError) as exc:
                try:
                    self.controller.stop(f"Serial error: {exc}")
                except Exception:
                    pass
                self.event_queue.put(exc)
                self.worker_stop.set()

    def drain_events(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, ControlStatus):
                self.apply_status(event)
            elif isinstance(event, Exception):
                self.status_var.set(f"Fault: {event}")
                self.output_var.set("stopped")
            else:
                self.status_var.set(f"Fault: {event}")
                self.output_var.set("stopped")
        self.after(100, self.drain_events)

    def apply_status(self, status: ControlStatus) -> None:
        telemetry = status.telemetry
        if telemetry:
            self.voltage_var.set("-- V" if telemetry.voltage_v is None else f"{telemetry.voltage_v:.3f} V")
            self.current_var.set("-- A" if telemetry.current_a is None else f"{telemetry.current_a:.3f} A")
            self.power_var.set("-- W" if telemetry.power_w is None else f"{telemetry.power_w:.1f} W")
            self.temp_var.set("-- C" if telemetry.temp_c is None else f"{telemetry.temp_c:.0f} C")
            self.output_var.set("running" if telemetry.output_enabled else "stopped")
        self.target_current_var.set(f"{status.target_current_a:.3f} A")
        self.mode_var.set(status.mode)
        if status.fault:
            self.status_var.set(f"Fault: {status.fault}")
        else:
            self.status_var.set(f"Requested {status.requested_power_w:.1f} W")

    def on_slider(self, _value: str) -> None:
        watts = float(self.slider_var.get())
        self.slider_label.configure(text=f"{watts:.1f} W")
        if self.controller:
            self.controller.set_requested_power(watts)

    def enable_load(self) -> None:
        if not self.controller:
            messagebox.showerror("Not connected", "Connect to a DL24 serial device first.")
            return
        try:
            self.controller.enable()
        except Exception as exc:
            messagebox.showerror("Enable failed", str(exc))

    def stop_load(self) -> None:
        if self.controller:
            self.controller.stop("Manual stop")
            self.status_var.set("Manual stop")

    def on_close(self) -> None:
        self.disconnect_existing()
        self.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DL24 dyno load slider")
    parser.add_argument("--port", help="serial port such as COM7")
    parser.add_argument("--max-power-w", type=float, default=50.0)
    parser.add_argument("--max-current-a", type=float, default=3.0)
    parser.add_argument("--max-voltage-v", type=float, default=36.0)
    parser.add_argument("--min-voltage-v", type=float, default=2.5)
    parser.add_argument("--max-temp-c", type=float, default=70.0)
    parser.add_argument("--update-rate-hz", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limits = SafetyLimits(
        max_power_w=args.max_power_w,
        max_current_a=args.max_current_a,
        max_voltage_v=args.max_voltage_v,
        min_voltage_v=args.min_voltage_v,
        max_temp_c=args.max_temp_c,
        update_rate_hz=args.update_rate_hz,
    )
    app = DynoApp(args.port, limits)
    app.mainloop()


if __name__ == "__main__":
    main()
