"""The rows the reads load: the intervals of a day come in opening order, whatever order they were saved in."""

from .conftest import HUB_DB, make_day
from .test_queries import run, t

pytestmark = HUB_DB


def test_the_intervals_of_a_day_come_in_opening_order():
    make_day(1, ("17:00", "20:00"), ("10:00", "14:00"))
    assert [i.open_time for i in run("schedule.week.get").days[1].intervals] == [
        t("10:00"),
        t("17:00"),
    ]
