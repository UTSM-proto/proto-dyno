from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyLimits:
    max_power_w: float = 50.0
    max_current_a: float = 3.0
    max_voltage_v: float = 36.0
    min_voltage_v: float = 2.5
    max_temp_c: float = 70.0
    update_rate_hz: float = 2.0
    telemetry_timeout_s: float = 2.0

    def validate(self) -> None:
        if self.max_power_w <= 0:
            raise ValueError("max_power_w must be positive")
        if self.max_current_a <= 0:
            raise ValueError("max_current_a must be positive")
        if self.max_voltage_v <= self.min_voltage_v:
            raise ValueError("max_voltage_v must be greater than min_voltage_v")
        if self.update_rate_hz <= 0:
            raise ValueError("update_rate_hz must be positive")


def clamp_power_request(requested_w: float, limits: SafetyLimits) -> float:
    return max(0.0, min(float(requested_w), limits.max_power_w))


def current_for_power(requested_w: float, measured_v: float, limits: SafetyLimits) -> float:
    safe_power_w = clamp_power_request(requested_w, limits)
    if measured_v <= 0:
        return 0.0
    if measured_v < limits.min_voltage_v:
        return 0.0
    return max(0.0, min(safe_power_w / measured_v, limits.max_current_a))


def safety_fault(voltage_v: float | None, temp_c: float | None, limits: SafetyLimits) -> str | None:
    if voltage_v is not None:
        if voltage_v > limits.max_voltage_v:
            return f"Voltage {voltage_v:.2f} V exceeds max {limits.max_voltage_v:.2f} V"
        if voltage_v < limits.min_voltage_v:
            return f"Voltage {voltage_v:.2f} V is below min {limits.min_voltage_v:.2f} V"
    if temp_c is not None and temp_c > limits.max_temp_c:
        return f"Temperature {temp_c:.1f} C exceeds max {limits.max_temp_c:.1f} C"
    return None
