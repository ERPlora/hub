"""The agenda hears the other apps through the worker's outbox relay, end to end (APPOINTMENT-F17, F23, F24,
F25): the real Sales, Customers and Staff operations write their events, one tick of the worker's real loop
hands them to Citas (``base.relay``), and the appointment is charged, moved to the kept card, emptied or
unassigned — once, a second tick changing nothing.
"""

import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent

from apps.appointment.models import Appointment, Recurring
from apps.sale.models import Order
from apps.tax.models import TaxCategory
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import MONDAY, make_customer, make_member, make_service, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


@pytest.fixture
def tick(monkeypatch):
    """One tick of the worker's real loop, without the SaaS (``register_apps``) and, inside the test's
    transaction, without releasing the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def once() -> None:
        stop = threading.Event()

        def wait(_seconds: float) -> bool:
            stop.set()
            return True

        now = timezone.now()
        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0

    return once


def delivered_to_appointment(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Citas."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    delivery = EventDelivery.objects.get(event_id=event.id, app_label="appointment")
    return delivery.status, delivery.attempts


def book(customer: str = "Lucía Pérez", staff: str = "Ana", start: str = "10:00"):
    return run(
        "appointment.appointment.create",
        {"customer": customer, "services": [{"service": "Haircut"}], "staff": staff, "start": wall(MONDAY, start)},
    )


def test_a_check_charged_at_the_till_marks_the_appointment_and_a_void_frees_it(tick):
    # APPOINTMENT-F17: «Charge» opens the check; the till charges it; the relay brings the sale back.
    make_service("Haircut", price=2000, duration=30, tax=TaxCategory.objects.get(key="service.generic"))
    make_customer("Lucía Pérez")
    make_member("Ana", "López")
    booked = book()
    opened = run("appointment.appointment.charge", {"id": str(booked.id)})
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "appointment-relay-0001", "order_id": str(opened.order_id), "payments": [{"method": "card"}]},
    )
    assert Appointment.objects.get(pk=booked.id).sale_id is None
    tick()
    assert delivered_to_appointment("sale.sale.created_from_appointment") == ("delivered", 1)
    charged = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (charged.sale_id, charged.status) == (sale.id, "completed")
    tick()
    assert OutboxEvent.objects.filter(name="appointment.appointment.charged").count() == 1

    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong customer"})
    tick()
    assert delivered_to_appointment("sale.sale.voided") == ("delivered", 1)
    assert Appointment.objects.get(pk=booked.id).sale_id is None


def test_a_check_voided_at_the_till_lets_charge_open_a_new_one(tick):
    # APPOINTMENT-F17: the check voided before it was charged lets go of the appointment.
    make_service("Haircut", price=2000, duration=30, tax=TaxCategory.objects.get(key="service.generic"))
    make_customer("Lucía Pérez")
    make_member("Ana", "López")
    booked = book()
    opened = run("appointment.appointment.charge", {"id": str(booked.id)})
    run("sale.order.void", {"order_id": str(opened.order_id)})
    tick()
    assert delivered_to_appointment("sale.order.voided") == ("delivered", 1)
    assert Appointment.objects.get(pk=booked.id).order_id is None
    again = run("appointment.appointment.charge", {"id": str(booked.id)})
    assert again.order_id != opened.order_id
    assert Order.objects.filter(appointment_id=booked.id).count() == 2


def test_merging_two_cards_moves_her_appointments_and_series_to_the_one_kept(tick):
    # APPOINTMENT-F23.
    make_service("Haircut", duration=30)
    make_member("Ana", "López")
    keep = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"})
    twin = run("customer.customer.create", {"name": "Lucia P.", "phone": "600999888"})
    booked = book("600999888")
    series = run(
        "appointment.recurring.create",
        {
            "customer": "600999888",
            "services": [{"service": "Haircut"}],
            "staff": "Ana",
            "frequency": "weekly",
            "start_date": MONDAY,
            "time": "16:00",
            "max_occurrences": 1,
        },
    )
    run("customer.customer.merge", {"id": str(keep.id), "absorbed_id": str(twin.id)})
    tick()
    assert delivered_to_appointment("customer.customer.merged") == ("delivered", 1)
    assert Appointment.objects.get(pk=booked.id).customer_id == keep.id
    assert Recurring.objects.get(pk=series.recurring.id).customer_id == keep.id
    # The name kept in the appointment is the one it was booked with.
    assert Appointment.objects.get(pk=booked.id).customer_name == "Lucia P."


def test_erasing_a_card_empties_her_appointments_but_keeps_them(tick):
    # APPOINTMENT-F24.
    make_service("Haircut", duration=30)
    make_member("Ana", "López")
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222", "email": "lucia@example.com"})
    booked = book("600111222")
    run("customer.customer.erase", {"id": str(card.id)})
    tick()
    assert delivered_to_appointment("customer.customer.erased") == ("delivered", 1)
    item = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (item.customer_name, item.customer_phone, item.customer_email) == ("", "", "")
    assert (item.number, item.status, item.staff_id) == (booked.number, booked.status, booked.staff_id)


def test_a_professional_who_leaves_has_her_upcoming_appointments_unassigned_and_her_series_paused(tick):
    # APPOINTMENT-F25.
    make_service("Haircut", duration=30)
    make_customer("Lucía Pérez")
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    booked = book(staff="Ana López")
    series = run(
        "appointment.recurring.create",
        {
            "customer": "Lucía Pérez",
            "services": [{"service": "Haircut"}],
            "staff": "Ana López",
            "frequency": "weekly",
            "start_date": MONDAY,
            "time": "16:00",
            "max_occurrences": 1,
        },
    )
    run("staff.member.terminate", {"id": str(ana.id)})
    tick()
    assert delivered_to_appointment("staff.member.terminated") == ("delivered", 1)
    item = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (item.staff_id, item.staff_name) == (None, "Ana López")
    assert Recurring.objects.get(pk=series.recurring.id).is_active is False
