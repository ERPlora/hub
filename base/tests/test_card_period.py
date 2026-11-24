"""A period on an assistant's card, as the person's language writes an interval (CLDR, Babel's ``format_interval``):
two days «21–31 dic 2026», a part of a day «26 nov 2026, 14:00–15:00», a moment at the business's hour. A card said the
start and the end apart, or only the start: «Comida · Descanso · 26 nov 2026, 14:00» had no end (hub#2347)."""

import datetime as dt

import pytest

from base.assistant.card_period import period
from base.tenancy.tests.business import HUB_DB, in_business_a

__all__ = ["in_business_a"]
#: The space CLDR writes around the dash of an interval: a thin one.
THIN = "\u2009"
#: And the one before «PM»: a narrow one that does not break.
NARROW = "\u202f"

UTC = dt.UTC


@pytest.mark.parametrize(
    ("start", "end", "language", "said"),
    [
        (dt.date(2026, 12, 21), dt.date(2026, 12, 31), "es", "21–31 dic 2026"),
        (dt.date(2026, 12, 21), dt.date(2026, 12, 31), "en", f"Dec 21{THIN}–{THIN}31, 2026"),
        (dt.date(2026, 12, 21), dt.date(2026, 12, 21), "es", "21 dic 2026"),
        (dt.date(2026, 12, 21), dt.date(2027, 1, 3), "es", f"21 dic 2026{THIN}–{THIN}3 ene 2027"),
        (dt.time(14, 0), dt.time(15, 0), "es", "14:00–15:00"),
        (dt.time(14, 0), dt.time(15, 0), "en", f"2:00{THIN}–{THIN}3:00{NARROW}PM"),
    ],
)
def test_days_and_hours_as_the_language_writes_an_interval(start, end, language, said):
    assert period(start, end, language) == said


@HUB_DB
@pytest.mark.parametrize(
    ("language", "said"),
    [("es", "26 nov 2026, 14:00–15:00"), ("en", f"Nov 26, 2026, 2:00{THIN}–{THIN}3:00{NARROW}PM")],
)
def test_two_moments_of_a_day_at_the_businesss_hour(language, said):
    """Business A keeps Madrid's clock: 13:00 UTC is 14:00 there in November."""
    assert period(dt.datetime(2026, 11, 26, 13, tzinfo=UTC), dt.datetime(2026, 11, 26, 14, tzinfo=UTC), language) == said


@HUB_DB
def test_two_moments_of_different_days_say_each_day():
    start, end = dt.datetime(2026, 11, 26, 13, tzinfo=UTC), dt.datetime(2026, 11, 27, 8, tzinfo=UTC)
    assert period(start, end, "es") == f"26 nov 2026, 14:00{THIN}–{THIN}27 nov 2026, 9:00"
