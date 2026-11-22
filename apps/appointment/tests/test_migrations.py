"""Migrations of Citas.

0003: an appointment saved with the end the wall clock summed ends its real minutes after its start.

Before hub#636 the end was the start plus the duration on the business's wall clock, so a booking over the change of
time was saved an hour longer (October) or shorter (March) than booked. The migration writes
``end = start + duration_minutes`` of real time (timestamps subtract in real time) on every row where they differ and
leaves the rest as they are. Backwards nothing changes: the wrong end is not worth keeping.

The function of the ``RunPython`` is called the way the migration runs it, with the app registry and a schema editor
whose connection is business A's own database, inside the test's transaction.

0004: «restored» comes and goes with its migration, on a business's own database cloned from the template for the
test, through the migrator's alias as ``migrate_hubs`` runs it.

0005, run the same way: a history line saved with the address of whoever changed the appointment, when their account
has no name, keeps what goes before the «@» (BASE-F119); a person's name and an API key's keep theirs. Back, nothing
changes.
"""

import datetime as dt
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import IntegrityError, connections, transaction

from apps.appointment.models import Appointment
from apps.whatsapp_inbox.tests.test_migrations import migrate
from base.tenancy.context import current_alias

from .conftest import HUB_DB, MADRID, at, make_appointment

MIGRATION = import_module("apps.appointment.migrations.0003_end_in_real_minutes")


class _SchemaEditor:
    @property
    def connection(self):
        return connections[current_alias()]


@HUB_DB
def test_an_end_the_wall_clock_got_wrong_is_written_its_real_minutes_after_the_start(salon):
    # make_appointment sums on the wall clock, as the app did before hub#636: 01:37 + 90 min on the day of 23 hours
    # lands at 03:07, 30 real minutes later; on the day of 25 hours, 150.
    spring = make_appointment(salon.lucia, salon.ana, [salon.cut], at(dt.date(2027, 3, 28), "01:37"), duration=90, number="APT-23H")
    autumn = make_appointment(salon.lucia, salon.ana, [salon.cut], at(dt.date(2026, 10, 25), "01:37"), duration=90, number="APT-25H")
    assert Appointment.objects.get(pk=spring.pk).end - spring.start == dt.timedelta(minutes=30)
    assert Appointment.objects.get(pk=autumn.pk).end - autumn.start == dt.timedelta(minutes=150)
    MIGRATION.forwards(global_apps, _SchemaEditor())
    fixed = {pk: Appointment.objects.get(pk=pk) for pk in (spring.pk, autumn.pk)}
    assert all(row.end - row.start == dt.timedelta(minutes=90) for row in fixed.values())
    assert fixed[spring.pk].end.astimezone(MADRID).isoformat() == "2027-03-28T04:07:00+02:00"
    assert fixed[autumn.pk].end.astimezone(MADRID).isoformat() == "2026-10-25T02:07:00+01:00"


@HUB_DB
def test_a_row_already_right_is_not_touched(salon):
    row = make_appointment(salon.lucia, salon.ana, [salon.cut], at(dt.date(2026, 10, 19), "10:00"), duration=90)
    before = Appointment.objects.get(pk=row.pk)
    MIGRATION.forwards(global_apps, _SchemaEditor())
    after = Appointment.objects.get(pk=row.pk)
    assert (after.end, after.updated_at) == (before.end, before.updated_at)
    assert after.end - after.start == dt.timedelta(minutes=90)


def history_line(state, database, number: str, **fields):
    """A «restored» line of a new appointment ``number``, written with the models of the migration ``state``."""
    customer = state.get_model("customer", "Customer").objects.using(database.alias).create(name="Lucía Pérez")
    start = at(dt.date(2026, 10, 19), "10:00")
    appointment = state.get_model("appointment", "Appointment").objects.using(database.alias).create(
        number=number, customer=customer, start=start, end=start + dt.timedelta(minutes=30), duration_minutes=30
    )
    return state.get_model("appointment", "History").objects.using(database.alias).create(
        appointment=appointment, action="restored", **fields
    )


def test_the_history_line_of_a_restored_appointment_comes_and_goes_with_its_migration(database):
    """0004 adds «restored» to the actions a history line may say (hub#1326); backwards, the check is the old one."""
    before = migrate(database, [("appointment", "0003_end_in_real_minutes")])
    with pytest.raises(IntegrityError), transaction.atomic(using=database.alias):
        history_line(before, database, "APT-BEFORE")

    after = migrate(database, [("appointment", "0004_history_restored")])

    assert history_line(after, database, "APT-AFTER").action == "restored"


def test_a_history_line_saved_with_a_colleague_s_address_keeps_only_what_goes_before_it(database):
    restored = [("appointment", "0004_history_restored")]
    before = migrate(database, restored)
    for number, actor in enumerate(("bea.lopez@example.com", "Luis García", "API · orders@shop.example", "")):
        history_line(before, database, f"APT-{number}", actor=actor)
    kept = ["", "API · orders@shop.example", "Luis García", "bea.lopez"]

    after = migrate(database, [("appointment", "0005_actor_without_address")])

    assert actors(after, database) == kept
    assert actors(migrate(database, restored), database) == kept


def actors(state, database) -> list[str]:
    return sorted(state.get_model("appointment", "History").objects.using(database.alias).values_list("actor", flat=True))
