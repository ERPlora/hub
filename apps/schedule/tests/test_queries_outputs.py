"""What the reads hand over: a day ready to say, with its weekday, in the language asked."""

import datetime as dt

from django.utils import translation

from apps.schedule.queries.outputs import day_label

from .conftest import HUB_DB

pytestmark = HUB_DB


def test_a_day_is_said_with_its_weekday_in_the_language_asked_whatever_the_thread_speaks():
    tuesday = dt.date(2030, 3, 5)
    with translation.override("en"):
        assert day_label(tuesday, "es") == "martes, 5 de marzo de 2030"
        assert translation.get_language() == "en"
    with translation.override("es"):
        assert day_label(tuesday, "en") == "Tuesday, March 5, 2030"
