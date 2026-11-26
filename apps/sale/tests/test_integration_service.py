"""Sale and Services together, no mocks (SALE-F38; SERVICE-F09, F31): the till sells the services of Services at
their price, a professional's own price or the amount typed within the service's range.
"""

from uuid import uuid7

import pytest
from django.utils import translation
from live.errors import Conflict

from apps.sale.tests.conftest import HUB_DB, charge, check, last_event, run, svc

pytestmark = HUB_DB


# ── Selling a service (SALE-F38, SERVICE-F09) ────────────────────────────────────────────────


def test_the_till_sells_a_service_of_services_at_its_price(haircut):
    order = check(haircut)
    [line] = order.lines
    assert (
        line.service_id,
        line.name,
        line.is_service,
        line.unit_price,
        line.tax_category_key,
    ) == (
        haircut.id,
        "Haircut",
        True,
        2500,
        "service.generic",
    )
    assert line.product_id is None and line.paid_by_voucher is False
    order = run(
        "sale.order.add_service_line",
        {"order_id": str(order.id), "service": "Haircut", "quantity": "2"},
    )
    assert order.provisional_total == 7500
    sale = charge(order, payments=[{"method": "card"}])
    assert (sale.total, [line.service_id for line in sale.lines]) == (
        7500,
        [haircut.id, haircut.id],
    )
    items = last_event("sale.sale.completed")["items"]
    assert {
        (item["service_id"], item["is_service"], item["paid_by_voucher"])
        for item in items
    } == {(str(haircut.id), True, False)}


# ── The professional's own price (SALE-F38, SERVICE-F31): Fresha, Phorest and Timely charge it ──


@pytest.fixture
def ana(db):
    """A professional of Staff, made by Staff."""
    return svc("staff.member.create", {"first_name": "Ana", "last_name": "López"})


def own_price(service, member, price, **more):
    return svc(
        "service.assignment.assign",
        {"service_id": str(service.id), "member_id": str(member.id), "custom_price": price, **more},
    )


def test_a_service_done_by_a_professional_with_her_own_price_is_charged_at_it(haircut, ana):
    own_price(haircut, ana, 3000)
    order = run(
        "sale.order.open",
        {"service_lines": [{"service_id": str(haircut.id), "staff_id": str(ana.id)}]},
    )
    [line] = order.lines
    assert (line.unit_price, line.line_total, line.staff_id) == (3000, 3000, ana.id)
    # Added to a check, and charged loose: the same price.
    order = run(
        "sale.order.add_service_line",
        {"order_id": str(order.id), "service_id": str(haircut.id), "staff_id": str(ana.id)},
    )
    assert [line.unit_price for line in order.lines] == [3000, 3000]
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "svc-own-price-01",
            "service_lines": [{"service_id": str(haircut.id), "staff_id": str(ana.id)}],
            "payments": [{"method": "card"}],
        },
    )
    assert sale.total == 3000


def test_without_her_own_price_or_without_a_professional_the_service_keeps_its_price(haircut, ana):
    bea = svc("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    own_price(haircut, bea, None)
    order = run(
        "sale.order.open",
        {
            "service_lines": [
                {"service_id": str(haircut.id)},
                {"service_id": str(haircut.id), "staff_id": str(ana.id)},
                {"service_id": str(haircut.id), "staff_id": str(bea.id)},
                # Not a professional of Staff at all: an id the till does not know.
                {"service_id": str(haircut.id), "staff_id": str(uuid7())},
            ]
        },
    )
    assert [line.unit_price for line in order.lines] == [2500, 2500, 2500, 2500]


def test_an_assignment_taken_away_takes_its_price_away(haircut, ana):
    assignment = own_price(haircut, ana, 3000)
    svc("service.assignment.remove", {"id": str(assignment.id)})
    order = run(
        "sale.order.open",
        {"service_lines": [{"service_id": str(haircut.id), "staff_id": str(ana.id)}]},
    )
    assert order.lines[0].unit_price == 2500


def test_a_service_without_a_fixed_price_still_takes_the_amount_typed(colour, ana):
    own_price(colour, ana, 7000)
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.open",
            {"service_lines": [{"service_id": str(colour.id), "staff_id": str(ana.id)}]},
        )
    assert refusal.value.code == "sale.service_price_required"


def test_a_counter_sale_charges_services_too(haircut):
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "svc-counter-0001",
            "service_lines": [{"service_id": str(haircut.id)}],
            "payments": [{"method": "cash", "tendered": 3000}],
        },
    )
    assert (sale.total, sale.change_total, sale.lines[0].service_id) == (
        2500,
        500,
        haircut.id,
    )


def test_a_service_without_a_fixed_price_takes_the_amount_typed_within_its_range(
    colour, haircut
):
    order = run("sale.order.open", {})
    add = lambda **more: run(  # noqa: E731
        "sale.order.add_service_line", {"order_id": str(order.id), **more}
    )
    with pytest.raises(Conflict) as refusal:
        add(service_id=str(colour.id))
    assert refusal.value.code == "sale.service_price_required"
    assert "unit_price" in refusal.value.fields
    with pytest.raises(Conflict) as refusal:
        add(service_id=str(colour.id), unit_price=3000)
    assert refusal.value.code == "sale.service_price_out_of_range"
    with pytest.raises(Conflict) as refusal:
        add(service_id=str(haircut.id), unit_price=2000)
    assert refusal.value.code == "sale.service_price_fixed"
    order = add(service_id=str(colour.id), unit_price=7000)
    assert order.lines[0].unit_price == 7000


def test_the_range_of_a_service_is_said_with_its_thousands_grouped(db):
    # «1.000,00 € – 2.500,00 €» in Spanish, never «1000.00 € – 2500.00 €».
    bridal = svc(
        "service.service.create",
        {
            "name": "Bridal",
            "pricing_type": "from",
            "price": 150000,
            "min_price": 100000,
            "max_price": 250000,
            "tax_category_key": "service.generic",
        },
    )
    order = run("sale.order.open", {})
    for language, low, high in (("es", "1.000,00 €", "2.500,00 €"), ("en", "€1,000.00", "€2,500.00")):
        with translation.override(language), pytest.raises(Conflict) as refusal:
            run(
                "sale.order.add_service_line",
                {"order_id": str(order.id), "service_id": str(bridal.id), "unit_price": 300000},
            )
        assert refusal.value.code == "sale.service_price_out_of_range"
        message = refusal.value.message.replace("\u00a0", " ").replace("\u202f", " ")
        assert low in message and high in message


def test_an_archived_or_unconfigured_service_is_not_sold(haircut):
    order = run("sale.order.open", {})
    svc("service.service.archive", {"id": str(haircut.id)})
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.add_service_line",
            {"order_id": str(order.id), "service_id": str(haircut.id)},
        )
    assert refusal.value.code == "sale.service_not_available"
    untaxed = svc(
        "service.service.create",
        {"name": "Massage", "price": 3000, "tax_category_key": "service.generic"},
    )
    # Its tax category gone (deactivated in Taxes, or emptied by support in the admin).
    from apps.service.models.catalog import Service

    Service.objects.filter(pk=untaxed.id).update(tax_category=None)
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.add_service_line",
            {"order_id": str(order.id), "service_id": str(untaxed.id)},
        )
    assert refusal.value.code == "sale.tax_category_missing"
