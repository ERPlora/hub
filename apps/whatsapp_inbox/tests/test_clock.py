"""The app's clock: the one seam the tests turn instead of the real time."""

import datetime as dt

from apps.whatsapp_inbox import clock


def test_now_is_aware_and_in_utc():
    moment = clock.now()
    assert moment.tzinfo is not None
    assert moment.utcoffset() == dt.timedelta(0)


def test_the_month_of_the_allowance_is_the_one_erplora_com_counts_in(monkeypatch):
    # 31 October 23:30 UTC is already 1 November in Madrid, and still October in erplora.com's count, a UTC month.
    monkeypatch.setattr(clock, "now", lambda: dt.datetime(2026, 10, 31, 23, 30, tzinfo=dt.UTC))
    assert clock.allowance_month() == "2026-10"
