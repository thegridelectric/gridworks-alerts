from gwalert.types import Glitch, LayoutLite, Report, SnapshotSpaceheat


def test_report_parses_channel_readings() -> None:
    report = Report.from_dict(
        {
            "ChannelReadingList": [
                {
                    "ChannelName": "hp-odu-pwr",
                    "ValueList": [26, 96],
                    "ScadaReadTimeUnixMsList": [1708518800235, 1708518808236],
                    "TypeName": "channel.readings",
                    "Version": "002",
                }
            ],
            "StateList": [],
            "TypeName": "report",
            "Version": "003",
        }
    )
    assert report.channel_reading_list[0].channel_name == "hp-odu-pwr"
    assert report.channel_reading_list[0].value_list == [26, 96]


def test_layout_lite_parses_critical_zones() -> None:
    layout = LayoutLite.from_dict(
        {
            "CriticalZoneList": ["Down"],
            "SystemMode": "Standby",
            "TypeName": "layout.lite",
            "Version": "012",
        }
    )
    assert layout.critical_zone_list == ["Down"]
    assert layout.system_mode == "Standby"


def test_glitch_parses_summary() -> None:
    glitch = Glitch.from_dict(
        {
            "FromGNodeAlias": "hw1.isone.me.versant.keene.beech.scada",
            "Type": "Critical",
            "Summary": "Pump fault",
            "TypeName": "glitch",
            "Version": "000",
        }
    )
    assert glitch.type == "Critical"
    assert glitch.summary == "Pump fault"


def test_snapshot_spaceheat_accepts_minimal_payload() -> None:
    snapshot = SnapshotSpaceheat.from_dict(
        {
            "FromGNodeAlias": "hw1.isone.me.versant.keene.spruce.scada",
            "SnapshotTimeUnixMs": 1709915800472,
            "LatestReadingList": [],
            "LatestStateList": [],
            "TypeName": "snapshot.spaceheat",
            "Version": "003",
        }
    )
    assert isinstance(snapshot, SnapshotSpaceheat)
