"""check_no_data judges freshness against the fetch window, not the clock after."""

from gwalert.alert_generator import AlertGenerator

HOUSE = "beech"
MINUTE_MS = 60_000


def make_generator(
    monkeypatch, *, end_ms: int, latest_ms: int
) -> tuple[AlertGenerator, list[str]]:
    """One house, newest reading at latest_ms, fetch window ending at end_ms."""
    gen = AlertGenerator.__new__(AlertGenerator)
    gen.max_time_no_data = 10 * 60
    gen.hours_back = 2
    gen.selected_house_aliases = [HOUSE]
    gen.alert_status = {HOUSE: {}}
    gen.data = {
        HOUSE: {
            "zone1-temp": {
                "times": [latest_ms - MINUTE_MS, latest_ms],
                "values": [1, 2],
            }
        }
    }
    gen.data_end_ms = end_ms
    sent: list[str] = []
    monkeypatch.setattr(
        gen, "send_alert", lambda message, house, alias: sent.append(message)
    )
    return gen, sent


def test_slow_fetch_does_not_alert_on_fresh_data(monkeypatch) -> None:
    # Newest reading 4 min before the window end; the fetch then took 6 min.
    end_ms = 1_789_480_800_000
    gen, sent = make_generator(
        monkeypatch, end_ms=end_ms, latest_ms=end_ms - 4 * MINUTE_MS
    )
    monkeypatch.setattr(gen, "reference_epoch", lambda: (end_ms + 6 * MINUTE_MS) / 1000)
    gen.check_no_data()
    assert sent == []
    assert gen.alert_status[HOUSE]["no_data"] is False


def test_stale_data_at_window_end_alerts(monkeypatch) -> None:
    end_ms = 1_789_480_800_000
    gen, sent = make_generator(
        monkeypatch, end_ms=end_ms, latest_ms=end_ms - 11 * MINUTE_MS
    )
    gen.check_no_data()
    assert sent == ["No data coming in since 11.0 minutes"]
    assert gen.alert_status[HOUSE]["no_data"] is True


def test_readings_after_window_end_are_ignored(monkeypatch) -> None:
    end_ms = 1_789_480_800_000
    gen, sent = make_generator(
        monkeypatch, end_ms=end_ms, latest_ms=end_ms - 11 * MINUTE_MS
    )
    gen.data[HOUSE]["zone1-temp"]["times"].append(end_ms + MINUTE_MS)
    gen.check_no_data()
    assert len(sent) == 1
