"""The ticket counter of each business day."""

import datetime as dt

from .conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_one_counter_a_day():
    from apps.kitchen.models.numbering import DayCounter

    DayCounter.objects.create(day=dt.date(2026, 10, 14), last_number=3)
    assert refused(lambda: DayCounter.objects.create(day=dt.date(2026, 10, 14)))
