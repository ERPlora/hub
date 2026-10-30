"""Migration 0002 of the attendance app (review of 2026-10-15, findings 4 and 7), reversible:

- a correction says explicitly whether the system made it and keeps the name of who made it, so a user
  deleted later never turns their corrections into the system's;
- the exact coordinates of a day clocked from the shared device are dropped: nobody asked for them
  (only a personal device, when the business requires it, keeps them); the distance, inside/outside
  and the accuracy stay.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry
and a schema editor whose connection is the test database.
"""

from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from apps.attendance.models import Correction, Record

from .conftest import make_member, utc

pytestmark = pytest.mark.django_db

MIGRATION = import_module("apps.attendance.migrations.0002_correction_author")


class _SchemaEditor:
    connection = connection


def historical_apps():
    """The models as 0002 sees them (its fields added): ``created_by`` still names control's user."""
    return MigrationLoader(connection).project_state(("attendance", "0002_correction_author")).apps


def run_forward():
    MIGRATION.forwards(historical_apps(), _SchemaEditor())


def _day(**fields) -> Record:
    return Record.objects.create(
        member=make_member(),
        clock_in_at=utc("2026-10-06T07:00"),
        work_date=utc("2026-10-06T07:00").date(),
        **fields,
    )


def test_existing_corrections_get_who_made_them(make_user):
    day = _day()
    boss = make_user("boss", first_name="Marta", last_name="Jefa")
    common = {
        "record": day,
        "old_clock_in_at": day.clock_in_at,
        "old_status": "open",
        "new_clock_in_at": day.clock_in_at,
        "new_status": "open",
        "reason": "x",
    }
    then = historical_apps().get_model("attendance", "Correction")
    common["record_id"] = common.pop("record").pk
    by_boss = then.objects.create(created_by_id=boss.pk, **common)
    by_system = then.objects.create(created_by_id=None, **common)
    run_forward()
    by_boss, by_system = Correction.objects.get(pk=by_boss.pk), Correction.objects.get(pk=by_system.pk)
    by_boss.refresh_from_db()
    by_system.refresh_from_db()
    assert (by_boss.is_system, by_boss.created_by_name) == (False, "Marta Jefa")
    assert (by_system.is_system, by_system.created_by_name) == (True, "")


def test_coordinates_of_the_shared_device_are_dropped_and_the_rest_stays():
    shared = _day(
        in_lat=40.4,
        in_lng=-3.7,
        in_accuracy_m=9.0,
        in_distance_m=12.0,
        in_within_radius=True,
    )
    personal = _day(
        source="personal",
        in_lat=40.4,
        in_lng=-3.7,
        in_distance_m=12.0,
        in_within_radius=True,
    )
    run_forward()
    shared.refresh_from_db()
    personal.refresh_from_db()
    assert (shared.in_lat, shared.in_lng, shared.out_lat, shared.out_lng) == (
        None,
        None,
        None,
        None,
    )
    assert (shared.in_accuracy_m, shared.in_distance_m, shared.in_within_radius) == (
        9.0,
        12.0,
        True,
    )
    assert (personal.in_lat, personal.in_lng) == (40.4, -3.7)


def test_it_reverses():
    MIGRATION.backwards(historical_apps(), _SchemaEditor())
    operations = [
        op
        for op in MIGRATION.Migration.operations
        if op.__class__.__name__ == "RunPython"
    ]
    assert operations and all(op.reversible for op in operations)
