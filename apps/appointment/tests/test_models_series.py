"""Models of the repeating appointments: what the database itself refuses, and what a row looks like.

The operations check before writing; these constraints are the last line when two writes race or a
second write path (the admin) skips the rules.
"""

import datetime as dt

from apps.appointment.models.series import Recurring, RecurringService

from .conftest import HUB_DB, MONDAY, make_customer, make_member, make_service, refused

pytestmark = HUB_DB


def test_a_series_refuses_a_rule_that_cannot_repeat():
    customer, ana = make_customer(), make_member()
    base = {
        "customer": customer,
        "customer_name": customer.name,
        "staff": ana,
        "staff_name": ana.full_name,
        "time": dt.time(10),
        "duration_minutes": 30,
        "start_date": MONDAY,
    }
    refused(lambda: Recurring.objects.create(frequency="yearly", **base))
    refused(lambda: Recurring.objects.create(frequency="weekly", day_of_week=7, **base))
    refused(
        lambda: Recurring.objects.create(
            frequency="weekly", end_date=MONDAY - dt.timedelta(days=1), **base
        )
    )
    refused(
        lambda: Recurring.objects.create(frequency="weekly", max_occurrences=0, **base)
    )
    series = Recurring.objects.create(frequency="weekly", **base)
    RecurringService.objects.create(
        recurring=series, service=make_service(), position=0
    )
    assert series.lines.count() == 1
