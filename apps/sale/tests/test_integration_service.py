"""Sale and Services together, no mocks (SALE-F27, F32, F38; SERVICE-F09, F22–F27): the till sells the
services of Services and pays a line of a service with a customer's voucher.

Everything runs through the two apps' real operations: Services' catalog, vouchers and sessions are
made by Services, and Sales reserves, releases, delivers and gives back the sessions by calling
Services' operations inside its own transaction. «Services off» is the app's operations missing from
the registry, as when it is not installed (the same path as ``app_inactive``).
"""

import datetime as dt
from uuid import uuid7

import pytest
from django.utils import timezone, translation
from live.context import system_context
from live.errors import Conflict, PermissionDenied
from live.models import OutboxEvent
from live.operations import get, registry

from apps.sale.models import Order, OrderLine, Refund, Sale, SaleCounter, SaleLine
from apps.sale.tests.conftest import A, ctx_for, run
from apps.service.models import Grant, Redemption

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


def svc(name: str, data: dict):
    """Services' own operation, run as the platform: how the business's catalog and vouchers exist."""
    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


@pytest.fixture
def haircut(db):
    return svc(
        "service.service.create",
        {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
    )


@pytest.fixture
def colour(db):
    return svc(
        "service.service.create",
        {
            "name": "Colour",
            "pricing_type": "from",
            "price": 6500,
            "min_price": 4000,
            "max_price": 9000,
            "tax_category_key": "service.generic",
        },
    )


@pytest.fixture
def lucia(customer):
    return customer("Lucía Pérez")


def voucher(owner, service, *, name="Bono 5 cortes", uses=5, validity=None):
    package = svc(
        "service.package.create",
        {
            "name": name,
            "max_uses": uses,
            "validity_days": validity,
            "items": [{"service_id": str(service.id)}],
        },
    )
    return svc(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": 10000},
    )


def check(*services, ctx=None):
    """An open check with one line per service (fixed price)."""
    return run(
        "sale.order.open",
        {"service_lines": [{"service_id": str(service.id)} for service in services]},
        ctx,
    )


def pay_with(order, line_id, grant, ctx=None):
    return run(
        "sale.order.apply_voucher",
        {"order_id": str(order.id), "line_id": str(line_id), "grant_id": str(grant.id)},
        ctx,
    )


def charge(order, key="svc-charge-0001", ctx=None, **more):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "order_id": str(order.id), **more},
        ctx,
    )


def remaining(grant) -> int | None:
    [row] = svc("service.grant.list", {"package_id": str(grant.package_id)}).rows
    return row.remaining


def session_of(line_id) -> Redemption:
    return Redemption.objects.get(
        order_line_id=line_id, status__in=["held", "consumed", "returned"]
    )


def last_event(name: str) -> dict:
    return (
        OutboxEvent.objects.filter(name=name)
        .order_by("-created_at", "-id")
        .first()
        .payload
    )


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
    # hub#1090: «1.000,00 € – 2.500,00 €» in Spanish, never «1000.00 € – 2500.00 €».
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
    from apps.service.models import Service

    Service.objects.filter(pk=untaxed.id).update(tax_category=None)
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.add_service_line",
            {"order_id": str(order.id), "service_id": str(untaxed.id)},
        )
    assert refusal.value.code == "sale.tax_category_missing"


# ── Paying a line with a voucher (SALE-F27, SERVICE-F22) ─────────────────────────────────────


def test_paying_a_line_with_a_voucher_holds_a_session_and_the_line_goes_to_zero(
    haircut, lucia
):
    grant = voucher(lucia, haircut)
    order = check(haircut, haircut)
    first, second = order.lines
    version = order.version
    order = pay_with(order, first.id, grant, ctx_for(EMPLOYEE))
    covered = order.lines[0]
    assert (
        covered.paid_by_voucher,
        covered.voucher_name,
        covered.voucher_remaining,
        covered.line_total,
    ) == (
        True,
        "Bono 5 cortes",
        4,
        0,
    )
    assert (
        covered.voucher_grant_id == grant.id and covered.voucher_hold_until is not None
    )
    assert (order.provisional_total, order.version) == (2500, version + 1)
    session = session_of(first.id)
    assert (session.status, session.service_id, str(session.id)) == (
        "held",
        haircut.id,
        str(covered.voucher_session_id),
    )
    assert remaining(grant) == 4
    preview = run("sale.checkout.preview", {"order_id": str(order.id)})
    assert preview.total == 2500
    assert [
        (line.paid_by_voucher, line.voucher_name, line.line_total)
        for line in preview.lines
    ] == [
        (True, "Bono 5 cortes", 0),
        (False, "", 2500),
    ]
    assert last_event("sale.order.changed") == {"order_id": str(order.id)}


def test_undoing_the_voucher_releases_the_session_and_the_line_is_charged_again(
    haircut, lucia
):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    line = order.lines[0]
    order = pay_with(order, line.id, grant)
    order = run(
        "sale.order.remove_voucher",
        {"order_id": str(order.id), "line_id": str(line.id)},
        ctx_for(EMPLOYEE),
    )
    assert (
        order.lines[0].paid_by_voucher,
        order.lines[0].line_total,
        order.provisional_total,
    ) == (False, 2500, 2500)
    assert Redemption.objects.get(order_line_id=line.id).status == "released"
    assert remaining(grant) == 5
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.remove_voucher",
            {"order_id": str(order.id), "line_id": str(line.id)},
        )
    assert refusal.value.code == "sale.line_not_covered"


def test_removing_the_line_or_voiding_the_check_releases_its_sessions(haircut, lucia):
    grant = voucher(lucia, haircut)
    order = check(haircut, haircut, haircut)
    one, two, three = (line.id for line in order.lines)
    for line_id in (one, two, three):
        order = pay_with(order, line_id, grant)
    assert remaining(grant) == 2
    run("sale.order.remove_line", {"order_id": str(order.id), "line_id": str(one)})
    assert Redemption.objects.get(order_line_id=one).status == "released"
    run("sale.order.void", {"order_id": str(order.id)})
    assert set(
        Redemption.objects.filter(order_line_id__in=[two, three]).values_list(
            "status", flat=True
        )
    ) == {"released"}
    assert remaining(grant) == 5


def test_voiding_a_line_sent_to_the_kitchen_releases_its_session(haircut, lucia):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    line = order.lines[0]
    pay_with(order, line.id, grant)
    run("sale.order.fire", {"order_id": str(order.id)})
    run(
        "sale.order.void_line",
        {"order_id": str(order.id), "line_id": str(line.id), "reason": "left"},
    )
    assert Redemption.objects.get(order_line_id=line.id).status == "released"


def test_a_line_paid_with_a_voucher_keeps_its_quantity_comp_and_discount(
    haircut, lucia
):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    line = order.lines[0]
    order = pay_with(order, line.id, grant)
    ref = {"order_id": str(order.id), "line_id": str(line.id)}
    for name, change in (
        ("sale.order.update_line", {"quantity": "2"}),
        ("sale.order.update_line", {"is_gift": True, "gift_reason": "birthday"}),
        ("sale.order.set_line_discount", {"discount_percent": "10"}),
    ):
        with pytest.raises(Conflict) as refusal:
            run(name, {**ref, **change})
        assert refusal.value.code == "sale.line_covered_by_voucher", name
    order = run("sale.order.update_line", {**ref, "notes": "short on the sides"})
    assert (
        order.lines[0].notes == "short on the sides" and order.lines[0].paid_by_voucher
    )


def test_only_a_single_unit_service_line_that_is_no_comp_takes_a_voucher(
    haircut, lucia, product
):
    grant = voucher(lucia, haircut)
    product("Shampoo", "SHA", 1200, "product.generic")
    order = run(
        "sale.order.open",
        {
            "lines": [{"product": "SHA"}],
            "service_lines": [{"service_id": str(haircut.id), "quantity": "2"}],
        },
    )
    shampoo, cuts = order.lines
    with pytest.raises(Conflict) as refusal:
        pay_with(order, shampoo.id, grant)
    assert refusal.value.code == "sale.line_not_coverable"
    with pytest.raises(Conflict) as refusal:
        pay_with(order, cuts.id, grant)
    assert refusal.value.code == "sale.voucher_needs_one_unit"
    split = run(
        "sale.order.split_line", {"order_id": str(order.id), "line_id": str(cuts.id)}
    )
    order = pay_with(split.order, cuts.id, grant)
    with pytest.raises(Conflict) as refusal:
        pay_with(order, cuts.id, grant)
    assert refusal.value.code == "sale.line_already_covered"
    [new_line] = split.new_line_ids
    run(
        "sale.order.update_line",
        {"order_id": str(order.id), "line_id": str(new_line), "is_gift": True},
    )
    with pytest.raises(Conflict) as refusal:
        pay_with(order, new_line, grant)
    assert refusal.value.code == "sale.line_not_coverable"
    assert Redemption.objects.filter(status="held").count() == 1


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("spent", "service.grant_no_uses_left"),
        ("expired", "service.grant_expired"),
        ("other_service", "service.grant_does_not_cover_service"),
    ],
)
def test_a_voucher_that_cannot_pay_is_refused_with_its_409_and_the_line_stays(
    haircut, colour, lucia, state, code
):
    service = colour if state == "other_service" else haircut
    grant = voucher(lucia, haircut, uses=1, validity=30)
    if state == "spent":
        svc("service.grant.redeem", {"id": str(grant.id)})
    elif state == "expired":
        Grant.objects.filter(pk=grant.id).update(
            granted_at=timezone.now() - dt.timedelta(days=31)
        )
    order = run("sale.order.open", {})
    order = run(
        "sale.order.add_service_line",
        {
            "order_id": str(order.id),
            "service_id": str(service.id),
            **({"unit_price": 6500} if service == colour else {}),
        },
    )
    with pytest.raises(Conflict) as refusal:
        pay_with(order, order.lines[0].id, grant)
    assert refusal.value.code == code
    assert refusal.value.message
    line = OrderLine.objects.get(pk=order.lines[0].id)
    assert line.voucher_session_id is None and line.line_total > 0


# ── Charging (SERVICE-F24) ──────────────────────────────────────────────────────────────────────


def test_charging_spends_the_session_and_the_sale_shows_the_line_at_zero(
    haircut, lucia, product
):
    grant = voucher(lucia, haircut)
    product("Shampoo", "SHA", 1200, "product.generic")
    order = run(
        "sale.order.open",
        {
            "lines": [{"product": "SHA"}],
            "service_lines": [{"service_id": str(haircut.id)}],
        },
    )
    cut = order.lines[1]
    order = pay_with(order, cut.id, grant)
    sale = charge(
        order,
        customer_id=str(lucia.id),
        payments=[{"method": "card"}],
        ctx=ctx_for(EMPLOYEE),
    )
    assert sale.total == 1200
    [_, line] = sale.lines
    assert (
        line.paid_by_voucher,
        line.voucher_name,
        line.line_total,
        line.service_id,
    ) == (
        True,
        "Bono 5 cortes",
        0,
        haircut.id,
    )
    session = session_of(cut.id)
    assert (session.status, session.sale_id) == ("consumed", sale.id)
    assert remaining(grant) == 4
    assert SaleLine.objects.get(pk=line.id).voucher_session_id == session.id
    items = last_event("sale.sale.completed")["items"]
    assert [item["paid_by_voucher"] for item in items] == [False, True]
    assert OutboxEvent.objects.filter(name="service.session.settled").count() == 1


def test_a_check_paid_whole_with_vouchers_is_charged_at_zero_without_payments(
    haircut, lucia
):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    order = pay_with(order, order.lines[0].id, grant)
    sale = charge(order, customer_id=str(lucia.id))
    assert (sale.total, sale.payments, sale.status) == (0, [], "completed")
    assert session_of(order.lines[0].id).status == "consumed"


def test_a_partial_charge_spends_only_the_sessions_of_the_lines_it_charges(
    haircut, lucia
):
    grant = voucher(lucia, haircut)
    order = check(haircut, haircut)
    first, second = (line.id for line in order.lines)
    pay_with(order, first, grant)
    order = pay_with(order, second, grant)
    charge(order, line_ids=[str(first)], customer_id=str(lucia.id))
    assert (session_of(first).status, session_of(second).status) == ("consumed", "held")
    charge(
        Order.objects.get(pk=order.id), key="svc-charge-0002", customer_id=str(lucia.id)
    )
    assert session_of(second).status == "consumed"


def test_charging_to_another_customer_or_to_nobody_charges_nothing(
    haircut, lucia, customer
):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    order = pay_with(order, order.lines[0].id, grant)
    marta = customer("Marta Ruiz")
    for who in ({"customer_id": str(marta.id)}, {}):
        with pytest.raises(Conflict) as refusal:
            charge(order, **who)
        assert refusal.value.code == "service.hold_customer_mismatch"
        assert "Bono 5 cortes" in refusal.value.message
    assert (
        not Sale.objects.exists()
        and not SaleCounter.objects.filter(last__gt=0).exists()
    )
    assert session_of(order.lines[0].id).status == "held"
    assert Order.objects.get(pk=order.id).status == "open"


def test_a_session_whose_day_passed_refuses_the_charge_until_the_voucher_is_applied_again(
    haircut, lucia
):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    line = order.lines[0]
    order = pay_with(order, line.id, grant)
    Redemption.objects.filter(order_line_id=line.id).update(
        hold_until=timezone.now() - dt.timedelta(minutes=1)
    )
    with pytest.raises(Conflict) as refusal:
        charge(order, customer_id=str(lucia.id))
    assert refusal.value.code == "service.hold_lost"
    order = run(
        "sale.order.remove_voucher",
        {"order_id": str(order.id), "line_id": str(line.id)},
    )
    order = pay_with(order, line.id, grant)
    sale = charge(order, customer_id=str(lucia.id))
    assert sale.total == 0 and remaining(grant) == 4


def test_the_same_charge_twice_spends_the_session_once(haircut, lucia):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    order = pay_with(order, order.lines[0].id, grant)
    first = charge(order, customer_id=str(lucia.id))
    again = charge(order, customer_id=str(lucia.id))
    assert (again.id, again.already) == (first.id, True)
    assert Redemption.objects.filter(status="consumed").count() == 1
    assert remaining(grant) == 4


def test_split_and_merge_carry_the_session_with_its_line(haircut, lucia):
    grant = voucher(lucia, haircut)
    order = check(haircut, haircut)
    first, second = (line.id for line in order.lines)
    pay_with(order, first, grant)
    split = run(
        "sale.order.split", {"order_id": str(order.id), "line_ids": [str(first)]}
    )
    sale = charge(split.new_order, customer_id=str(lucia.id))
    assert sale.total == 0 and session_of(first).status == "consumed"
    other = check(haircut)
    pay_with(other, other.lines[0].id, grant)
    merged = run(
        "sale.order.merge",
        {"from_order_id": str(other.id), "to_order_id": str(order.id)},
    )
    charge(
        merged,
        key="svc-charge-0002",
        customer_id=str(lucia.id),
        payments=[{"method": "card"}],
    )
    assert session_of(other.lines[0].id).status == "consumed"
    assert not Redemption.objects.filter(order_line_id=second).exists()


# ── Voiding and refunding (SALE-F32, SERVICE-F26, F27) ──────────────────────────────────────────


def charged_with_voucher(haircut, lucia, product=None, key="svc-charge-0001"):
    grant = voucher(lucia, haircut)
    lines = {"service_lines": [{"service_id": str(haircut.id)}]}
    if product is not None:
        lines["lines"] = [{"product": "SHA"}]
    order = run("sale.order.open", lines)
    cut = next(line for line in order.lines if line.service_id)
    order = pay_with(order, cut.id, grant)
    payments = [{"method": "card"}] if product is not None else []
    sale = charge(order, key=key, customer_id=str(lucia.id), payments=payments)
    return grant, sale, next(line for line in sale.lines if line.paid_by_voucher)


def test_voiding_the_sale_gives_its_sessions_back(haircut, lucia):
    grant, sale, line = charged_with_voucher(haircut, lucia)
    assert remaining(grant) == 4
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"})
    session = Redemption.objects.get(
        pk=SaleLine.objects.get(pk=line.id).voucher_session_id
    )
    assert (session.status, session.return_reference, session.return_reason) == (
        "returned",
        sale.id,
        "wrong customer",
    )
    assert remaining(grant) == 5


def refund(sale, *, lines=(), allocations=(), key=None, ctx=None):
    return run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "did not come",
            "allocations": list(allocations),
            "lines": [{"line_id": str(line.id)} for line in lines],
            **({"idempotency_key": key} if key else {}),
        },
        ctx,
    )


def test_refunding_the_line_paid_with_a_voucher_gives_its_session_back_without_money(
    haircut, lucia
):
    grant, sale, line = charged_with_voucher(haircut, lucia)
    assert run("sale.sale.get", {"sale_id": str(sale.id)}).sessions_to_return == 1
    done = refund(sale, lines=[line], key="svc-refund-0001")
    assert (done.total, done.fully_refunded) == (0, True)
    session = Redemption.objects.get(
        pk=SaleLine.objects.get(pk=line.id).voucher_session_id
    )
    assert (session.status, session.return_reference) == ("returned", done.refund_id)
    assert remaining(grant) == 5
    detail = run("sale.sale.get", {"sale_id": str(sale.id)})
    assert (detail.status, detail.sessions_to_return) == ("refunded", 0)
    # The same attempt again gives nothing back twice.
    again = refund(sale, lines=[line], key="svc-refund-0001")
    assert again.already is True and remaining(grant) == 5


def test_a_refund_of_money_and_of_the_voucher_line_together(haircut, lucia, product):
    product("Shampoo", "SHA", 1200, "product.generic")
    grant, sale, line = charged_with_voucher(haircut, lucia, product)
    card = sale.payments[0]
    # All the money back, the session kept: the sale still has its session to give back.
    done = refund(sale, allocations=[{"payment_id": str(card.id), "amount": 1200}])
    assert done.fully_refunded is False
    detail = run("sale.sale.get", {"sale_id": str(sale.id)})
    assert (detail.status, detail.refundable_total, detail.sessions_to_return) == (
        "completed",
        0,
        1,
    )
    listed = run("sale.sale.list", {}).rows[0]
    assert (listed.id, listed.sessions_to_return) == (sale.id, 1)
    done = refund(sale, lines=[line])
    assert done.fully_refunded is True
    assert remaining(grant) == 5


def test_a_refund_that_gives_back_nothing_is_refused(haircut, lucia, product):
    product("Shampoo", "SHA", 1200, "product.generic")
    _grant, sale, _line = charged_with_voucher(haircut, lucia, product)
    shampoo = next(line for line in sale.lines if not line.paid_by_voucher)
    for lines in ((), (shampoo,)):
        with pytest.raises(Conflict) as refusal:
            refund(sale, lines=lines)
        assert refusal.value.code == "sale.refund_nothing"
    assert not Refund.objects.exists()


def test_a_session_given_back_once_is_not_given_back_again(haircut, lucia):
    _grant, sale, line = charged_with_voucher(haircut, lucia)
    refund(sale, lines=[line])
    with pytest.raises(Conflict) as refusal:
        refund(sale, lines=[line])
    assert refusal.value.code in (
        "sale.refund_requires_completed",
        "sale.refund_line_already_returned",
    )


def test_giving_sessions_back_needs_the_managers_permission_of_services(haircut, lucia):
    _grant, sale, line = charged_with_voucher(haircut, lucia)
    ctx = ctx_for("hub_manager")
    ctx = type(ctx)(
        scope=ctx.scope,
        actor=ctx.actor,
        permissions=ctx.permissions - {"service.return_session"},
    )
    with pytest.raises(PermissionDenied):
        refund(sale, lines=[line], ctx=ctx)
    assert not Refund.objects.exists()


# ── Services off (UnknownOperation, as when the app is not installed; app_inactive takes the same path) ──


@pytest.fixture
def services_off(monkeypatch):
    def turn_off():
        for name in [name for name in registry if name.startswith("service.")]:
            monkeypatch.delitem(registry, name)

    return turn_off


def test_without_services_the_till_sells_no_service_and_pays_with_no_voucher(
    haircut, lucia, services_off
):
    grant = voucher(lucia, haircut)
    order = check(haircut, haircut)
    first, second = (line.id for line in order.lines)
    order = pay_with(order, first, grant)
    services_off()
    for name, data in (
        (
            "sale.order.add_service_line",
            {"order_id": str(order.id), "service_id": str(haircut.id)},
        ),
        (
            "sale.order.apply_voucher",
            {
                "order_id": str(order.id),
                "line_id": str(second),
                "grant_id": str(grant.id),
            },
        ),
        (
            "sale.sale.complete",
            {
                "idempotency_key": "svc-off-00001",
                "order_id": str(order.id),
                "customer_id": str(lucia.id),
            },
        ),
    ):
        with pytest.raises(Conflict) as refusal:
            run(name, data)
        assert refusal.value.code == "sale.services_unavailable", name
    # Taking the line off still works: its session comes back alone at its deadline (SERVICE-F25).
    order = run(
        "sale.order.remove_line", {"order_id": str(order.id), "line_id": str(first)}
    )
    assert [line.id for line in order.lines] == [second]
    assert Redemption.objects.get(order_line_id=first).status == "held"


def test_without_services_a_sale_with_sessions_is_not_voided(
    haircut, lucia, services_off
):
    _grant, sale, _line = charged_with_voucher(haircut, lucia)
    services_off()
    with pytest.raises(Conflict) as refusal:
        run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong"})
    assert refusal.value.code == "sale.services_unavailable"
    assert Sale.objects.get(pk=sale.id).status == "completed"


def test_a_voucher_applied_after_a_ticket_discount_never_lifts_the_discount_over_the_cap(haircut, lucia):
    # The cap weighs what is left to pay: a line the voucher pays is worth nothing.
    run("sale.settings.update", {"max_discount_percent": 10}, system_context(A))
    grant = voucher(lucia, haircut)
    order = check(haircut, haircut)
    run(
        "sale.order.set_discount",
        {"order_id": str(order.id), "discount_percent": "0", "discount_amount": 400},
        ctx_for(EMPLOYEE),
    )
    order = pay_with(order, order.lines[0].id, grant, ctx_for(EMPLOYEE))
    with pytest.raises(Conflict) as refusal:
        charge(order, customer_id=str(lucia.id), ctx=ctx_for(EMPLOYEE))
    assert refusal.value.code == "sale.discount_over_limit"
    assert not Sale.objects.exists()


def test_a_voucher_never_leaves_a_fixed_ticket_discount_bigger_than_what_is_left_to_pay(haircut, lucia):
    grant = voucher(lucia, haircut)
    order = check(haircut)
    run("sale.order.set_discount", {"order_id": str(order.id), "discount_percent": "0", "discount_amount": 500})
    with pytest.raises(Conflict) as refusal:
        pay_with(order, order.lines[0].id, grant)
    assert refusal.value.code == "sale.discount_out_of_range"
    assert not Redemption.objects.exists()
    assert OrderLine.objects.get(pk=order.lines[0].id).voucher_session_id is None


def test_a_line_paid_with_a_voucher_goes_back_whole_its_session_is_never_split(haircut, lucia):
    _grant, sale, line = charged_with_voucher(haircut, lucia)
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.sale.refund",
            {
                "sale_id": str(sale.id),
                "reason": "half a haircut",
                "allocations": [],
                "lines": [{"line_id": str(line.id), "quantity": "0.5"}],
            },
        )
    assert refusal.value.code == "sale.refund_voucher_line_whole"
    assert not Refund.objects.exists()
    assert Redemption.objects.get(pk=SaleLine.objects.get(pk=line.id).voucher_session_id).status == "consumed"
