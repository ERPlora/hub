"""Models of the appointments' numbers: what the database itself refuses, and what a row looks like.

The operations check before writing; these constraints are the last line when two writes race or a
second write path (the admin) skips the rules.
"""

from apps.appointment.models.numbering import Counter

from .conftest import HUB_DB, MONDAY, refused

pytestmark = HUB_DB


def test_one_counter_per_day():
    Counter.objects.create(day=MONDAY, last_number=3)
    refused(lambda: Counter.objects.create(day=MONDAY))
