from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Protocol

import serial
from serial.tools import list_ports


BAUDRATE = 9600

GET_OUTPUT = 0x10
GET_VOLTAGE = 0x11
GET_CURRENT = 0x12
GET_TEMP = 0x16
GET_SET_CURRENT = 0x17
GET_SET_CUTOFF = 0x18

SET_OUTPUT = 0x01
SET_CURRENT = 0x02
SET_CUTOFF = 0x03


class SerialLike(Protocol):
    def write(self, data: bytes) -> int | None: ...
    def read(self, size: int = 1) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class DeviceCandidate:
    port: str
    description: str
    hwid: str
    likely: bool

    def label(self) -> str:
        marker = "*" if self.likely else " "
        return f"{marker} {self.port} - {self.description} [{self.hwid}]"


@dataclass(frozen=True)
class Telemetry:
    voltage_v: float | None
    current_a: float | None
    power_w: float | None
    temp_c: float | None
    output_enabled: bool | None
    target_current_a: float | None
    timestamp_s: float


def find_candidates() -> list[DeviceCandidate]:
    likely_terms = ("DL24", "ATORCH", "CH340", "USB-SERIAL", "CP210", "FTDI", "UART", "SERIAL")
    candidates: list[DeviceCandidate] = []
    for port in list_ports.comports():
        text = " ".join(str(x or "") for x in (port.device, port.description, port.hwid, port.manufacturer))
        likely = any(term in text.upper() for term in likely_terms)
        candidates.append(DeviceCandidate(port.device, port.description or "", port.hwid or "", likely))
    return sorted(candidates, key=lambda item: (not item.likely, item.port))


class DL24Error(RuntimeError):
    pass


class DL24Load:
    """Minimal DL24/PX100-style serial protocol wrapper."""

    def __init__(self, port: str | None = None, device: SerialLike | None = None, timeout_s: float = 0.4):
        if device is None:
            if port is None:
                raise ValueError("port is required when device is not supplied")
            device = serial.Serial(port=port, baudrate=BAUDRATE, timeout=timeout_s, write_timeout=timeout_s)
        self.device = device

    def close(self) -> None:
        self.device.close()

    def stop(self) -> None:
        self._write_int(SET_OUTPUT, 0)

    def enable(self) -> None:
        self._write_int(SET_OUTPUT, 0x0100)

    def set_current_a(self, current_a: float) -> None:
        current_a = max(0.0, min(float(current_a), 99.99))
        self._write_float(SET_CURRENT, current_a)

    def set_cutoff_voltage_v(self, voltage_v: float) -> None:
        self._write_float(SET_CUTOFF, max(0.0, min(float(voltage_v), 99.99)))

    def set_power_w(self, power_w: float) -> bool:
        _ = power_w
        return False

    def read_telemetry(self) -> Telemetry:
        voltage = self.get_voltage_v()
        current = self.get_current_a()
        temp = self.get_temp_c()
        output = self.get_output_enabled()
        target_current = self.get_target_current_a()
        power = None if voltage is None or current is None else voltage * current
        return Telemetry(voltage, current, power, temp, output, target_current, monotonic())

    def get_output_enabled(self) -> bool | None:
        value = self._read_int(GET_OUTPUT)
        return None if value is None else bool(value)

    def get_voltage_v(self) -> float | None:
        value = self._read_int(GET_VOLTAGE)
        return None if value is None else value / 1000.0

    def get_current_a(self) -> float | None:
        value = self._read_int(GET_CURRENT)
        return None if value is None else value / 1000.0

    def get_temp_c(self) -> float | None:
        value = self._read_int(GET_TEMP)
        return None if value is None else float(value)

    def get_target_current_a(self) -> float | None:
        value = self._read_int(GET_SET_CURRENT)
        return None if value is None else value / 100.0

    def get_cutoff_voltage_v(self) -> float | None:
        value = self._read_int(GET_SET_CUTOFF)
        return None if value is None else value / 100.0

    def _send(self, command: int, payload: bytes) -> None:
        frame = bytes([0xB1, 0xB2, command, *payload, 0xB6])
        self.device.write(frame)

    def _read_response(self, start: bytes, length: int) -> bytes:
        deadline = monotonic() + 1.0
        buffer = bytearray()
        while monotonic() < deadline:
            chunk = self.device.read(max(1, length - len(buffer)))
            if chunk:
                buffer.extend(chunk)
                idx = buffer.find(start)
                if idx >= 0:
                    buffer = buffer[idx:]
                    while len(buffer) < length and monotonic() < deadline:
                        buffer.extend(self.device.read(length - len(buffer)))
                    if len(buffer) >= length:
                        return bytes(buffer[:length])
            else:
                continue
        raise DL24Error("Timed out waiting for serial response")

    def _read_int(self, command: int) -> int | None:
        self._send(command, b"\x00\x00")
        response = self._read_response(b"\xCA\xCB", 7)
        if response[5] != 0xCE or response[6] != 0xCF:
            raise DL24Error(f"Bad response for command 0x{command:02x}: {response.hex(' ')}")
        return int.from_bytes(response[2:5], "big")

    def _write_int(self, command: int, value: int) -> None:
        self._write_payload(command, int(value).to_bytes(2, "big"))

    def _write_float(self, command: int, value: float) -> None:
        whole = int(value)
        frac = int(round((value - whole) * 100))
        self._write_payload(command, bytes([whole, frac]))

    def _write_payload(self, command: int, payload: bytes) -> None:
        if hasattr(self.device, "reset_input_buffer"):
            self.device.reset_input_buffer()
        self._send(command, payload)
        ack = self._read_response(b"\x6F", 1)
        if ack != b"\x6F":
            raise DL24Error(f"Bad ack for command 0x{command:02x}: {ack.hex(' ')}")
