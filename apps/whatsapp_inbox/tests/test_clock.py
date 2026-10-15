"""The app's clock: the one seam the tests turn instead of the real time."""

import datetime as dt
from zoneinfo import ZoneInfo

from apps.whatsapp_inbox import clock

MADRID = ZoneInfo("Europe/Madrid")


def test_now_is_aware_and_in_utc():
    moment = clock.now()
    assert moment.tzinfo is not None
    assert moment.utcoffset() == dt.timedelta(0)


def test_the_business_month_is_madrid_s(monkeypatch):
    # 31 October 23:30 UTC is already 1 November in Madrid (UTC+1 in winter).
    monkeypatch.setattr(
        clock, "now", lambda: dt.datetime(2026, 10, 31, 23, 30, tzinfo=dt.UTC)
    )
    assert clock.business_month() == "2026-11"


def test_the_business_zone_is_madrid_in_phase_1():
    assert clock.BUSINESS_ZONE == MADRID
