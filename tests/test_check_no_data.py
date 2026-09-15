"""check_no_data judges freshness against its own query window, not the clock after."""

from gwalert.alert_generator import AlertGenerator

HOUSE = "beech"
MINUTE_MS = 60_000
END_MS = 1_789_480_800_000


def make_generator(
    monkeypatch, *, latest_ms: int, end_ms: int = END_MS
) -> tuple[AlertGenerator, list[str]]:
    """One house whose newest alert-channel reading is at latest_ms."""
    gen = AlertGenerator()  # binds the session factory only; no connection is made
    gen.freshness_end_ms = end_ms
    gen.latest_data_ms = {HOUSE: latest_ms}
    sent: list[str] = []
    monkeypatch.setattr(
        gen, "send_alert", lambda message, house, alias: sent.append(message)
    )
    return gen, sent


def test_slow_full_fetch_does_not_age_fresh_data(monkeypatch) -> None:
    # Newest reading 4 min before the window end; the clock is 6 min past it.
    gen, sent = make_generator(monkeypatch, latest_ms=END_MS - 4 * MINUTE_MS)
    monkeypatch.setattr(gen, "reference_epoch", lambda: (END_MS + 6 * MINUTE_MS) / 1000)
    gen.check_no_data()
    assert sent == []
    assert gen.alert_status[HOUSE]["no_data"] is False


def test_stale_data_at_window_end_alerts_once(monkeypatch) -> None:
    gen, sent = make_generator(monkeypatch, latest_ms=END_MS - 11 * MINUTE_MS)
    gen.check_no_data()
    gen.check_no_data()
    assert sent == ["No data coming in since 11.0 minutes"]
    assert gen.alert_status[HOUSE]["no_data"] is True


def test_data_returning_clears_the_alert_state(monkeypatch) -> None:
    gen, sent = make_generator(monkeypatch, latest_ms=END_MS - 11 * MINUTE_MS)
    gen.check_no_data()
    gen.latest_data_ms[HOUSE] = END_MS - MINUTE_MS
    gen.check_no_data()
    assert len(sent) == 1
    assert gen.alert_status[HOUSE]["no_data"] is False
