"""Appointments with the real Sales app: «Charge» opens a check in the till through ``sale.order.open``
(the caller's session, Sales' rules) with a service line per service (SALE-F38), so a customer's voucher
can pay one (SALE-F27); the till charges it, and the sale's events come back to the agenda
(``sale.sale.created_from_appointment``, ``sale.sale.voided``) as the relay will hand them.
"""

import datetime as dt
import uuid

import pytest
from live.errors import Conflict, NotFound
from live.models import OutboxEvent
from live.operations import get

from django.utils import timezone

from apps.appointment import events
from apps.appointment.models import Appointment
from apps.sale.models import Order
from apps.tax.models import TaxCategory

from .conftest import A, MONDAY, ctx_for, make_customer, make_member, make_service, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


@pytest.fixture
def booked(db):
    generic = TaxCategory.objects.get(key="service.generic")
    make_service("Haircut", price=2000, duration=30, tax=generic)
    make_service("Colour", price=4500, duration=60, tax=generic)
    make_customer("Lucía Pérez")
    make_member("Ana", "López")
    return run(
        "appointment.appointment.create",
        {
            "customer": "Lucía Pérez",
            "services": [{"service": "Haircut"}, {"service": "Colour"}],
            "staff": "Ana",
            "start": wall(MONDAY, "10:00"),
        },
    )


def relay(name: str):
    event = OutboxEvent.objects.filter(name=name).latest("id")
    return events.react(A, event.name, event.payload)


def test_charging_opens_a_check_with_a_service_line_per_service_and_the_sale_comes_back(booked):
    opened = run("appointment.appointment.charge", {"number": booked.number})
    order = Order.objects.get(pk=opened.order_id)
    assert (order.appointment_id, order.label) == (booked.id, f"Lucía Pérez · {booked.number}")
    lines = list(order.lines.order_by("position", "id"))
    services = {line.service_id for line in Appointment.objects.get(pk=booked.id).lines.all()}
    assert [(line.name, line.unit_price, line.tax_category_key, line.staff_id, line.is_service) for line in lines] == [
        ("Haircut", 2000, "service.generic", booked.staff_id, True),
        ("Colour", 4500, "service.generic", booked.staff_id, True),
    ]
    assert {line.service_id for line in lines} == services
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "appointment-test-0001", "order_id": str(order.id), "payments": [{"method": "card"}]},
    )
    assert sale.total == 6500
    assert relay("sale.sale.created_from_appointment").changed == 1
    charged = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (charged.sale_id, charged.status) == (sale.id, "completed")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong customer"})
    assert relay("sale.sale.voided").changed == 1
    assert Appointment.objects.get(pk=booked.id).sale_id is None


def test_a_voucher_of_the_customer_pays_a_service_of_the_check_opened_from_the_agenda(booked):
    haircut = Appointment.objects.get(pk=booked.id).lines.get(name="Haircut").service
    package = run(
        "service.package.create",
        {"name": "Five haircuts", "max_uses": 5, "items": [{"service_id": str(haircut.id)}]},
    )
    grant = run("service.grant.create", {"package_id": str(package.id), "customer_id": str(booked.customer_id)})
    order = Order.objects.get(pk=run("appointment.appointment.charge", {"id": str(booked.id)}).order_id)
    line = order.lines.get(service_id=haircut.id)
    run("sale.order.apply_voucher", {"order_id": str(order.id), "line_id": str(line.id), "grant_id": str(grant.id)})
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "appointment-test-0002",
            "order_id": str(order.id),
            "customer_id": str(booked.customer_id),
            "payments": [{"method": "card"}],
        },
    )
    assert sale.total == 4500
    assert relay("sale.sale.created_from_appointment").changed == 1
    assert Appointment.objects.get(pk=booked.id).status == "completed"


def test_a_service_without_a_fixed_price_is_charged_at_the_price_booked(db):
    generic = TaxCategory.objects.get(key="service.generic")
    make_service("Highlights", price=6000, duration=90, tax=generic, pricing_type="from", min_price=5000, max_price=9000)
    make_customer("Marta Ruiz")
    make_member("Ana", "López")
    booked = run(
        "appointment.appointment.create",
        {"customer": "Marta Ruiz", "services": [{"service": "Highlights"}], "staff": "Ana", "start": wall(MONDAY, "10:00")},
    )
    order = Order.objects.get(pk=run("appointment.appointment.charge", {"id": str(booked.id)}).order_id)
    [line] = order.lines.all()
    assert (line.name, line.unit_price, line.is_service) == ("Highlights", 6000, True)


def test_the_check_charges_what_was_booked_the_professionals_own_price_and_an_old_price_included(db):
    from apps.service.models import Service

    from .conftest import assign

    generic = TaxCategory.objects.get(key="service.generic")
    cut = make_service("Haircut", price=2000, duration=30, tax=generic)
    colour = make_service("Colour", price=4500, duration=60, tax=generic)
    make_customer("Lucía Pérez")
    ana = make_member("Ana", "López")
    assign(cut, ana, price=3000)
    assign(colour, ana)
    booked = run(
        "appointment.appointment.create",
        {"customer": "Lucía Pérez", "services": [{"service": "Haircut"}, {"service": "Colour"}], "staff": "Ana", "start": wall(MONDAY, "10:00")},
    )
    # The catalog changes after booking: the check keeps what the appointment booked.
    Service.objects.filter(pk=colour.pk).update(price=5000)
    order = Order.objects.get(pk=run("appointment.appointment.charge", {"id": str(booked.id)}).order_id)
    assert [(line.name, line.unit_price) for line in order.lines.order_by("position", "id")] == [
        ("Haircut", 3000),
        ("Colour", 4500),
    ]


def test_an_employee_charges_her_own_appointment_without_the_open_price_right(booked, make_user):
    from apps.staff.models import Member

    user = make_user("ana", role="hub_employee")
    Member.objects.filter(pk=booked.staff_id).update(user=user)
    employee = ctx_for("hub_employee", actor=user)
    assert "sale.sell_open_price" not in employee.permissions
    charge = get("appointment.appointment.charge")
    opened = charge(employee, charge.input.model_validate({"id": str(booked.id)}))
    assert Order.objects.get(pk=opened.order_id).lines.count() == 2


def test_an_employee_does_not_charge_a_colleagues_appointment_she_cannot_see(booked, make_user):
    user = make_user("bea", role="hub_employee")
    make_member("Bea", "Ruiz", user=user)
    charge = get("appointment.appointment.charge")
    with pytest.raises(NotFound):
        charge(ctx_for("hub_employee", actor=user), charge.input.model_validate({"id": str(booked.id)}))
    assert Order.objects.count() == 0


# ── One check per appointment (F17): charging again goes back to it ───────────────────────────────


def test_charging_twice_goes_back_to_the_same_open_check(booked):
    first = run("appointment.appointment.charge", {"id": str(booked.id)})
    again = run("appointment.appointment.charge", {"number": booked.number})
    assert again.order_id == first.order_id
    assert Order.objects.filter(appointment_id=booked.id).count() == 1
    assert Order.objects.get(pk=first.order_id).lines.count() == 2
    assert run("appointment.appointment.get", {"id": str(booked.id)}).order_id == first.order_id


def test_a_voided_check_lets_the_appointment_open_a_new_one(booked):
    first = run("appointment.appointment.charge", {"id": str(booked.id)})
    run("sale.order.void", {"order_id": str(first.order_id)})
    assert relay("sale.order.voided").changed == 1
    assert run("appointment.appointment.get", {"id": str(booked.id)}).order_id is None
    second = run("appointment.appointment.charge", {"id": str(booked.id)})
    assert second.order_id != first.order_id
    assert Order.objects.filter(appointment_id=booked.id, status="open").count() == 1


def test_a_check_charged_before_the_agenda_hears_it_is_not_opened_again(booked):
    opened = run("appointment.appointment.charge", {"id": str(booked.id)})
    run(
        "sale.sale.complete",
        {"idempotency_key": "appointment-test-0003", "order_id": str(opened.order_id), "payments": [{"method": "card"}]},
    )
    with pytest.raises(Conflict) as refused:
        run("appointment.appointment.charge", {"id": str(booked.id)})
    assert refused.value.code == "appointment.already_charged"
    assert Order.objects.filter(appointment_id=booked.id).count() == 1


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("appointment.appointment.cancel", {}),
        ("appointment.appointment.mark_no_show", {}),
        ("appointment.appointment.delete", {}),
    ],
)
def test_an_appointment_with_an_open_check_is_not_cancelled_marked_no_show_nor_deleted(booked, name, data):
    run("appointment.appointment.charge", {"id": str(booked.id)})
    # Its time has passed: a no-show would be allowed but for the open check.
    an_hour_ago = timezone.now() - dt.timedelta(hours=2)
    Appointment.objects.filter(pk=booked.id).update(start=an_hour_ago, end=an_hour_ago + dt.timedelta(minutes=90))
    with pytest.raises(Conflict) as refused:
        run(name, {"id": str(booked.id), **data})
    assert refused.value.code == "appointment.check_open"
    assert Appointment.objects.get(pk=booked.id).status == "confirmed"


def test_a_voided_sale_frees_the_appointment_for_a_new_check(booked):
    opened = run("appointment.appointment.charge", {"id": str(booked.id)})
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "appointment-test-0004", "order_id": str(opened.order_id), "payments": [{"method": "card"}]},
    )
    relay("sale.sale.created_from_appointment")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong customer"})
    relay("sale.sale.voided")
    after = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (after.sale_id, after.order_id) == (None, None)


def test_a_sale_never_marks_a_cancelled_or_deleted_appointment_nor_replaces_its_sale(booked):
    mark = get("appointment.appointment.mark_charged")
    from live.context import system_context

    def charged(appointment_id, sale_id):
        return mark(system_context(A), mark.input.model_validate({"appointment_id": str(appointment_id), "sale_id": str(sale_id)}))

    first = uuid.uuid7()
    assert charged(booked.id, first).changed == 1
    assert charged(booked.id, first).changed == 0
    with pytest.raises(Conflict) as replaced:
        charged(booked.id, uuid.uuid7())
    assert replaced.value.code == "appointment.already_charged"
    assert Appointment.objects.get(pk=booked.id).sale_id == first

    cancelled = run(
        "appointment.appointment.create",
        {"customer": "Lucía Pérez", "services": [{"service": "Haircut"}], "staff": "Ana", "start": wall(MONDAY, "15:00")},
    )
    run("appointment.appointment.cancel", {"id": str(cancelled.id)})
    with pytest.raises(Conflict) as gone:
        charged(cancelled.id, uuid.uuid7())
    assert gone.value.code == "appointment.cannot_charge"
