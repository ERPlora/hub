"""Deleting appointments, one or several at once (APPOINTMENT-F11)."""

import uuid

import pytest
from live.errors import PermissionDenied

from apps.appointment.models.appointments import Appointment

from .conftest import HUB_DB, MONDAY, at, make_appointment, run
from .write_checks import book, events, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_deleting_archives_and_refuses_what_happened_or_was_charged(salon):
    out = book(salon)
    assert run("appointment.appointment.delete", {"id": str(out.id)}).id == out.id
    assert Appointment.objects.get(pk=out.id).deleted_at is not None
    assert run("appointment.appointment.list", {"date_from": MONDAY}).total == 0
    assert len(events("appointment.appointment.deleted")) == 1
    for fields in (
        {"status": "completed"},
        {"status": "in_progress"},
        {"sale_id": uuid.uuid7()},
    ):
        item = make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), **fields
        )
        refused(
            "appointment.cannot_delete",
            lambda item=item: run("appointment.appointment.delete", {"id": str(item.id)}),
        )


def test_a_bulk_delete_deletes_all_or_none(salon):
    one, two = book(salon, "10:00"), book(salon, "11:00")
    done = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), status="completed"
    )
    refused(
        "appointment.cannot_delete",
        lambda: run(
            "appointment.appointment.bulk_delete", {"ids": [str(one.id), str(done.id)]}
        ),
    )
    out = run(
        "appointment.appointment.bulk_delete", {"ids": [str(one.id), str(two.id)]}
    )
    assert set(out.deleted) == {one.id, two.id}


def test_a_manager_does_not_delete():
    with pytest.raises(PermissionDenied):
        run(
            "appointment.appointment.delete",
            {"id": str(uuid.uuid7())},
            role="hub_manager",
        )
