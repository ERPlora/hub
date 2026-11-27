"""Free times take a day and the services or the minutes."""

from pathlib import Path

import pytest

from apps.appointment.schemas.availability import CheckIn, SlotsIn, SlotsOut, WindowOut
from base.tests.typed_operations import ts_fields

from .schema_checks import MONDAY, errors

AVAILABILITY_TS = Path(__file__).resolve().parents[1] / "frontend" / "operations-availability.d.ts"


def test_free_times_take_a_day_and_the_services_or_the_minutes():
    assert not errors(SlotsIn, date=MONDAY, services=["Cut"])
    assert not errors(SlotsIn, date=MONDAY, duration_minutes=45, staff="Ana")
    assert "__all__" in errors(SlotsIn, date=MONDAY)
    assert "__all__" in errors(CheckIn, start=f"{MONDAY}T10:00")


@pytest.mark.parametrize(("interface", "schema"), [("SlotsOut", SlotsOut), ("WindowOut", WindowOut)])
def test_the_typed_free_times_declare_their_schema_fields(interface, schema):
    # The booking panel reads the free times through these TypeScript types: a field the schema answers and the
    # type does not declare is invisible to it.
    assert ts_fields(interface, AVAILABILITY_TS) == set(schema.model_fields)
