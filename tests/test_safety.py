from proto_dyno.safety import SafetyLimits, current_for_power, safety_fault


def test_power_to_current_clamps_by_power_and_current() -> None:
    limits = SafetyLimits(max_power_w=50, max_current_a=3)
    assert current_for_power(100, 10, limits) == 3
    assert current_for_power(20, 10, limits) == 2


def test_power_to_current_stops_below_min_voltage() -> None:
    limits = SafetyLimits(min_voltage_v=2.5)
    assert current_for_power(20, 2.0, limits) == 0


def test_safety_faults() -> None:
    limits = SafetyLimits(max_voltage_v=36, min_voltage_v=2.5, max_temp_c=70)
    assert "exceeds" in safety_fault(37, None, limits)
    assert "below" in safety_fault(2.4, None, limits)
    assert "Temperature" in safety_fault(12, 71, limits)
    assert safety_fault(12, 25, limits) is None
