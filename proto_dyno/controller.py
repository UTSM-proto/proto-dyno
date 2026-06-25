from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .dl24 import DL24Load, Telemetry
from .safety import SafetyLimits, current_for_power, safety_fault


@dataclass(frozen=True)
class ControlStatus:
    telemetry: Telemetry | None
    requested_power_w: float
    target_current_a: float
    load_enabled: bool
    fault: str | None
    mode: str


class DynoController:
    def __init__(self, load: DL24Load, limits: SafetyLimits):
        limits.validate()
        self.load = load
        self.limits = limits
        self.requested_power_w = 0.0
        self.load_enabled = False
        self.last_telemetry_s: float | None = None
        self.last_fault: str | None = None
        self.native_cp_available = False

    def set_requested_power(self, watts: float) -> None:
        self.requested_power_w = max(0.0, min(float(watts), self.limits.max_power_w))

    def enable(self) -> None:
        self.last_fault = None
        self.load.enable()
        self.load_enabled = True

    def stop(self, reason: str | None = None) -> None:
        try:
            self.load.set_current_a(0.0)
            self.load.stop()
        finally:
            self.load_enabled = False
            if reason:
                self.last_fault = reason

    def poll_once(self) -> ControlStatus:
        telemetry = self.load.read_telemetry()
        self.last_telemetry_s = monotonic()

        fault = safety_fault(telemetry.voltage_v, telemetry.temp_c, self.limits)
        if fault:
            self.stop(fault)
            return ControlStatus(telemetry, self.requested_power_w, 0.0, False, fault, "stopped")

        target_current = 0.0
        mode = "cc-fallback"
        if self.load_enabled:
            if self.native_cp_available and self.load.set_power_w(self.requested_power_w):
                mode = "native-cp"
            else:
                voltage = telemetry.voltage_v or 0.0
                target_current = current_for_power(self.requested_power_w, voltage, self.limits)
                self.load.set_current_a(target_current)

        return ControlStatus(
            telemetry=telemetry,
            requested_power_w=self.requested_power_w,
            target_current_a=target_current,
            load_enabled=self.load_enabled,
            fault=self.last_fault,
            mode=mode,
        )

    def check_telemetry_timeout(self) -> str | None:
        if self.last_telemetry_s is None:
            return None
        age_s = monotonic() - self.last_telemetry_s
        if age_s > self.limits.telemetry_timeout_s:
            reason = f"Telemetry lost for {age_s:.1f} s"
            self.stop(reason)
            return reason
        return None
