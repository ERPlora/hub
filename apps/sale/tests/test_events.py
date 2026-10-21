"""The sale app's events (``sale.<entity>.<fact>``) and its reactions to Customers' merge and to the
document Invoicing issues for a sale.

There is no outbox relay yet (phase 2 runs it in the worker); a reaction is tested by handing ``react``
the event as the relay will: its name, its scope and its payload.
"""

import re

import pytest
from live.context import Scope
from live.operations import NAME_RE

from apps.sale import events
from apps.sale.models import Sale
from apps.sale.tests.conftest import run

PAST_FACT = re.compile(r"^sale\.[a-z_]+\.[a-z_]+(ed|_from_appointment)$")
A = Scope("host", "a")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("sale.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "SALE_COMPLETED": "sale.sale.completed",
        "SALE_CREATED_FROM_APPOINTMENT": "sale.sale.created_from_appointment",
        "SALE_VOIDED": "sale.sale.voided",
        "SALE_REFUNDED": "sale.sale.refunded",
        "SALE_REASSIGNED": "sale.sale.reassigned",
        "SALE_INVOICED": "sale.sale.invoiced",
        "ORDER_OPENED": "sale.order.opened",
        "ORDER_CHANGED": "sale.order.changed",
        "ORDER_FIRED": "sale.order.fired",
        "ORDER_COMPLETED": "sale.order.completed",
        "ORDER_VOIDED": "sale.order.voided",
        "ORDER_MERGED": "sale.order.merged",
        "ORDER_LINE_REMOVED": "sale.order.line_removed",
        "ORDER_LINE_VOIDED": "sale.order.line_voided",
        "PAYMENT_METHOD_CREATED": "sale.payment_method.created",
        "SETTINGS_UPDATED": "sale.settings.updated",
        "DEPARTMENT_CREATED": "sale.department.created",
        "DEPARTMENT_UPDATED": "sale.department.updated",
        "DEPARTMENT_DELETED": "sale.department.deleted",
        "QUICK_NOTE_CREATED": "sale.quick_note.created",
        "QUICK_NOTE_UPDATED": "sale.quick_note.updated",
        "QUICK_NOTE_DELETED": "sale.quick_note.deleted",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_it_reacts_to_two_customer_cards_merged_and_to_a_document_issued():
    # Invoicing issues the document of a sale in the charge itself; when it could not (no issuer yet,
    # INVOICE-F06) its own reaction issues it later, and the sale learns its number from the notice.
    assert events.REACTIONS == {
        "customer.customer.merged": "sale.customer.reassign",
        "invoice.invoice.issued": "sale.sale.record_invoice",
    }


def test_an_event_it_does_not_follow_is_ignored():
    assert events.react(A, "customer.customer.created", {"id": "x"}) is None


@pytest.mark.django_db
def test_the_merge_of_customer_moves_the_sales(product, customer):
    product("Coffee", "COF", 150, "product.generic")
    ana, duplicate = customer("Ana López"), customer("Ana Lopez")
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "react-key-01",
            "lines": [{"product": "COF"}],
            "customer_id": str(duplicate.id),
        },
    )
    # Customers' own merge, which records the event the relay will hand over.
    run(
        "customer.customer.merge", {"id": str(ana.id), "absorbed_id": str(duplicate.id)}
    )
    from live.models import OutboxEvent

    merged = OutboxEvent.objects.get(name="customer.customer.merged")
    result = events.react(A, merged.name, merged.payload)
    assert result.moved == 1
    assert Sale.objects.get().customer_id == ana.id


# ── A document Invoicing issued later, linked by its ``source`` (INVOICE-F06) ───────────────────────

ISSUER = {
    "legal_name": "Bar Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}


def _issued_notices(since: int = 0) -> list:
    from live.models import OutboxEvent

    return list(
        OutboxEvent.objects.filter(name="invoice.invoice.issued").order_by("created_at", "id")
    )[since:]


def _deliver_to_invoicing(name: str):
    """Hands Sales' newest event ``name`` to Invoicing's real reaction, as the relay will."""
    from live.models import OutboxEvent

    from apps.invoice import events as invoice_events

    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()
    return invoice_events.react(A, event.name, event.payload)


def _card_charge(key: str, ctx=None):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "lines": [{"product": "COF"}], "payments": [{"method": "card"}]},
        ctx,
    )


@pytest.mark.django_db
def test_the_rectifying_invoice_of_a_void_issued_later_goes_back_to_its_sale(product):
    # No issuer at the till: the ticket and the void's rectifying invoice both wait (pending). Invoicing
    # issues them from the outbox once the issuer exists and gives each to the sale as it issues it
    # (INVOICE-F06); each notice carries its real ``source``, and Sales' reaction to it changes nothing.
    product("Coffee", "COF", 150, "restaurant.drink")
    sale = _card_charge("source-void-01")
    voided = run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    assert (voided.invoice_status, voided.void_invoice_status) == ("pending", "pending")
    run("invoice.issuer.update", ISSUER)
    ticket = _deliver_to_invoicing("sale.sale.completed").invoice
    rectification = _deliver_to_invoicing("sale.sale.voided").invoice
    notices = _issued_notices()
    assert [n.payload["source"]["void"] for n in notices] == [False, True]
    read = Sale.objects.get(pk=sale.id)
    assert (read.invoice_status, read.invoice_number, read.invoice_id) == (
        "issued",
        ticket.number,
        ticket.id,
    )
    assert (read.void_invoice_status, read.void_invoice_number) == ("issued", rectification.number)
    # The relay's notices come afterwards: nothing new.
    assert not any(events.react(A, n.name, n.payload).recorded for n in notices)


@pytest.mark.django_db
def test_the_rectifying_invoice_of_a_refund_issued_later_goes_back_to_its_refund(product):
    # The ticket was issued at the till; the manager who refunded may not rectify invoices, so the
    # refund's rectifying invoice waits and Invoicing's reaction issues it: the refund has its number at
    # once (INVOICE-F06), the sale's own documents do not change, and Sales' reaction to the notice
    # changes nothing.
    from apps.sale.models import Refund
    from apps.sale.tests.conftest import ctx_for

    product("Coffee", "COF", 150, "restaurant.drink")
    run("invoice.issuer.update", ISSUER)
    sale = _card_charge("source-refund-01")
    assert sale.invoice_status == "issued"
    manager = ctx_for("hub_manager")
    manager = type(manager)(
        scope=manager.scope,
        actor=manager.actor,
        permissions=manager.permissions - {"invoice.rectify_invoice"},
    )
    payment = Sale.objects.get(pk=sale.id).payments.get()
    refunded = run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Broken",
            "allocations": [{"payment_id": str(payment.id), "amount": 100}],
        },
        manager,
    )
    refund = Refund.objects.get(sale_id=sale.id)
    assert (refunded.invoice_status, refund.invoice_status) == ("pending", "pending")
    before = len(_issued_notices())
    rectification = _deliver_to_invoicing("sale.sale.refunded").invoice
    (notice,) = _issued_notices(before)
    assert notice.payload["source"] == {
        "type": "refund",
        "sale_id": str(sale.id),
        "refund_id": str(refund.id),
        "void": False,
    }
    refund.refresh_from_db()
    assert (refund.invoice_status, refund.invoice_number, refund.invoice_type) == (
        "issued",
        rectification.number,
        rectification.invoice_type,
    )
    read = Sale.objects.get(pk=sale.id)
    assert (read.invoice_number, read.void_invoice_status) == (sale.invoice_number, "")
    assert events.react(A, notice.name, notice.payload).recorded is False


@pytest.mark.django_db
def test_a_document_not_issued_from_a_sale_is_ignored(product):
    product("Coffee", "COF", 150, "restaurant.drink")
    sale = _card_charge("source-other-01")
    other = {
        "invoice_id": "01a13bcd-5bb9-756f-9dd6-f03399fe7360",
        "number": "F-2026-000001",
        "invoice_type": "F1",
        "source_type": "manual",
        "sale_id": None,
        "source": {"type": "manual", "sale_id": None, "refund_id": None, "void": False},
    }
    assert events.react(A, "invoice.invoice.issued", other).recorded is False
    # A full invoice that replaces the ticket (F3) or a rectification of an invoice are Invoicing's: the
    # sale keeps the document of its charge.
    for kind, invoice_type in (("substitution", "F3"), ("rectification", "R1")):
        notice = {**other, "invoice_type": invoice_type, "source_type": kind, "sale_id": str(sale.id)}
        notice["source"] = {"type": kind, "sale_id": str(sale.id), "refund_id": None, "void": False}
        assert events.react(A, "invoice.invoice.issued", notice).recorded is False
    assert Sale.objects.get(pk=sale.id).invoice_status == "pending"
