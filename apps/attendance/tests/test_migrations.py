"""Migration 0002 of the attendance app, on a business's own database:

- a correction gets the fields that say whether the system made it and the name of who made it; the corrections
  already there are left as they are;
- the exact coordinates of a day clocked from the shared device are dropped: nobody asked for them
  (only a personal device, when the business requires it, keeps them); the distance, inside/outside
  and the accuracy stay.

Its function runs the way ``migrate`` runs it, with the app registry of 0002 and a schema editor whose connection is
the business's database, inside the test's transaction.
"""

from importlib import import_module
from types import SimpleNamespace

from django.db import connections
from django.db.migrations.loader import MigrationLoader

from apps.attendance.models import Correction, Record
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.migration_steps import python_steps
from base.tests.test_auth_views import ON_HUB_A

from .conftest import make_member, utc

pytestmark = ON_HUB_A

MODULE = "apps.attendance.migrations.0002_correction_author"
MIGRATION = import_module(MODULE)


def _on_business_a():
    """What ``migrate`` hands the migration's functions: the app registry of 0002 and a schema editor."""
    database = connections[hubs.HUB_A_ALIAS]
    historical = MigrationLoader(database).project_state(("attendance", "0002_correction_author")).apps
    return historical, SimpleNamespace(connection=database)


def run_forward():
    MIGRATION.forwards(*_on_business_a())


def _day(**fields) -> Record:
    return Record.objects.create(
        member=make_member(),
        clock_in_at=utc("2026-10-06T07:00"),
        work_date=utc("2026-10-06T07:00").date(),
        **fields,
    )


def test_its_only_python_drops_the_coordinates():
    assert python_steps(MODULE) == ["forwards"]


def test_a_correction_already_there_is_left_as_it_is(hub_a):
    with use_hub(hub_a):
        day = _day()
        correction = Correction.objects.create(
            record=day,
            old_clock_in_at=day.clock_in_at,
            old_status="open",
            new_clock_in_at=day.clock_in_at,
            new_status="open",
            reason="x",
            created_by_name="Marta Jefa",
        )

    run_forward()

    with use_hub(hub_a):
        correction.refresh_from_db()
    assert (correction.is_system, correction.created_by_name) == (False, "Marta Jefa")


def test_coordinates_of_the_shared_device_are_dropped_and_the_rest_stays(hub_a):
    with use_hub(hub_a):
        shared = _day(in_lat=40.4, in_lng=-3.7, in_accuracy_m=9.0, in_distance_m=12.0, in_within_radius=True)
        personal = _day(source="personal", in_lat=40.4, in_lng=-3.7, in_distance_m=12.0, in_within_radius=True)

    run_forward()

    with use_hub(hub_a):
        shared.refresh_from_db()
        personal.refresh_from_db()
    assert (shared.in_lat, shared.in_lng, shared.out_lat, shared.out_lng) == (None, None, None, None)
    assert (shared.in_accuracy_m, shared.in_distance_m, shared.in_within_radius) == (9.0, 12.0, True)
    assert (personal.in_lat, personal.in_lng) == (40.4, -3.7)


def test_it_reverses():
    MIGRATION.backwards(*_on_business_a())
    operations = [op for op in MIGRATION.Migration.operations if op.__class__.__name__ == "RunPython"]
    assert operations and all(op.reversible for op in operations)
