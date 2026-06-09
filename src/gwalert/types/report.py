from gwalert.types._aliases import GwMessage


class ChannelReadings(GwMessage):
    channel_name: str
    value_list: list[int]
    scada_read_time_unix_ms_list: list[int]


class MachineStates(GwMessage):
    machine_handle: str
    state_list: list[str]
    unix_ms_list: list[int]


class Report(GwMessage):
    channel_reading_list: list[ChannelReadings] = []
    state_list: list[MachineStates] = []
