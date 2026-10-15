"""The customer app's events (``customer.<entity>.<fact>``, recorded by services.py) and its reactions.

The reactions are tested with the Sales app's REAL events: a sale is paid, voided and refunded through
the sale's own operations and its outbox payload is handed to ``events.react``, as the relay will
(phase 2). The sale app is imported here only, in the tests: Customers does not depend on it.
"""

import pytest
from live.context import system_context
from live.models import OutboxEvent
from live.operations import NAME_RE, get

from apps.customer import events
from apps.customer.models import Activity, Customer, Purchase
from apps.customer.tests.conftest import A


def declared():
    """The app's own events (the other apps' it reacts to are named ``SALE_*``)."""
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and not name.startswith("SALE_")
    }


def test_the_events():
    assert declared() == {
        "CUSTOMER_CREATED": "customer.customer.created",
        "CUSTOMER_UPDATED": "customer.customer.updated",
        "CUSTOMER_GROUPS_CHANGED": "customer.customer.groups_changed",
        "CUSTOMER_TAGS_CHANGED": "customer.customer.tags_changed",
        "CUSTOMER_DELETED": "customer.customer.deleted",
        "CUSTOMER_MERGED": "customer.customer.merged",
        "CUSTOMER_ERASED": "customer.customer.erased",
        "NOTE_ADDED": "customer.note.added",
        "ACTIVITY_RECORDED": "customer.activity.recorded",
        "CONSENT_GRANTED": "customer.consent.granted",
        "CONSENT_WITHDRAWN": "customer.consent.withdrawn",
        "ORDER_LINKED": "customer.order.linked",
        "ORDER_UNLINKED": "customer.order.unlinked",
        "PURCHASE_RECORDED": "customer.purchase.recorded",
        "PURCHASE_VOIDED": "customer.purchase.voided",
        "PURCHASE_REFUNDED": "customer.purchase.refunded",
        "GROUP_CREATED": "customer.group.created",
        "GROUP_UPDATED": "customer.group.updated",
        "GROUP_DELETED": "customer.group.deleted",
        "TAG_CREATED": "customer.tag.created",
        "TAG_UPDATED": "customer.tag.updated",
        "TAG_DELETED": "customer.tag.deleted",
        "FIELD_CREATED": "customer.field.created",
        "FIELD_UPDATED": "customer.field.updated",
        "FIELD_DELETED": "customer.field.deleted",
    }


def test_every_event_is_app_entity_fact():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert value.startswith("customer."), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


# Reactions to the Sales app (WORKBOOK «A qué reacciona»; CUSTOMER-F20, F21, F22)


def test_the_reactions():
    assert events.SALE_COMPLETED == "sale.sale.completed"
    assert events.SALE_VOIDED == "sale.sale.voided"
    assert events.SALE_REFUNDED == "sale.sale.refunded"
    assert events.REACTIONS == {
        "sale.sale.completed": "customer.purchase.record",
        "sale.sale.voided": "customer.purchase.void",
        "sale.sale.refunded": "customer.purchase.refund",
    }
    for operation_name in events.REACTIONS.values():
        assert get(operation_name).permission == "customer.record_purchase"


def test_an_event_it_does_not_react_to_does_nothing():
    assert events.react(A, "sale.order.completed", {"order_id": "x"}) is None


def _sale_run(name: str, data: dict):
    from apps.sale.tests.conftest import run

    return run(name, data)


def _last_payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first().payload


@pytest.fixture
def coffee(db):
    """A 12.10 € product, made by inventory as the sale tests make it."""
    get("inventory.product.create")(
        system_context(A),
        get("inventory.product.create").input.model_validate(
            {"name": "Coffee", "sku": "COF", "price": 1210, "tax_category_key": "product.generic"}
        ),
    )


@pytest.fixture
def ana(db):
    op = get("customer.customer.create")
    return op(system_context(A), op.input.model_validate({"name": "Ana López", "phone": "600111222"}))


def _paid(ana, quantity="2"):
    # Paid by card: cash needs an open till session (the sale's till contract), not what is tested here.
    return _sale_run(
        "sale.sale.complete",
        {
            "idempotency_key": "cus-react-0001",
            "lines": [{"product": "COF", "quantity": quantity}],
            "customer_id": str(ana.id),
            "payments": [{"method": "card"}],
        },
    )


@pytest.mark.django_db
def test_a_paid_sale_is_recorded_on_its_card_once(coffee, ana):
    _paid(ana)
    payload = _last_payload("sale.sale.completed")
    assert events.react(A, "sale.sale.completed", payload).recorded is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (1, 2420)
    assert events.react(A, "sale.sale.completed", payload).recorded is False


@pytest.mark.django_db
def test_a_voided_sale_is_taken_off_its_card(coffee, ana):
    sale = _paid(ana)
    events.react(A, "sale.sale.completed", _last_payload("sale.sale.completed"))
    _sale_run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"})
    assert events.react(A, "sale.sale.voided", _last_payload("sale.sale.voided")).voided is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (0, 0)


@pytest.mark.django_db
def test_a_refund_lowers_the_spend_and_stays_in_the_history_once(coffee, ana):
    sale = _paid(ana)
    events.react(A, "sale.sale.completed", _last_payload("sale.sale.completed"))
    _sale_run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "one cup back",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1210}],
            "lines": [],
        },
    )
    payload = _last_payload("sale.sale.refunded")
    refunded = events.react(A, "sale.sale.refunded", payload)
    assert (refunded.refunded, str(refunded.refund_id)) == (True, payload["refund_id"])
    card = Customer.objects.get(pk=ana.id)
    # «Spent» goes down by what came back; «Purchases» does not change (F22).
    assert (card.total_purchases, card.total_spent) == (1, 1210)
    line = Purchase.objects.get(refund_id=payload["refund_id"])
    assert (line.status, line.amount, str(line.sale_id)) == ("refunded", -1210, str(sale.id))
    entry = Activity.objects.get(kind=Activity.Kind.PURCHASE_REFUNDED)
    assert (entry.text, entry.data["amount"]) == ("one cup back", 1210)
    # The same refund delivered twice counts once.
    assert events.react(A, "sale.sale.refunded", payload).refunded is False
    assert Customer.objects.get(pk=ana.id).total_spent == 1210
