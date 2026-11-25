"""The purchases of a card: recorded, voided and refunded with each sale (CUSTOMER-F20, F21, F22)."""

import uuid
from datetime import timedelta

import pytest
from live.errors import PermissionDenied

from apps.customer import events
from apps.customer.models import Customer, Purchase
from apps.customer.schemas.erasing import EraseIn
from apps.customer.schemas.fields import CustomerRefIn as RefIn
from apps.customer.schemas.purchases import PurchaseRecordIn, PurchaseRefundIn, PurchaseVoidIn

from .conftest import HUB_DB, HUB_DB_COMMITTED, NOW, card, clear_outbox, outbox, race, run, system

pytestmark = HUB_DB


# customer.purchase.record / void (CUSTOMER-F20, F21; purchase_ledger.pg)


def totals(customer):
    customer.refresh_from_db()
    return (
        customer.total_purchases,
        customer.total_spent,
        customer.lifecycle_stage,
        customer.last_purchase_at,
    )


def record(customer, sale, total, at=NOW, **extra):
    return system(
        "customer.purchase.record",
        PurchaseRecordIn(
            customer_id=customer.id if customer else None,
            sale_id=sale,
            total=total,
            purchased_at=at,
            **extra,
        ),
    )


def void(sale, reason="mistake"):
    return system("customer.purchase.void", PurchaseVoidIn(sale_id=sale, reason=reason))


def test_a_sale_is_recorded_once_and_moves_the_stage():
    ana = card("Ana")
    first, second = uuid.uuid7(), uuid.uuid7()
    assert record(ana, first, 1250, currency="EUR").recorded is True
    assert totals(ana) == (1, 1250, "first_purchase", NOW)
    assert (
        record(ana, first, 1250, at=NOW + timedelta(minutes=5)).recorded is False
    )  # redelivered
    assert totals(ana) == (1, 1250, "first_purchase", NOW)
    later = NOW + timedelta(days=1)
    record(ana, second, 300, at=later)
    assert totals(ana) == (2, 1550, "active", later)
    purchase = Purchase.objects.get(sale_id=first)
    assert (purchase.amount, purchase.currency, purchase.status) == (
        1250,
        "EUR",
        "confirmed",
    )
    timeline = list(ana.activity.values_list("kind", "related_id", "data"))
    assert timeline[-1] == (
        "purchase_recorded",
        str(first),
        {"amount": 1250, "currency": "EUR"},
    )
    assert [name for name, _ in outbox()] == [events.PURCHASE_RECORDED] * 2
    assert outbox()[0][1] == {"customer_id": str(ana.id), "sale_id": str(first)}


def test_a_sale_without_customer_or_for_a_card_that_is_gone_records_nothing():
    assert record(None, uuid.uuid7(), 999).recorded is False
    gone = card("Gone", deleted_at=NOW)
    assert record(gone, uuid.uuid7(), 500).recorded is False
    assert totals(gone)[:2] == (0, 0)
    assert not Purchase.objects.exists() and outbox() == []


def test_a_manual_entry_has_no_sale_and_is_never_deduplicated():
    ana = card("Ana")
    record(ana, None, 100)
    record(ana, None, 100)
    assert totals(ana)[:2] == (2, 200)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("lead", "first_purchase"),
        ("prospect", "first_purchase"),
        ("first_purchase", "active"),
        ("at_risk", "active"),
        ("dormant", "active"),
        ("churned", "churned"),
        ("vip", "vip"),
        ("active", "active"),
    ],
)
def test_the_stage_moves_forward_with_a_purchase(before, after):
    ana = card("Ana", lifecycle_stage=before)
    record(ana, uuid.uuid7(), 100)
    assert totals(ana)[2] == after


def test_a_void_reverts_the_figures_once_and_keeps_the_history():
    ana = card("Ana")
    first, second = uuid.uuid7(), uuid.uuid7()
    record(ana, first, 1250)
    record(ana, second, 300, at=NOW + timedelta(days=1))
    clear_outbox()
    assert void(second).voided is True
    assert totals(ana) == (1, 1250, "first_purchase", NOW)
    assert Purchase.objects.get(sale_id=second).status == "voided"
    assert void(second, "again").voided is False
    assert void(uuid.uuid7()).voided is False
    void(first, "refund")
    assert totals(ana) == (0, 0, "lead", None)
    voids = list(
        ana.activity.filter(kind="purchase_voided").values_list("related_id", "text")
    )
    assert voids == [(str(first), "refund"), (str(second), "mistake")]
    assert outbox() == [
        (events.PURCHASE_VOIDED, {"customer_id": str(ana.id), "sale_id": str(second)}),
        (events.PURCHASE_VOIDED, {"customer_id": str(ana.id), "sale_id": str(first)}),
    ]


def test_a_void_never_demotes_a_vip():
    ana = card("Ana", lifecycle_stage="vip")
    sale = uuid.uuid7()
    record(ana, sale, 100)
    void(sale)
    assert totals(ana)[2] == "vip"


@pytest.mark.parametrize(
    "role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
)
def test_only_the_system_records_and_voids_purchases(role):
    ana = card("Ana")
    with pytest.raises(PermissionDenied):
        run(
            "customer.purchase.record",
            PurchaseRecordIn(customer_id=ana.id, sale_id=uuid.uuid7(), total=100),
            role,
        )
    with pytest.raises(PermissionDenied):
        run("customer.purchase.void", PurchaseVoidIn(sale_id=uuid.uuid7()), role)


def test_a_deleted_card_with_purchases_keeps_them_and_a_later_sale_does_not_add_up():
    ana = card("Ana")
    record(ana, uuid.uuid7(), 500)
    run("customer.customer.delete", RefIn(id=ana.id))
    assert record(ana, uuid.uuid7(), 700).recorded is False
    assert (ana.purchases.count(), totals(ana)[:2]) == (1, (1, 500))


# customer.purchase.refund (CUSTOMER-F22)


def refund(sale, refund_id, total, reason="returned", at=None):
    return system(
        "customer.purchase.refund",
        PurchaseRefundIn(
            sale_id=sale,
            refund_id=refund_id,
            total=total,
            reason=reason,
            refunded_at=at,
        ),
    )


def test_a_refund_lowers_the_spend_once_and_leaves_a_negative_line_in_the_history():
    ana = card("Ana")
    sale, first, second = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    record(ana, sale, 2420, currency="EUR")
    clear_outbox()
    later = NOW + timedelta(hours=2)
    assert refund(sale, first, 1210, "one cup back", later).refunded is True
    # «Spent» goes down by what came back; «Purchases», the last purchase and the stage do not move.
    assert totals(ana) == (1, 1210, "first_purchase", NOW)
    line = Purchase.objects.get(refund_id=first)
    assert (
        line.sale_id,
        line.amount,
        line.currency,
        line.status,
        line.recorded_at,
        line.void_reason,
    ) == (
        sale,
        -1210,
        "EUR",
        "refunded",
        later,
        "one cup back",
    )
    assert refund(sale, first, 1210).refunded is False  # redelivered
    assert (
        refund(sale, second, 1210).refunded is True
    )  # a second refund of the same sale
    assert totals(ana)[:2] == (1, 0)
    entries = list(
        ana.activity.filter(kind="purchase_refunded").values_list("text", "data")
    )
    assert entries == [
        ("returned", {"amount": 1210, "currency": "EUR"}),
        ("one cup back", {"amount": 1210, "currency": "EUR"}),
    ]
    assert outbox() == [
        (
            events.PURCHASE_REFUNDED,
            {"customer_id": str(ana.id), "sale_id": str(sale), "refund_id": str(first)},
        ),
        (
            events.PURCHASE_REFUNDED,
            {
                "customer_id": str(ana.id),
                "sale_id": str(sale),
                "refund_id": str(second),
            },
        ),
    ]


def test_a_refund_of_a_sale_not_recorded_or_voided_changes_nothing():
    assert refund(uuid.uuid7(), uuid.uuid7(), 100).refunded is False
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)
    void(sale)
    clear_outbox()
    assert refund(sale, uuid.uuid7(), 500).refunded is False
    assert totals(ana)[:2] == (0, 0) and outbox() == []


def test_a_refund_of_an_erased_card_counts_but_adds_nothing_to_its_timeline():
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)
    run("customer.customer.erase", EraseIn(id=ana.id))
    assert refund(sale, uuid.uuid7(), 200).refunded is True
    assert totals(ana)[:2] == (1, 300)
    assert list(ana.activity.values_list("kind", flat=True)) == ["erased"]


@pytest.mark.parametrize(
    "role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
)
def test_only_the_system_records_refunds(role):
    with pytest.raises(PermissionDenied):
        run(
            "customer.purchase.refund",
            PurchaseRefundIn(sale_id=uuid.uuid7(), refund_id=uuid.uuid7(), total=100),
            role,
        )


def test_voiding_a_sale_of_an_erased_card_adds_nothing_to_its_timeline():
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)
    run("customer.customer.erase", EraseIn(id=ana.id))
    assert void(sale).voided is True
    assert totals(ana)[:2] == (0, 0)
    assert list(ana.activity.values_list("kind", flat=True)) == ["erased"]


@HUB_DB_COMMITTED
def test_a_void_locks_the_card_before_its_purchase_so_it_never_deadlocks_with_a_merge(plan_with_room):
    # A merge locks the cards and then their purchases; a void used to lock the purchase and then
    # the card. Both orders at once wait for each other until Postgres kills one of them.
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)

    def lock_the_card():
        Customer.objects.select_for_update().get(pk=ana.pk)

    def then_its_purchases():
        list(Purchase.objects.select_for_update().filter(customer=ana))

    assert (
        race(lock_the_card, lambda: void(sale), then=then_its_purchases).voided is True
    )
    assert totals(ana)[:2] == (0, 0)
