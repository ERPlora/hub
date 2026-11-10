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
from live.context import Scope, system_context
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get, registry

from apps.sale.models import Order, OrderLine, Refund, Sale, SaleCounter, SaleLine, VoucherSession
from apps.sale.tests.conftest import A, ctx_for, run
from apps.service.models import Grant, Redemption
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

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


# ── What a session counts for whoever does it (SALE-F28, SERVICE-F24) ────────────────────────


def charged_open(key, *lines, staff=None, ctx=None):
    """A sale charged by card with one open-price line per ``(name, price, professional or None)``: how a voucher is
    charged at the till today (SERVICE-F14)."""
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "open_lines": [
                {
                    "name": name,
                    "unit_price": price,
                    "tax_category_key": "service.generic",
                    **({"staff_id": str(member)} if member else {}),
                }
                for name, price, member in lines
            ],
            "payments": [{"method": "card"}],
            **({"staff_id": str(staff)} if staff else {}),
        },
        ctx,
    )


def grant_for(owner, service, *, name="Bono de 100", uses=3, amount=10000, **more):
    package = svc(
        "service.package.create",
        {"name": name, "max_uses": uses, "items": [{"service_id": str(service.id)}]},
    )
    return svc(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": amount, **more},
    )


def voucher_of_100(owner, service, *, uses=3, name="Bono de 100", seller=None, key="sold-0001"):
    """A voucher of ``uses`` sessions, charged at the till for 100.00 (by ``seller``) and granted saying that sale."""
    sold = charged_open(key, (name, 10000, seller))
    return grant_for(owner, service, name=name, uses=uses, sale_id=str(sold.id))


def spend_session(grant, service, owner, key, *, staff=None, sale_staff=None, ctx=None):
    """One session of ``grant`` pays a check of one line of ``service`` that ``staff`` does, charged."""
    order = run(
        "sale.order.open",
        {
            "service_lines": [
                {"service_id": str(service.id), **({"staff_id": str(staff)} if staff else {})}
            ]
        },
        ctx,
    )
    order = pay_with(order, order.lines[0].id, grant, ctx)
    return charge(
        order,
        key=key,
        customer_id=str(owner.id),
        ctx=ctx,
        **({"staff_id": str(sale_staff)} if sale_staff else {}),
    )


def by_staff(**params):
    return {row.staff_id: row for row in run("sale.sale.by_staff", params).rows}


def test_a_session_counts_for_who_does_it_though_the_line_charged_nothing(haircut, lucia):
    # flow: SALE-F28 (REC_PELUQUERIA-F15): the reproduction of hub#685, gross_total 0 and nothing else to read.
    ana = uuid7()
    sale = spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    assert (sale.total, SaleLine.objects.get(sale=sale.id).voucher_value) == (0, 3333)
    row = by_staff()[ana]
    assert (row.sales_count, row.voucher_total, row.production_total) == (1, 3333, 3333)
    # Her line charged nothing: the money figures stay what they say. The period's revenue is the voucher's own sale.
    assert (row.gross_total, row.net_total, row.tax_total, row.total_revenue) == (0, 0, 0, 0)
    assert run("sale.sale.stats", {}).total_revenue == 10000


def test_the_three_sessions_of_a_voucher_of_100_euros_add_up_to_what_was_paid(haircut, lucia):
    ana, bea = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    spend_session(grant, haircut, lucia, "value-0002", staff=bea)
    spend_session(grant, haircut, lucia, "value-0003", staff=ana)
    rows = by_staff()
    assert (rows[ana].voucher_total, rows[bea].voucher_total) == (3333 + 3333, 3334)
    assert rows[ana].voucher_total + rows[bea].voucher_total == 10000


def test_a_line_that_names_nobody_counts_for_who_serves_the_check(haircut, lucia):
    ana, bea = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", sale_staff=ana)
    spend_session(grant, haircut, lucia, "value-0002", staff=bea, sale_staff=ana)
    rows = by_staff()
    assert (rows[ana].voucher_total, rows[bea].voucher_total) == (3333, 3334)


def test_what_was_charged_is_not_rewritten_when_the_voucher_changes_later(haircut, lucia):
    # flow: SALE-F27: the value is fixed at the charge, like the name of the voucher on the line.
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    svc(
        "service.package.update",
        {"id": str(grant.package_id), "max_uses": 10, "fixed_price": 90000},
    )
    svc("service.grant.adjust", {"id": str(grant.id), "uses_delta": 5, "reason": "courtesy"})
    assert by_staff()[ana].voucher_total == 3333


def test_a_session_keeps_counting_with_services_off(haircut, lucia, services_off):
    ana = uuid7()
    spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    services_off()
    assert by_staff()[ana].production_total == 3333


def test_voiding_the_sale_takes_the_session_off_who_did_it(haircut, lucia):
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut)
    sale = spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"})
    assert ana not in by_staff()
    # Its share went back to the voucher, for the session spent in its place.
    bea = uuid7()
    spend_session(grant, haircut, lucia, "value-0002", staff=bea)
    assert by_staff()[bea].voucher_total == 3333


def test_refunding_the_session_takes_it_off_who_did_it_though_no_money_moved(haircut, lucia):
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut)
    kept = spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    back = spend_session(grant, haircut, lucia, "value-0002", staff=ana)
    done = refund(back, lines=[back.lines[0]], key="value-refund-0001")
    assert done.total == 0
    row = by_staff()[ana]
    assert (row.voucher_total, row.production_total, row.refunded_total) == (3333, 3333, 0)
    assert SaleLine.objects.get(sale=kept.id).voucher_value == 3333
    # The sale that went back stays with its value: a sale is never edited.
    assert SaleLine.objects.get(sale=back.id).voucher_value == 3334


def test_a_professional_whose_only_session_came_back_counts_nothing(haircut, lucia):
    ana = uuid7()
    sale = spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    refund(sale, lines=[sale.lines[0]], key="value-refund-0001")
    row = by_staff()[ana]
    assert (row.sales_count, row.voucher_total, row.production_total) == (1, 0, 0)


def test_a_session_and_money_add_up_in_what_the_commission_goes_on(haircut, colour, lucia):
    # Bea charged more money, Ana made more with the session: the list goes by what each one produced.
    ana, bea = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, uses=1)
    order = run(
        "sale.order.open",
        {
            "service_lines": [
                {"service_id": str(haircut.id), "staff_id": str(ana)},
                {"service_id": str(haircut.id), "staff_id": str(ana)},
                {"service_id": str(haircut.id), "staff_id": str(bea)},
                {"service_id": str(haircut.id), "staff_id": str(bea)},
            ]
        },
    )
    order = pay_with(order, order.lines[0].id, grant)
    charge(order, key="value-0001", customer_id=str(lucia.id), payments=[{"method": "card"}])
    rows = run("sale.sale.by_staff", {}).rows
    assert [
        (row.staff_id, row.gross_total, row.total_revenue, row.voucher_total, row.production_total)
        for row in rows
    ] == [
        (ana, 2500, 2500, 10000, 12500),
        (bea, 5000, 5000, 0, 5000),
    ]
    # With the voucher's own sale, which nobody served, the rows square with the period's revenue.
    assert sum(row.total_revenue for row in rows) + 10000 == run("sale.sale.stats", {}).total_revenue


def test_a_session_of_an_unlimited_voucher_counts_at_the_price_of_its_line(haircut, lucia):
    # There are no sessions to divide by: like a salon's till (Meevo), at the service's own price, frozen on the line.
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut, name="Bono sin límite", uses=None)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    assert by_staff()[ana].voucher_total == 2500


def test_a_line_no_voucher_pays_is_worth_no_session(haircut, lucia):
    ana = uuid7()
    order = run(
        "sale.order.open", {"service_lines": [{"service_id": str(haircut.id), "staff_id": str(ana)}]}
    )
    sale = charge(order, key="value-0001", payments=[{"method": "card"}])
    assert SaleLine.objects.get(sale=sale.id).voucher_value == 0
    row = by_staff()[ana]
    assert (row.voucher_total, row.production_total) == (0, 2500)


def test_the_session_counts_on_the_business_day_of_its_sale(haircut, lucia):
    ana = uuid7()
    sale = spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    day = Sale.objects.get(pk=sale.id).business_day
    assert by_staff(date_from=str(day), date_to=str(day))[ana].voucher_total == 3333
    assert ana not in by_staff(date_from=str(day + dt.timedelta(days=1)))


# ── A session spent outside the till (SERVICE-F21, hub#770): no line carries it ─────────────


def professional(first_name: str, ctx=None):
    """A member of Staff's team: Services only takes a professional who is on it."""
    return run("staff.member.create", {"first_name": first_name, "last_name": "López"}, ctx).id


def voucher_of_100_in(ctx, *, seller=None):
    """In the business of ``ctx``: a haircut of 25.00, Lucía and a voucher of 3 sessions of it, charged at the till for
    100.00 (by ``seller``) and granted saying that sale. Its service, its owner, the voucher sold and the sale."""
    cut = run("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"}, ctx)
    owner = run("customer.customer.create", {"name": "Lucía Pérez"}, ctx)
    package = run(
        "service.package.create", {"name": "Bono de 100", "max_uses": 3, "items": [{"service_id": str(cut.id)}]}, ctx
    )
    sold = charged_open("value-b-0000", ("Bono de 100", 10000, seller), ctx=ctx)
    grant = run(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": 10000, "sale_id": str(sold.id)},
        ctx,
    )
    return cut, owner, grant, sold


def redeem(grant, *, member=None, service=None, ctx=None):
    """One session of ``grant`` spent outside the till (the assistant, the API), saying who did it."""
    return run(
        "service.grant.redeem",
        {
            "id": str(grant.id),
            **({"member_id": str(member)} if member else {}),
            **({"service_id": str(service.id)} if service else {}),
        },
        ctx,
    )


def test_a_session_spent_outside_the_till_counts_for_who_did_it(haircut, lucia):
    # flow: SERVICE-F21, SALE-F28: the reproduction of hub#770, `rows: []` before.
    ana, bea = professional("Ana"), professional("Bea")
    redeem(voucher_of_100(lucia, haircut), member=ana, service=haircut)
    charged_open("money-0001", ("Corte", 2500, bea))
    rows = run("sale.sale.by_staff", {}).rows
    assert [
        (row.staff_id, row.sales_count, row.gross_total, row.total_revenue, row.voucher_total, row.production_total)
        for row in rows
    ] == [(ana, 0, 0, 0, 3333, 3333), (bea, 1, 2500, 2500, 0, 2500)]
    assert VoucherSession.objects.get().session_id == Redemption.objects.get(order_line_id=None).id


def test_a_session_at_the_till_and_one_outside_it_count_once_each(haircut, lucia):
    ana = professional("Ana")
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    redeem(grant, member=ana)
    row = by_staff()[ana]
    assert (row.sales_count, row.voucher_total, row.production_total) == (1, 3333 + 3334, 3333 + 3334)
    # The session of the till is on its line, the other one apart: neither is in both.
    assert VoucherSession.objects.count() == 1


def test_a_session_outside_the_till_that_names_nobody_counts_for_nobody(haircut, lucia):
    grant = voucher_of_100(lucia, haircut)
    redeem(grant)
    assert by_staff() == {}
    ana = professional("Ana")
    redeem(grant, member=ana)
    # The one that named nobody kept its share of the price: Ana's is the second of three.
    assert {staff_id: row.voucher_total for staff_id, row in by_staff().items()} == {ana: 3334}


def test_a_session_outside_the_till_keeps_counting_with_services_off(haircut, lucia, services_off):
    ana = professional("Ana")
    redeem(voucher_of_100(lucia, haircut), member=ana)
    services_off()
    assert by_staff()[ana].production_total == 3333


def test_a_session_outside_the_till_counts_on_the_business_day_it_was_spent(haircut, lucia):
    ana = professional("Ana")
    redeem(voucher_of_100(lucia, haircut), member=ana)
    today = run("sale.business_day.get").today
    assert by_staff(date_from=str(today), date_to=str(today))[ana].voucher_total == 3333
    assert ana not in by_staff(date_from=str(today + dt.timedelta(days=1)))
    assert ana not in by_staff(date_to=str(today - dt.timedelta(days=1)))


def test_a_session_outside_the_till_of_an_unlimited_voucher_counts_at_her_price_of_the_service(haircut, lucia):
    # As the till counts it, at the price of its line: her own price for the service, else the service's. Without the
    # service said there is nothing to price it by.
    ana, bea = professional("Ana"), professional("Bea")
    run("service.assignment.assign", {"service_id": str(haircut.id), "member_id": str(ana), "custom_price": 3000})
    grant = voucher_of_100(lucia, haircut, name="Bono sin límite", uses=None)
    redeem(grant, member=ana, service=haircut)
    redeem(grant, member=bea, service=haircut)
    redeem(grant, member=bea)
    rows = by_staff()
    assert (rows[ana].voucher_total, rows[bea].voucher_total) == (3000, 2500)
    assert Redemption.objects.filter(value=None).count() == 3


def test_a_session_told_twice_counts_once(lucia):
    session, ana = uuid7(), uuid7()
    for _ in range(2):
        run("sale.voucher_session.record", {"session_id": str(session), "staff_id": str(ana), "value": 3333})
    assert by_staff()[ana].voucher_total == 3333
    assert VoucherSession.objects.count() == 1
    # The second telling changed nothing: nothing to repaint.
    assert OutboxEvent.objects.filter(name="sale.voucher_session.recorded").count() == 1


def test_who_may_not_sell_may_not_say_who_did_a_session():
    op = get("sale.voucher_session.record")
    assert op.permission == "sale.add_sale"
    employee = ctx_for(EMPLOYEE)
    no_sell = employee.__class__(**{**employee.__dict__, "permissions": employee.permissions - {"sale.add_sale"}})
    with pytest.raises(PermissionDenied):
        op(no_sell, op.input.model_validate({"session_id": str(uuid7()), "staff_id": str(uuid7()), "value": 1}))
    assert not VoucherSession.objects.exists()


def test_the_employee_who_spends_a_session_says_who_did_it_with_their_own_permissions(haircut, lucia):
    ana = professional("Ana")
    redeem(voucher_of_100(lucia, haircut), member=ana, ctx=ctx_for(EMPLOYEE))
    assert by_staff()[ana].voucher_total == 3333


def test_with_sales_off_the_session_is_spent_and_says_who_did_it_all_the_same(haircut, lucia, monkeypatch):
    ana = professional("Ana")
    grant = voucher_of_100(lucia, haircut)
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)
    out = redeem(grant, member=ana)
    assert (out.remaining, Redemption.objects.get(pk=out.id).member_id) == (2, ana)
    assert not VoucherSession.objects.exists()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_session_outside_the_till_in_one_business_counts_nothing_in_another(hub_a, hub_b):
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_b):
        _cut, _owner, grant, _sold = voucher_of_100_in(in_b)
        ana = professional("Ana", in_b)
        redeem(grant, member=ana, ctx=in_b)
        # Positive control: it counts, in its own business.
        assert {row.staff_id: row.production_total for row in run("sale.sale.by_staff", {}, in_b).rows} == {
            ana: 3333
        }
    with use_hub(hub_a):
        assert run("sale.sale.by_staff", {}, in_a).rows == []
    assert VoucherSession.objects.using(hubs.HUB_B_ALIAS).get().staff_id == ana


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_session_in_one_business_counts_nothing_in_another(hub_a, hub_b):
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    ana, seller = uuid7(), uuid7()
    with use_hub(hub_b):
        cut, owner, grant, sold = voucher_of_100_in(in_b, seller=seller)
        spend_session(grant, cut, owner, "value-b-0001", staff=ana, ctx=in_b)
        # Positive control: they count, in their own business.
        rows = {row.staff_id: row for row in run("sale.sale.by_staff", {}, in_b).rows}
        assert (rows[ana].production_total, rows[seller].production_total) == (3333, 0)
    with use_hub(hub_a):
        assert run("sale.sale.by_staff", {}, in_a).rows == []
    assert Grant.objects.using(hubs.HUB_B_ALIAS).get(pk=grant.id).sale_line_id == sold.lines[0].id


# ── The line that sold a voucher (hub#769, SERVICE-F14) ─────────────────────────────────────


def test_a_voucher_sold_by_one_and_done_by_another_counts_once_and_to_the_cent(haircut, lucia):
    # flow: SERVICE-F14, SALE-F28: A sells it and counts 0; B does its 3 sessions and adds up 100.00. Money stays money.
    seller, doer = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    for key in ("value-0001", "value-0002", "value-0003"):
        spend_session(grant, haircut, lucia, key, staff=doer)
    rows = by_staff()
    assert (
        rows[seller].gross_total,
        rows[seller].total_revenue,
        rows[seller].voucher_sold_total,
        rows[seller].voucher_total,
        rows[seller].production_total,
    ) == (10000, 10000, 10000, 0, 0)
    assert (
        rows[doer].gross_total,
        rows[doer].total_revenue,
        rows[doer].voucher_sold_total,
        rows[doer].voucher_total,
        rows[doer].production_total,
    ) == (0, 0, 0, 10000, 10000)
    assert sum(row.production_total for row in rows.values()) == run("sale.sale.stats", {}).total_revenue == 10000
    assert Grant.objects.get(pk=grant.id).sale_line_id == SaleLine.objects.get(name="Bono de 100").id
    assert last_event("sale.sale.voucher_line_changed")["sale_id"] == str(SaleLine.objects.get(name="Bono de 100").sale_id)


def test_the_list_goes_by_what_each_one_produced_once_the_voucher_is_out(haircut, lucia):
    seller, doer = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    spend_session(grant, haircut, lucia, "value-0001", staff=doer)
    assert [row.staff_id for row in run("sale.sale.by_staff", {}).rows] == [doer, seller]


def test_a_voucher_granted_without_its_sale_counts_nothing_so_nothing_counts_twice(haircut, lucia):
    # flow: SERVICE-F14: its money may be on a line nobody named: that line counts for who sold it, as it did, and the
    # sessions for nobody. The same for a voucher sold before this existed (hub#769).
    seller, doer = uuid7(), uuid7()
    charged_open("sold-0001", ("Bono de 100", 10000, seller))
    grant = grant_for(lucia, haircut)
    sale = spend_session(grant, haircut, lucia, "value-0001", staff=doer)
    rows = by_staff()
    assert (rows[seller].production_total, rows[doer].production_total) == (10000, 0)
    assert SaleLine.objects.get(sale=sale.id).voucher_value == 0
    assert Grant.objects.get(pk=grant.id).sale_line_id is None


def test_a_voucher_given_away_needs_no_line_and_takes_none_out(haircut, lucia):
    seller = uuid7()
    sold = charged_open("sold-0001", ("Corte", 2500, seller), ("Champú", 1200, seller))
    grant = grant_for(lucia, haircut, amount=0, sale_id=str(sold.id))
    assert Grant.objects.get(pk=grant.id).sale_line_id is None
    assert by_staff()[seller].production_total == 3700


def test_a_sale_of_several_lines_says_which_one_paid_the_voucher(haircut, lucia):
    seller = uuid7()
    sold = charged_open("sold-0001", ("Bono de 100", 10000, seller), ("Champú", 1200, seller))
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_line_required"
    # It says the lines to choose from: the name of each is what a person tells them apart by.
    assert "Bono de 100" in str(refusal.value) and "Champú" in str(refusal.value)
    assert not Grant.objects.exists()
    line = next(line for line in sold.lines if line.name == "Bono de 100")
    grant = grant_for(lucia, haircut, name="Otro bono", sale_id=str(sold.id), sale_line_id=str(line.id))
    assert Grant.objects.get(pk=grant.id).sale_line_id == line.id
    # What is left for who sold them is the shampoo.
    assert by_staff()[seller].production_total == 1200


def test_the_line_alone_names_its_sale(haircut, lucia):
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    grant = grant_for(lucia, haircut, sale_line_id=str(sold.lines[0].id))
    assert Grant.objects.get(pk=grant.id).sale_id == sold.id


def test_a_line_of_another_sale_or_a_sale_that_does_not_exist_is_refused(haircut, lucia):
    one = charged_open("sold-0001", ("Bono de 100", 10000, None))
    other = charged_open("sold-0002", ("Bono de 100", 10000, None))
    with pytest.raises(NotFound) as refusal:
        grant_for(lucia, haircut, sale_id=str(one.id), sale_line_id=str(other.lines[0].id))
    assert refusal.value.code == "sale.sale_line_not_found"
    with pytest.raises(NotFound) as refusal:
        grant_for(lucia, haircut, name="Otro", sale_id=str(uuid7()))
    assert refusal.value.code == "sale.sale_not_found"
    with pytest.raises(NotFound) as refusal:
        grant_for(lucia, haircut, name="Otro más", sale_line_id=str(uuid7()))
    assert refusal.value.code == "sale.sale_line_not_found"
    assert not Grant.objects.exists()


def test_a_line_pays_no_more_vouchers_than_it_charged(haircut, lucia):
    # Two vouchers charged on a line of two units fit; a third, or one dearer than the line, does not.
    seller = uuid7()
    order = run(
        "sale.order.open",
        {
            "open_lines": [
                {
                    "name": "Bono x 2",
                    "unit_price": 10000,
                    "quantity": "2",
                    "tax_category_key": "service.generic",
                    "staff_id": str(seller),
                }
            ]
        },
    )
    sold = charge(order, key="sold-0001", payments=[{"method": "card"}])
    grant_for(lucia, haircut, name="Uno", sale_id=str(sold.id))
    assert by_staff()[seller].production_total == 10000
    grant_for(lucia, haircut, name="Dos", sale_id=str(sold.id))
    assert by_staff()[seller].production_total == 0
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, name="Tres", amount=1, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_over_line"
    assert Grant.objects.count() == 2
    # Voiding one gives back only its part of the line.
    svc("service.grant.void", {"id": str(Grant.objects.get(package__name="Uno").id), "reason": "wrong customer"})
    assert by_staff()[seller].production_total == 10000


def test_a_line_a_voucher_paid_is_no_line_to_choose_from(haircut, lucia):
    # It charged 0: the only line that charged anything is the voucher's, with nothing to guess.
    seller = uuid7()
    other = voucher_of_100(lucia, haircut, name="El de la clienta", key="sold-0000")
    order = run(
        "sale.order.open",
        {
            "service_lines": [{"service_id": str(haircut.id)}],
            "open_lines": [
                {"name": "Otro bono", "unit_price": 5000, "tax_category_key": "service.generic", "staff_id": str(seller)}
            ],
        },
    )
    covered = next(line for line in order.lines if line.service_id)
    order = pay_with(order, covered.id, other)
    sold = charge(order, key="sold-0001", customer_id=str(lucia.id), payments=[{"method": "card"}])
    grant = grant_for(lucia, haircut, name="Otro bono", amount=5000, sale_id=str(sold.id))
    assert Grant.objects.get(pk=grant.id).sale_line_id == SaleLine.objects.get(sale=sold.id, name="Otro bono").id
    assert by_staff()[seller].production_total == 0


def test_a_sale_that_charged_nothing_pays_for_no_voucher(haircut, lucia):
    other = voucher_of_100(lucia, haircut, name="El de la clienta", key="sold-0000")
    order = check(haircut)
    sold = charge(pay_with(order, order.lines[0].id, other), key="sold-0001", customer_id=str(lucia.id))
    assert sold.total == 0
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, name="Otro bono", amount=5000, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_over_line"


def test_a_voided_sale_pays_no_voucher(haircut, lucia):
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    run("sale.sale.void", {"sale_id": str(sold.id), "reason": "wrong customer"})
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_sale_voided"


def test_voiding_the_voucher_gives_its_line_back_to_who_sold_it(haircut, lucia):
    # The money is still charged and no voucher lives on it, until a refund says otherwise (SERVICE-F17).
    seller = uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    assert by_staff()[seller].production_total == 0
    notices = OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed")
    assert notices.count() == 1
    svc("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    row = by_staff()[seller]
    assert (row.voucher_sold_total, row.production_total) == (0, 10000)
    # The screens hear of this one too.
    assert notices.count() == 2
    assert last_event("sale.sale.voucher_line_changed")["line_id"] == str(SaleLine.objects.get(name="Bono de 100").id)
    # The same line can pay the voucher granted in its place.
    line = SaleLine.objects.get(name="Bono de 100")
    grant_for(lucia, haircut, name="El bueno", sale_id=str(line.sale_id))
    assert by_staff()[seller].production_total == 0


def test_voiding_a_voucher_not_linked_to_a_line_tells_sales_nothing(haircut, lucia):
    seller = uuid7()
    charged_open("sold-0001", ("Bono de 100", 10000, seller))
    before = OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed").count()
    svc("service.grant.void", {"id": str(grant_for(lucia, haircut).id), "reason": "wrong customer"})
    assert OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed").count() == before == 0


def test_money_back_on_the_line_of_a_voucher_never_takes_production_below_nothing(haircut, lucia):
    seller = uuid7()
    grant_sale = charged_open("sold-0001", ("Bono de 100", 10000, seller))
    grant_for(lucia, haircut, sale_id=str(grant_sale.id))
    allocation = {"payment_id": str(grant_sale.payments[0].id)}
    refund(grant_sale, allocations=[{**allocation, "amount": 3000}], key="value-refund-0001")
    row = by_staff()[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (7000, 7000, 0)
    refund(grant_sale, allocations=[{**allocation, "amount": 7000}], key="value-refund-0002")
    row = by_staff()[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (0, 0, 0)


def test_money_back_shared_with_another_line_comes_off_each_as_it_always_did(haircut, lucia):
    # 100.00 of the voucher and 25.00 of a cut: 50.00 back share out 40.00 and 10.00: 15.00 of the cut are left.
    seller = uuid7()
    sold = charged_open("sold-0001", ("Bono de 100", 10000, seller), ("Corte", 2500, seller))
    line = next(line for line in sold.lines if line.name == "Bono de 100")
    grant_for(lucia, haircut, sale_id=str(sold.id), sale_line_id=str(line.id))
    refund(sold, allocations=[{"payment_id": str(sold.payments[0].id), "amount": 5000}], key="value-refund-0001")
    row = by_staff()[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (7500, 6000, 1500)


def test_voiding_the_sale_of_a_voucher_takes_it_off_every_figure_of_who_sold_it(haircut, lucia):
    seller, doer = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    spend_session(grant, haircut, lucia, "value-0001", staff=doer)
    run("sale.sale.void", {"sale_id": str(SaleLine.objects.get(name="Bono de 100").sale_id), "reason": "wrong"})
    rows = by_staff()
    assert seller not in rows
    # The voucher sold lives on (SERVICE-F27 does not void it): its session stays with who did it.
    assert rows[doer].production_total == 3333


def test_the_employee_who_grants_says_the_sale_with_their_own_permissions(haircut, lucia):
    employee = ctx_for(EMPLOYEE)
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    package = svc("service.package.create", {"name": "Bono", "max_uses": 3, "items": [{"service_id": str(haircut.id)}]})
    grant = run(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id), "amount": 10000, "sale_id": str(sold.id)},
        employee,
    )
    assert Grant.objects.get(pk=grant.id).sale_line_id == sold.lines[0].id


def test_who_may_not_charge_may_not_say_what_a_line_paid(haircut, lucia):
    op = get("sale.sale.voucher_sold")
    assert op.permission == "sale.take_payment"
    assert get("sale.sale.voucher_unsold").permission == "sale.take_payment"
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    no_charge = ctx_for(EMPLOYEE)
    no_charge = no_charge.__class__(
        **{**no_charge.__dict__, "permissions": no_charge.permissions - {"sale.take_payment"}}
    )
    with pytest.raises(PermissionDenied):
        op(no_charge, op.input.model_validate({"sale_id": str(sold.id), "amount": 10000}))


def test_a_grant_that_says_its_sale_with_sales_off_is_granted_without_a_line(haircut, lucia, monkeypatch):
    # With Sales off there is no figure to count it in; the voucher is sold all the same. It says no line, so its
    # sessions count nothing. Voiding it asks nothing of Sales either.
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)
    grant = grant_for(lucia, haircut, sale_id=str(uuid7()))
    row = Grant.objects.get(pk=grant.id)
    assert (row.sale_id is not None, row.sale_line_id) == (True, None)
    svc("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    assert Grant.objects.get(pk=grant.id).voided_at is not None


def test_voiding_a_linked_voucher_with_sales_off_still_voids_and_the_line_stays_out(haircut, lucia, monkeypatch):
    seller = uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    saved = {name: op for name, op in registry.items() if name.startswith("sale.")}
    for name in saved:
        monkeypatch.delitem(registry, name)
    svc("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    assert Grant.objects.get(pk=grant.id).voided_at is not None
    for name, op in saved.items():
        monkeypatch.setitem(registry, name, op)
    # Nothing counts twice: the line stays out of who sold it until a person sees to it.
    assert by_staff()[seller].production_total == 0
