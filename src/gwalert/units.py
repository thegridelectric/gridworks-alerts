"""Temperature readings to degrees F, by the unit the channel declares.

A journal channel names its unit twice: `unit_type` is the sema word the
spelling belongs to (`gw1.unit`, `spaceheat.telemetry.name`) and `unit` is
the member. A detector converts through this table, never by guessing the
scale from the channel's name.
"""

from collections.abc import Callable


def c_to_f(celsius: float) -> float:
    return celsius * 9 / 5 + 32


TEMPERATURE_F_BY_UNIT: dict[tuple[str, str], Callable[[int], float]] = {
    ("gw1.unit", "FahrenheitX100"): lambda v: v / 100,
    ("spaceheat.telemetry.name", "AirTempFTimes1000"): lambda v: v / 1000,
    ("spaceheat.telemetry.name", "WaterTempFTimes1000"): lambda v: v / 1000,
    ("spaceheat.telemetry.name", "AirTempCTimes1000"): lambda v: c_to_f(v / 1000),
    ("spaceheat.telemetry.name", "WaterTempCTimes1000"): lambda v: c_to_f(v / 1000),
    ("spaceheat.telemetry.name", "CelsiusTimes100"): lambda v: c_to_f(v / 100),
}


def temperature_f(unit_type: str | None, unit: str | None, value: int) -> float | None:
    """The reading in degrees F, or None when the unit is not a temperature."""
    if unit_type is None or unit is None:
        return None
    convert = TEMPERATURE_F_BY_UNIT.get((unit_type, unit))
    if convert is None:
        return None
    return convert(value)


# A zone channel's role is its name's suffix. Longer suffixes first so
# "-floor-temp" and "-gw-temp" are not read as "-temp".
ZONE_ROLE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("floor", "-floor-temp"),
    ("gw", "-gw-temp"),
    ("air", "-temp"),
    ("setpoint", "-set"),
)


def zone_channel_role(channel_name: str) -> str | None:
    for role, suffix in ZONE_ROLE_SUFFIXES:
        if channel_name.endswith(suffix):
            return role
    return None
