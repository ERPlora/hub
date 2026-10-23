"""APPOINTMENT-F28: what the device is told of Citas, as ``base.notice.list`` fills in the app's declaration.

The customer's own bookings and cancellations (WhatsApp, the online booking), never the front desk's, of the agenda
the person sees, the newest first, in the person's language; a tap opens the agenda on the appointment's day. The
shell tells each row once on the device (``packages/ui``, ``device-notices.ts``).
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.operations import get

from base.schemas import NoticeListIn

from .conftest import MONDAY, at, ctx_for, make_appointment, make_customer
from .test_queries import TUESDAY, employee_linked_to

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def citas_on(monkeypatch):
    """Citas on in the hub of the tests (the photo of the SaaS says which apps are on)."""
    monkeypatch.setattr(
        "base.queries.active_apps", lambda scope: frozenset({"base", "appointment", "customer", "service", "staff", "schedule"})
    )


def notices(ctx):
    op = get("base.notice.list")
    return op(ctx, NoticeListIn()).model_dump(mode="json")["notices"]


def test_the_device_is_told_the_customers_own_bookings_and_cancellations_never_the_front_desks(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp")
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"))
    cancelled = make_appointment(
        make_customer("Pepa Gil"),
        salon.bea,
        [salon.colour],
        at(TUESDAY, "16:00"),
        source="online",
        status="cancelled",
        cancelled_by_customer=True,
        cancelled_at=timezone.now() + dt.timedelta(seconds=1),
    )

    told = notices(ctx_for("hub_admin"))

    assert [(n["key"], n["id"]) for n in told] == [
        ("appointment.cancelled", str(cancelled.id)),
        ("appointment.booked", str(cancelled.id)),
        ("appointment.booked", str(booked.id)),
    ]
    first = told[0]
    assert first["title"] == "Appointment cancelled · Pepa Gil"
    assert first["body"].split(" · ")[0] == "Colour"
    assert first["body"].split(" · ")[-1] == "Bea Ruiz"
    assert first["body"].split(" · ")[1].endswith(" at 16:00")
    assert first["route"] == f"/appointment/agenda?date={TUESDAY.isoformat()}"
    assert told[2]["title"] == f"New appointment · {salon.lucia.name}"
    assert told[2]["route"] == f"/appointment/agenda?date={MONDAY.isoformat()}"
    assert all(n["at"] for n in told)


def test_in_spanish_the_old_shells_words(salon):
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp")

    [told] = notices(ctx_for("hub_admin", language="es"))

    assert told["title"] == f"Nueva cita · {salon.lucia.name}"
    assert told["body"].split(" · ")[1].endswith(" a las 10:00")


def test_an_employee_is_told_only_of_her_own_agenda(salon, make_user):
    mine = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp")
    make_appointment(salon.lucia, salon.bea, [salon.colour], at(MONDAY, "12:00"), source="online")

    told = notices(employee_linked_to(salon.ana, make_user))

    assert [n["id"] for n in told] == [str(mine.id)]


def test_an_erased_customer_is_still_told_without_her_name(salon):
    from apps.appointment.models import Appointment

    erased = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp")
    Appointment.objects.filter(pk=erased.pk).update(customer_name="")

    [told] = notices(ctx_for("hub_admin"))

    assert told["title"] == "New appointment"


def test_an_appointment_without_a_professional_is_told_without_one(salon):
    make_appointment(salon.lucia, None, [salon.cut], at(MONDAY, "10:00"), source="whatsapp")

    [told] = notices(ctx_for("hub_admin"))

    assert told["body"].split(" · ")[0] == salon.cut.name
    assert len(told["body"].split(" · ")) == 2


def test_whoever_sees_an_agenda_hears_citas_and_nobody_else(salon):
    op = get("base.notice.list")
    assert op(ctx_for("hub_employee"), NoticeListIn()).sources == ["appointment.booked", "appointment.cancelled"]
    assert op(ctx_for("hub_employee", permissions={"base.view_home"}), NoticeListIn()).sources == []
