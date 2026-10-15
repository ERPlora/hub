"""Sale and Appointments together, no mocks (SALE-F26, F38; APPOINTMENT-F17): a check opened from the
agenda is charged at the price the appointment was booked at — the professional's own price included —
and never twice.

``booked_price`` freezes a service line at what the appointment booked. Sales checks it by name against
Appointments (``appointment.appointment.get``, with the seller's session): the appointment exists, is not
cancelled nor a no-show nor charged, is the check's customer's, and booked that service at that price (a
lower one only with the open-price right). Without Appointments it is an open price: only with
``sale.sell_open_price``.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict, PermissionDenied
from live.operations import registry

from apps.sale.models import Order
from apps.sale.tests.conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


def as_platform(name: str, data: dict):
    return run(name, data, system_context(A))


@pytest.fixture(autouse=True)
def anytime(db):
    """No rule of hours at all: the business never refuses an appointment on hours."""
    from apps.schedule.models import ScheduleSettings, WeekDay

    WeekDay.objects.all().delete()
    ScheduleSettings.objects.all().delete()


@pytest.fixture
def salon(db, customer):
    """A 20 € haircut that Ana does at her own 90 €, and Lucía's card."""
    haircut = as_platform(
        "service.service.create",
        {"name": "Haircut", "price": 2000, "tax_category_key": "service.generic"},
    )
    ana = as_platform("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    as_platform(
        "service.assignment.assign",
        {"service_id": str(haircut.id), "member_id": str(ana.id), "custom_price": 9000},
    )
    lucia = customer("Lucía Pérez")
    return haircut, ana, lucia


def book(salon, days: int = 7):
    haircut, ana, lucia = salon
    start = timezone.localtime() + dt.timedelta(days=days)
    return as_platform(
        "appointment.appointment.create",
        {
            "customer_id": str(lucia.id),
            "services": [{"service_id": str(haircut.id)}],
            "staff_id": str(ana.id),
            "start": start.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=None).isoformat(),
        },
    )


def open_check(appointment, haircut, ctx=None, **line):
    return run(
        "sale.order.open",
        {
            "appointment_id": str(appointment.id) if appointment else None,
            "service_lines": [{"service_id": str(haircut.id), **line}],
        },
        ctx,
    )


def test_charging_from_the_agenda_charges_the_professionals_own_price(salon):
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    assert appointment.services[0].price == 9000
    opened = run("appointment.appointment.charge", {"id": str(appointment.id)})
    order = Order.objects.get(pk=opened.order_id)
    [line] = order.lines.all()
    assert (line.service_id, line.unit_price) == (haircut.id, 9000)
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "apt-own-0001", "order_id": str(order.id), "payments": [{"method": "card"}]},
    )
    assert sale.total == 9000


def test_the_booked_price_stays_whatever_the_catalog_says_today(salon):
    haircut, ana, _lucia = salon
    appointment = book(salon)
    # After the booking, Ana's own price goes up: the appointment keeps what it booked.
    as_platform(
        "service.assignment.assign",
        {"service_id": str(haircut.id), "member_id": str(ana.id), "custom_price": 9500},
    )
    order = open_check(
        appointment, haircut, ctx_for("hub_manager"), staff_id=str(ana.id), booked_price=9000
    )
    assert order.lines[0].unit_price == 9000


def test_an_appointment_the_seller_cannot_see_has_no_booked_price_for_her(salon):
    # An employee sees her own appointments only (APPOINTMENT «view own»): another's is not hers to charge.
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    refusal = mismatch(appointment, haircut, ctx_for(EMPLOYEE), booked_price=9000)
    # Said as it is: she cannot see it (not «cancelled, another customer's…», which she cannot know).
    assert refusal.message == (
        "You cannot see that appointment: it is another professional's or it no longer exists. Charge it "
        "from the appointment's own professional or at the catalog price."
    )


def mismatch(appointment, haircut, ctx=None, **line):
    with pytest.raises(Conflict) as refusal:
        open_check(appointment, haircut, ctx, **line)
    assert refusal.value.code == "sale.booked_price_mismatch"
    return refusal.value


def test_a_booked_price_above_what_was_booked_is_refused(salon):
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    refusal = mismatch(appointment, haircut, booked_price=9001)
    assert refusal.fields == {"booked_price": refusal.message}
    assert not Order.objects.exists()


def test_a_lower_booked_price_needs_the_open_price_right(salon):
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    mismatch(appointment, haircut, ctx_for(EMPLOYEE), booked_price=5000)
    order = open_check(appointment, haircut, ctx_for("hub_manager"), booked_price=5000)
    assert order.lines[0].unit_price == 5000


def test_a_booked_price_of_a_service_the_appointment_did_not_book_is_refused(salon):
    _haircut, _ana, _lucia = salon
    appointment = book(salon)
    shave = as_platform(
        "service.service.create",
        {"name": "Shave", "price": 9000, "tax_category_key": "service.generic"},
    )
    mismatch(appointment, shave, booked_price=9000)


def test_a_cancelled_or_unknown_appointment_has_no_booked_price(salon):
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    as_platform("appointment.appointment.cancel", {"id": str(appointment.id)})
    mismatch(appointment, haircut, booked_price=9000)
    from uuid import uuid7

    class Nowhere:
        id = uuid7()

    mismatch(Nowhere, haircut, booked_price=9000)


def test_the_booked_price_of_another_customers_appointment_is_refused(salon, customer):
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    other = customer("Marta Ruiz")
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.sale.complete",
            {
                "idempotency_key": "apt-other-0001",
                "appointment_id": str(appointment.id),
                "customer_id": str(other.id),
                "service_lines": [{"service_id": str(haircut.id), "booked_price": 9000}],
                "payments": [{"method": "card"}],
            },
        )
    assert refusal.value.code == "sale.booked_price_mismatch"


def test_without_an_appointment_a_booked_price_is_an_open_price(salon):
    haircut, _ana, _lucia = salon
    with pytest.raises(PermissionDenied):
        open_check(None, haircut, ctx_for(EMPLOYEE), booked_price=1500)
    assert open_check(None, haircut, ctx_for("hub_manager"), booked_price=1500).lines[0].unit_price == 1500


def test_without_appointments_in_the_business_a_booked_price_is_an_open_price(salon, monkeypatch):
    haircut, _ana, _lucia = salon
    appointment = book(salon)
    for name in [name for name in registry if name.startswith("appointment.")]:
        monkeypatch.delitem(registry, name)
    with pytest.raises(PermissionDenied):
        open_check(appointment, haircut, ctx_for(EMPLOYEE), booked_price=9000)
    order = open_check(appointment, haircut, ctx_for("hub_manager"), booked_price=9000)
    assert order.lines[0].unit_price == 9000
