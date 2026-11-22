"""Migration 0005 of the appointment app, both ways, on a business's own database cloned from the template and through
the migrator's alias, as ``migrate_hubs`` runs it. Forward, who booked, changed or blocked time in the agenda, saved by
the address of an account without a name, keeps what goes before the «@» (BASE-F119); a person's name and an API key's
keep theirs. Back, nothing changes."""

import datetime as dt

from apps.whatsapp_inbox.tests.test_migrations import database
from base.tests.colleagues import kept_both_ways

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "appointment"
BEFORE = [(APP, "0004_history_restored")]
AFTER = [(APP, "0005_actor_without_address")]
WHO = [
    ("Recurring", "created_by"),
    ("Appointment", "created_by"),
    ("Appointment", "updated_by"),
    ("History", "actor"),
    ("BlockedTime", "created_by"),
]
#: The booking rules: one row at most.
RULES = [("Settings", "updated_by")]
START = dt.datetime(2026, 10, 19, 10, tzinfo=dt.UTC)


def kept_by(apps, database, number: int, who: str) -> None:
    """A series, an appointment with a line of its history and a blocked time, all of them by ``who``."""
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model, _ in WHO}
    lucia = apps.get_model("customer", "Customer").objects.using(database.alias).create(name=f"Lucía {number}")
    rows["Recurring"].create(
        customer=lucia, frequency="weekly", time=START.time(), duration_minutes=30, start_date=START.date(), created_by=who
    )
    end = START + dt.timedelta(minutes=30)
    booked = rows["Appointment"].create(
        number=f"APT-{number}", customer=lucia, start=START, end=end, duration_minutes=30, created_by=who, updated_by=who
    )
    rows["History"].create(appointment=booked, action="created", actor=who)
    rows["BlockedTime"].create(title=f"Break {number}", start=START, end=end, created_by=who)


def test_who_acted_in_the_agenda_saved_by_their_address_keeps_only_what_goes_before_it(database):
    kept_both_ways(database, BEFORE, AFTER, kept_by, WHO, RULES)
