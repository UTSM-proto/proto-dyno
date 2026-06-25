from proto_dyno.dl24 import DL24Load


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.read_buffer = bytearray()

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        command = data[2]
        if command >= 0x10:
            values = {
                0x10: 1,
                0x11: 12340,
                0x12: 1250,
                0x16: 42,
                0x17: 150,
            }
            value = values.get(command, 0)
            self.read_buffer.extend(b"\xCA\xCB" + value.to_bytes(3, "big") + b"\xCE\xCF")
        else:
            self.read_buffer.extend(b"\x6F")
        return len(data)

    def read(self, size: int = 1) -> bytes:
        if not self.read_buffer:
            return b""
        out = bytes(self.read_buffer[:size])
        del self.read_buffer[:size]
        return out

    def reset_input_buffer(self) -> None:
        self.read_buffer.clear()

    def close(self) -> None:
        pass


def test_read_telemetry() -> None:
    fake = FakeSerial()
    load = DL24Load(device=fake)
    telemetry = load.read_telemetry()
    assert telemetry.voltage_v == 12.34
    assert telemetry.current_a == 1.25
    assert round(telemetry.power_w, 3) == 15.425
    assert telemetry.temp_c == 42
    assert telemetry.output_enabled is True
    assert telemetry.target_current_a == 1.5


def test_set_current_frame() -> None:
    fake = FakeSerial()
    load = DL24Load(device=fake)
    load.set_current_a(1.25)
    assert fake.writes[-1] == bytes([0xB1, 0xB2, 0x02, 0x01, 0x19, 0xB6])
