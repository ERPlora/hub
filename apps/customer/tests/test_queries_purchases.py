"""A card's purchases with their amount and status, refunds included (CUSTOMER-F22, F23, ``purchase_ledger.pg``),
and the cards whose figures disagree with them."""

import uuid
from datetime import timedelta

from apps.customer.models import Purchase
from apps.customer.schemas.purchases import DivergencesIn, PurchaseListIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def test_the_purchases_with_their_amount_and_status():
    ana = card("Ana")
    first = Purchase.objects.create(
        customer=ana,
        sale_id=uuid.uuid7(),
        amount=1250,
        currency="EUR",
        recorded_at=NOW - timedelta(days=1),
    )
    second = Purchase.objects.create(
        customer=ana, sale_id=uuid.uuid7(), amount=300, status="voided", recorded_at=NOW
    )
    page = run("customer.purchase.list", PurchaseListIn(customer_id=ana.id))
    assert [(row.sale_id, row.amount, row.status) for row in page.rows] == [
        (second.sale_id, 300, "voided"),
        (first.sale_id, 1250, "confirmed"),
    ]
    assert [
        row.amount
        for row in run(
            "customer.purchase.list",
            PurchaseListIn(customer_id=ana.id, status="confirmed"),
        ).rows
    ] == [1250]
    assert [
        row.amount
        for row in run(
            "customer.purchase.list",
            PurchaseListIn(customer_id=ana.id, sort="amount", descending=False),
        ).rows
    ] == [300, 1250]
    assert (
        run(
            "customer.purchase.list",
            PurchaseListIn(customer_id=ana.id, search=str(first.sale_id)[-6:]),
        ).total
        == 1
    )


def test_divergences_list_the_cards_whose_figures_disagree_with_their_purchases():
    healthy = card("Healthy", total_purchases=1, total_spent=500)
    Purchase.objects.create(customer=healthy, sale_id=uuid.uuid7(), amount=500)
    Purchase.objects.create(
        customer=healthy, sale_id=uuid.uuid7(), amount=700, status="voided"
    )
    card("Drifted", total_purchases=2, total_spent=900)
    page = run("customer.purchase.divergences", DivergencesIn())
    assert [
        (
            row.name,
            row.total_purchases,
            row.ledger_purchases,
            row.total_spent,
            row.ledger_spent,
        )
        for row in page.rows
    ] == [("Drifted", 2, 0, 900, 0)]


def test_a_refund_is_a_line_of_its_own_in_the_history_and_can_be_filtered(  # CUSTOMER-F22
):
    ana = card("Ana")
    sale = uuid.uuid7()
    Purchase.objects.create(customer=ana, sale_id=sale, amount=2420, recorded_at=NOW - timedelta(hours=1))
    Purchase.objects.create(
        customer=ana, sale_id=sale, refund_id=uuid.uuid7(), amount=-1210, status="refunded", recorded_at=NOW
    )
    page = run("customer.purchase.list", PurchaseListIn(customer_id=ana.id))
    assert [(row.amount, row.status) for row in page.rows] == [(-1210, "refunded"), (2420, "confirmed")]
    refunds = run("customer.purchase.list", PurchaseListIn(customer_id=ana.id, status="refunded"))
    assert [row.amount for row in refunds.rows] == [-1210]


def test_a_refunded_card_is_no_divergence():
    # Its spend is what was paid minus what came back; its purchases count the paid ones only.
    refunded = card("Refunded", total_purchases=1, total_spent=1210)
    sale = uuid.uuid7()
    Purchase.objects.create(customer=refunded, sale_id=sale, amount=2420)
    Purchase.objects.create(customer=refunded, sale_id=sale, refund_id=uuid.uuid7(), amount=-1210, status="refunded")
    assert run("customer.purchase.divergences", DivergencesIn()).rows == []
