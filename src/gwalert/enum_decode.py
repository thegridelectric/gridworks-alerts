"""Decode integer enum readings using JournalKeeper channel unit_type names."""

from __future__ import annotations

# Positional index lists mirror the sema declaration order (append-only evolution).
ENUM_VALUES_BY_TYPE: dict[str, list[str]] = {
    "change.relay.state": ["CloseRelay", "OpenRelay"],
    "gpm.from.hz.method": ["Constant"],
    "gw1.actor.class": [
        "NoActor",
        "PrimaryScada",
        "SecondaryScada",
        "PowerMeter",
        "LocalControl",
        "LeafAlly",
        "DerivedGenerator",
        "PicoCycler",
        "HpBoss",
        "I2cRelayMultiplexer",
        "I2cZeroTenMultiplexer",
        "Hubitat",
        "Relay",
        "MultipurposeSensor",
        "HoneywellThermostat",
        "ApiTankModule",
        "ApiFlowModule",
        "ZeroTenOutputer",
        "ApiBtuMeter",
        "SiegLoop",
        "GpioSensor",
        "I2cBus",
        "I2cRelayBoard",
        "I2cThermistorReader",
    ],
    "gw1.emission.method": ["OnTrigger", "Periodic", "AsyncAndPeriodic"],
    "gw1.lc.top.state": [
        "Dormant",
        "UsingNonElectricBackup",
        "Normal",
        "ScadaBlind",
        "Monitor",
    ],
    "gw1.leaf.ally.all.tanks.state": [
        "Dormant",
        "Initializing",
        "HpOnStoreOff",
        "HpOnStoreCharge",
        "HpOffStoreOff",
        "HpOffStoreDischarge",
        "HpOffNonElectricBackup",
    ],
    "gw1.leaf.ally.buffer.only.state": [
        "Dormant",
        "Initializing",
        "HpOn",
        "HpOff",
        "HpOffNonElectricBackup",
    ],
    "gw1.local.control.all.tanks.state": [
        "Initializing",
        "HpOnStoreOff",
        "HpOnStoreCharge",
        "HpOffStoreOff",
        "HpOffStoreDischarge",
        "Dormant",
    ],
    "gw1.local.control.buffer.only.state": [
        "Initializing",
        "HpOn",
        "HpOff",
        "Dormant",
    ],
    "gw1.local.control.standby.top.state": ["EverythingOff", "Dormant"],
    "gw1.main.auto.state": ["LocalControl", "LeafTransactiveNode", "Dormant"],
    "gw1.quantity": [
        "Unknown",
        "Unitless",
        "Power",
        "Energy",
        "Temperature",
        "FlowRate",
        "Volume",
        "Voltage",
        "Current",
        "Percent",
        "Frequency",
    ],
    "gw1.seasonal.storage.mode": ["AllTanks", "BufferOnly"],
    "gw1.system.mode": ["Heating", "Standby", "MonitorOnly"],
    "gw1.unit": [
        "Unknown",
        "Unitless",
        "FahrenheitX100",
        "Watts",
        "WattHours",
        "Gallons",
        "GpmX100",
        "Seconds",
        "SecondsX10",
        "Milliseconds",
    ],
    "hz.calc.method": ["BasicExpWeightedAvg", "BasicButterWorth", "UniformWindow"],
    "log.level": ["Critical", "Error", "Warning", "Info", "Debug", "Trace"],
    "relay.closed.or.open": ["RelayClosed", "RelayOpen"],
    "relay.energization.state": ["DeEnergized", "Energized"],
    "relay.wiring.config": ["NormallyClosed", "NormallyOpen", "DoubleThrow"],
    "sh.actor.class": [
        "NoActor",
        "PrimaryScada",
        "SecondaryScada",
        "Scada",
        "HomeAlone",
        "BooleanActuator",
        "PowerMeter",
        "LocalControl",
        "LeafAlly",
        "Atn",
        "SimpleSensor",
        "MultipurposeSensor",
        "Thermostat",
        "HubitatTelemetryReader",
        "HubitatTankModule",
        "HubitatPoller",
        "I2cRelayMultiplexer",
        "FlowTotalizer",
        "Relay",
        "Admin",
        "Fsm",
        "Parentless",
        "Hubitat",
        "HoneywellThermostat",
        "ApiTankModule",
        "ApiFlowModule",
        "PicoCycler",
        "I2cDfrMultiplexer",
        "I2cZeroTenMultiplexer",
        "ZeroTenOutputer",
        "AtomicAlly",
        "SynthGenerator",
        "FakeAtn",
        "PumpDoctor",
        "StratBoss",
        "HpRelayBoss",
        "HpBoss",
        "ApiBtuMeter",
        "DerivedGenerator",
        "SiegLoop",
        "GpioSensor",
        "I2cBus",
        "I2cRelayBoard",
        "I2cThermistorReader",
    ],
}


def decode_enum_value(unit_type: str, value: int) -> str:
    values = ENUM_VALUES_BY_TYPE.get(unit_type)
    if values is None:
        return str(value)
    if 0 <= value < len(values):
        return values[value]
    return str(value)


def decode_relay_state_value(value: int) -> str:
    """RelayState channel values index relay.energization.state."""
    energization = ENUM_VALUES_BY_TYPE["relay.energization.state"]
    if 0 <= value < len(energization):
        return energization[value]
    return str(value)


def energization_for_contacts_closed(wiring_config: str = "NormallyClosed") -> str:
    """Return the energization state when relay contacts are closed."""
    if wiring_config == "NormallyOpen":
        return "Energized"
    return "DeEnergized"


def map_top_state_for_relay5(state: str) -> str:
    """Map gw1.main.auto.state values to legacy relay5 boss semantics."""
    if state == "LeafTransactiveNode":
        return "Scada"
    return state
