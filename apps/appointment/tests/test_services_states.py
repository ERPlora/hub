"""The states of an appointment (APPOINTMENT-F03, APPOINTMENT-F05, APPOINTMENT-F07, APPOINTMENT-F08,
APPOINTMENT-F09): confirming, starting, completing, a no-show and cancelling.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.appointment.models.appointments import History

from .conftest import HUB_DB, MONDAY, at, make_appointment, make_customer, make_settings, run
from .write_checks import actions, book, events, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_the_state_machine(salon):
    pending = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status="pending"
    )
    assert (
        run("appointment.appointment.confirm", {"id": str(pending.id)}).status
        == "confirmed"
    )
    refused(
        "appointment.cannot_confirm",
        lambda: run("appointment.appointment.confirm", {"id": str(pending.id)}),
    )
    other = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status="pending"
    )
    refused(
        "appointment.cannot_complete",
        lambda: run("appointment.appointment.complete", {"id": str(other.id)}),
    )
    assert (
        run("appointment.appointment.start", {"id": str(pending.id)}).status
        == "in_progress"
    )
    refused(
        "appointment.cannot_start",
        lambda: run("appointment.appointment.start", {"id": str(pending.id)}),
    )
    assert (
        run("appointment.appointment.complete", {"id": str(pending.id)}).status
        == "completed"
    )
    assert actions(pending.id) == ["confirmed", "started", "completed"]
    assert [
        len(events(f"appointment.appointment.{e}"))
        for e in ("confirmed", "started", "completed")
    ] == [1, 1, 1]
    # A pending one may be started at once (the customer is sitting there).
    walk_in = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), status="pending"
    )
    assert (
        run("appointment.appointment.start", {"id": str(walk_in.id)}).status
        == "in_progress"
    )


def test_a_no_show_is_marked_only_once_its_time_has_passed(salon):
    future = book(salon)
    refused(
        "appointment.no_show_too_early",
        lambda: run("appointment.appointment.mark_no_show", {"id": str(future.id)}),
    )
    past = make_appointment(
        salon.lucia, salon.ana, [salon.cut], timezone.now() - dt.timedelta(hours=1)
    )
    assert (
        run("appointment.appointment.mark_no_show", {"id": str(past.id)}).status
        == "no_show"
    )
    assert (
        actions(past.id) == ["no_show"]
        and len(events("appointment.appointment.marked_no_show")) == 1
    )
    refused(
        "appointment.cannot_mark_no_show",
        lambda: run("appointment.appointment.mark_no_show", {"id": str(past.id)}),
    )


def test_cancelling_keeps_the_reason_and_frees_the_time(salon):
    make_settings(allow_overlapping=False)
    out = book(salon)
    cancelled = run(
        "appointment.appointment.cancel", {"id": str(out.id), "reason": "Ill"}
    )
    assert (
        cancelled.status,
        cancelled.cancellation_reason,
        cancelled.cancelled_by_customer,
    ) == ("cancelled", "Ill", False)
    assert cancelled.cancelled_at is not None
    assert (
        History.objects.get(appointment_id=out.id, action="cancelled").reason == "Ill"
    )
    assert book(salon).status == "confirmed"  # the time is free again
    refused(
        "appointment.cannot_cancel",
        lambda: run("appointment.appointment.cancel", {"id": str(out.id)}),
    )
    for status in ("in_progress", "completed"):
        item = make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), status=status
        )
        refused(
            "appointment.cannot_cancel",
            lambda item=item: run("appointment.appointment.cancel", {"id": str(item.id)}),
        )
    charged = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), sale_id=uuid.uuid7()
    )
    refused(
        "appointment.cannot_cancel",
        lambda: run("appointment.appointment.cancel", {"id": str(charged.id)}),
    )


def test_the_customer_cancels_within_the_policy(salon):
    out = book(salon)
    mine = {
        "id": str(out.id),
        "on_behalf_of_customer": True,
        "customer_id": str(salon.lucia.id),
        "reason": "Ill",
    }
    make_settings(allow_customer_cancellation=False)
    refused(
        "appointment.customer_cancellation_disabled",
        lambda: run("appointment.appointment.cancel", mine),
    )
    make_settings(cancellation_notice_hours=24 * 60)
    refused(
        "appointment.cancellation_notice_required",
        lambda: run("appointment.appointment.cancel", mine),
    )
    make_settings()
    other = make_customer("Pepa Gil", phone="+34600222333")
    refused(
        "appointment.appointment_not_found",
        lambda: run(
            "appointment.appointment.cancel", {**mine, "customer_id": str(other.id)}
        ),
        NotFound,
    )
    assert run("appointment.appointment.cancel", mine).cancelled_by_customer is True
    assert (
        History.objects.get(appointment_id=out.id, action="cancelled").by_customer
        is True
    )
