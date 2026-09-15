"""Zone detectors read temperatures by the channel's unit and role, not by name."""

import pytest

from gwalert.alert_generator import AlertGenerator
from gwalert.units import temperature_f, zone_channel_role

HOUSE = "spruce"
T0 = 1_789_480_800_000
GW1 = "gw1.unit"
SH = "spaceheat.telemetry.name"


@pytest.mark.parametrize(
    ("unit_type", "unit", "value", "expected_f"),
    [
        (GW1, "FahrenheitX100", 6566, 65.66),
        (SH, "AirTempFTimes1000", 65660, 65.66),
        (SH, "WaterTempFTimes1000", 120000, 120.0),
        (SH, "AirTempCTimes1000", 20000, 68.0),
        (SH, "WaterTempCTimes1000", 50000, 122.0),
        (SH, "CelsiusTimes100", 1959, 67.262),
    ],
)
def test_temperature_f_by_unit(unit_type, unit, value, expected_f) -> None:
    assert temperature_f(unit_type, unit, value) == pytest.approx(expected_f)


def test_non_temperature_units_are_none() -> None:
    assert temperature_f(SH, "MicroVolts", 2300250) is None
    assert temperature_f(GW1, "Unitless", 1) is None
    assert temperature_f(None, None, 1) is None


def test_zone_channel_roles() -> None:
    assert zone_channel_role("zone1-bedrooms-set") == "setpoint"
    assert zone_channel_role("zone1-bedrooms-temp") == "air"
    assert zone_channel_role("zone1-bedrooms-floor-temp") == "floor"
    assert zone_channel_role("zone2-living-rm-gw-temp") == "gw"
    assert zone_channel_role("zone1-bedrooms-gw-microvolts") is None
    assert zone_channel_role("zone1-bedrooms-heat-call") is None


def channel(unit_type: str, unit: str, *values: int) -> dict:
    return {
        "times": [T0 + i * 60_000 for i in range(len(values))],
        "values": list(values),
        "unit": unit,
        "unit_type": unit_type,
    }


def make_generator(
    monkeypatch, channels: dict[str, dict]
) -> tuple[AlertGenerator, list[str]]:
    gen = AlertGenerator()
    gen.selected_house_aliases = [HOUSE]
    gen.houses_in_standby = []
    gen.critical_zones_by_house = {HOUSE: {"known": False, "list": []}}
    gen.alert_status = {HOUSE: {}}
    gen.data = {HOUSE: channels}
    sent: list[str] = []
    monkeypatch.setattr(
        gen, "send_alert", lambda message, house, alias: sent.append(message)
    )
    return gen, sent


def test_spruce_floor_temp_in_fahrenheit_x100_is_not_freezing(monkeypatch) -> None:
    gen, sent = make_generator(
        monkeypatch,
        {
            "zone1-bedrooms-floor-temp": channel(GW1, "FahrenheitX100", 6566),
            "zone1-bedrooms-gw-temp": channel(SH, "CelsiusTimes100", 1959),
            "zone1-bedrooms-gw-microvolts": channel(SH, "MicroVolts", 2300250),
        },
    )
    gen.check_zone_freezing()
    assert sent == []
    assert gen.alert_status[HOUSE]["zone_freezing"]["zone1-bedrooms"] is False


def test_smart_thermostat_zone_freezing_alerts(monkeypatch) -> None:
    gen, sent = make_generator(
        monkeypatch,
        {"zone1-bedrooms-temp": channel(SH, "AirTempFTimes1000", 35000)},
    )
    gen.check_zone_freezing()
    assert sent == ["zone1-bedrooms is below 40F"]


def test_gw_temp_in_celsius_is_the_freezing_fallback(monkeypatch) -> None:
    gen, sent = make_generator(
        monkeypatch,
        {"zone3-upstairs-gw-temp": channel(SH, "CelsiusTimes100", 200)},
    )
    gen.check_zone_freezing()
    assert sent == ["zone3-upstairs is below 40F"]


def test_setpoint_check_converts_both_sides_by_unit(monkeypatch) -> None:
    # Spruce: setpoint 69.96 F and floor 65.66 F, both FahrenheitX100; 4.3 F below.
    gen, sent = make_generator(
        monkeypatch,
        {
            "zone1-bedrooms-set": channel(GW1, "FahrenheitX100", 6996),
            "zone1-bedrooms-floor-temp": channel(GW1, "FahrenheitX100", 6566),
        },
    )
    gen.check_zone_below_setpoint()
    assert sent == ["zone1-bedrooms is significantly below setpoint"]


def test_setpoint_check_is_ok_when_within_tolerance(monkeypatch) -> None:
    gen, sent = make_generator(
        monkeypatch,
        {
            "zone1-bedrooms-set": channel(SH, "AirTempFTimes1000", 68000),
            "zone1-bedrooms-temp": channel(SH, "AirTempFTimes1000", 67000),
        },
    )
    gen.check_zone_below_setpoint()
    assert sent == []
