"""Two devices at once (INVOICE-F01, F08, F09, F11): real sessions in threads, real row locks.

A series numbers every document once and never leaves a hole, also with six issuing at once; the same
charge or the same refund delivered twice at once is one document and one number; two rectifications of
the same invoice at once are one rectification, and the other is refused without spending a number
(the current product's open question 12, closed here with its test).
"""

import threading

import pytest
from django.db import connection
from django.utils import timezone
from live.errors import OperationError

from apps.customer.models import Customer
from apps.customer.tests.conftest import card_deleted_on_screen, card_protected, reads, writes
from apps.invoice.models import Invoice, InvoiceSeries, Issuer
from apps.invoice.tests.conftest import ISSUER, deliver, run
from apps.sale.models import Sale

pytestmark = pytest.mark.django_db(transaction=True)

TODAY = timezone.localdate()
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
}


@pytest.fixture(autouse=True)
def factory_data(transactional_db):
    """A transactional test starts from a flushed database: tax's factory catalogue and the factory
    payment methods are planted again, as their migrations do (idempotent); then the issuer."""
    from importlib import import_module

    from django.apps import apps as registry

    with connection.schema_editor() as editor:
        for module in (
            "apps.tax.migrations.0002_factory_catalogue",
            "apps.tax.migrations.0005_retail_alcohol",
            "apps.sale.migrations.0002_factory_payment_methods",
        ):
            import_module(module).plant(registry, editor)
    run("invoice.issuer.update", ISSUER)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def manual():
    return run(
        "invoice.invoice.create",
        {
            "lines": [
                {
                    "description": "Course",
                    "quantity": "1",
                    "unit_price": 1000,
                    "tax_rate": "21",
                }
            ],
            **RECIPIENT,
        },
    )


def outcome(result) -> str:
    code = getattr(result, "code", None)
    if code:
        return code
    if isinstance(result, Exception):
        return repr(result)
    return "already" if getattr(result, "already", False) else "ok"


def test_six_documents_at_once_take_six_numbers_in_a_row_without_a_hole():
    results = at_once(*(manual for _ in range(6)))
    assert [outcome(result) for result in results] == ["ok"] * 6
    assert sorted(result.number for result in results) == [
        f"FACT-{TODAY.year}-{n:06d}" for n in range(1, 7)
    ]
    assert InvoiceSeries.objects.get(code="FACT", year=TODAY.year).current_number == 6


def charged_without_document(charge, key: str):
    """A sale charged while Invoicing cannot issue (no issuer yet): the till leaves its document pending
    and Invoicing's reaction to the outbox issues it later (INVOICE-F06), here raced twice."""
    Issuer.objects.all().delete()
    sale = charge(key)
    assert not Invoice.objects.exists()
    run("invoice.issuer.update", ISSUER)
    return sale


def test_the_same_charge_delivered_twice_at_once_is_one_invoice_and_one_number(
    product, charge
):
    product()
    charged_without_document(charge, "race-0001")
    results = at_once(
        lambda: deliver("sale.sale.completed"), lambda: deliver("sale.sale.completed")
    )
    assert sorted(outcome(result) for result in results) == ["already", "ok"]
    assert results[0].invoice.id == results[1].invoice.id
    assert Invoice.objects.count() == 1
    assert InvoiceSeries.objects.get(code="TICKET", year=TODAY.year).current_number == 1


def test_two_rectifications_of_one_invoice_at_once_are_one_and_spend_one_number():
    invoice = manual()
    results = at_once(
        lambda: run(
            "invoice.invoice.rectify",
            {"invoice_id": str(invoice.id), "reason": "first"},
        ),
        lambda: run(
            "invoice.invoice.rectify",
            {"invoice_id": str(invoice.id), "reason": "second"},
        ),
    )
    assert sorted(outcome(result) for result in results) == [
        "invoice.already_cancelled",
        "ok",
    ]
    assert Invoice.objects.filter(rectifies_id=invoice.id).count() == 1
    assert InvoiceSeries.objects.get(code="RECT", year=TODAY.year).current_number == 1


def test_the_same_refund_delivered_twice_at_once_is_one_rectification(product, charge):
    product()
    Issuer.objects.all().delete()
    sale = charge("race-0002")
    payment = Sale.objects.get(pk=sale.id).payments.get()
    # Refunded before its ticket exists: the till leaves the rectification pending too.
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "x",
            "allocations": [{"payment_id": str(payment.id), "amount": 500}],
        },
    )
    run("invoice.issuer.update", ISSUER)
    deliver("sale.sale.completed")
    results = at_once(
        lambda: deliver("sale.sale.refunded"), lambda: deliver("sale.sale.refunded")
    )
    assert sorted(outcome(result) for result in results) == ["already", "ok"]
    assert Invoice.objects.filter(invoice_type__startswith="R").count() == 1
    assert InvoiceSeries.objects.get(code="RECT", year=TODAY.year).current_number == 1


# ── The Hub admin's «Delete» of the customer's card while a document names it ────────────────────
#
# An invoice by hand and the full invoice that replaces a ticket find the recipient's card and then write the
# document that points at it. The Hub admin's «Delete» of that card between the two found nothing protecting it
# and deleted it: the document then failed at its COMMIT (an IntegrityError, a 500; its number was not spent).
# The document locks the card when it finds it, before its ticket and its series' number, as a charge does: the
# deletion waits for it and answers «Cannot delete», since the document protects the card; a document that comes
# second waits for the deletion and is told the card is gone, spending no number.

HOW = ["page", "list"]


def by_hand(card):
    data = {
        "lines": [{"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
        "customer_id": str(card.id),
    }
    return lambda: run("invoice.invoice.create", data)


def full_for_a_ticket(card):
    simplified = run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [{"description": "Coffee", "quantity": "2", "unit_price": 150, "tax_rate": "10"}],
        },
    )
    data = {"number": simplified.number, "customer_id": str(card.id)}
    return lambda: run("invoice.invoice.substitute", data)


#: The documents that name a card, and the series that numbers them.
CARD_DOCUMENTS = {"by hand": by_hand, "full for a ticket": full_for_a_ticket}


def a_card() -> Customer:
    return Customer.objects.create(
        name="Talleres Pérez SL", tax_id="B12345674", address="Calle Luna 3", city="Madrid"
    )


def fact_numbers() -> int:
    series = InvoiceSeries.objects.filter(code="FACT", year=TODAY.year).first()
    return series.current_number if series else 0


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("document", sorted(CARD_DOCUMENTS))
def test_the_hub_admin_cannot_delete_a_card_a_document_names_meanwhile(document, how):
    card = a_card()
    issue = CARD_DOCUMENTS[document](card)
    with card_deleted_on_screen(card, how, writes("invoice_invoice")) as answers:
        issue()
    [answer] = answers
    assert card_protected(answer)
    assert Invoice.objects.get(customer=card).number == f"FACT-{TODAY.year}-000001"


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("document", sorted(CARD_DOCUMENTS))
def test_a_document_whose_card_the_hub_admin_deletes_first_is_told_it_is_gone(document, how):
    card = a_card()
    issue = CARD_DOCUMENTS[document](card)
    with card_deleted_on_screen(card, how, reads("customer_customer")) as answers:
        with pytest.raises(OperationError) as refused:
            issue()
    [answer] = answers
    assert answer.status_code == 302
    assert (refused.value.status, refused.value.code) == (404, "customer.customer_unavailable")
    assert not Customer.objects.filter(pk=card.pk).exists()
    assert not Invoice.objects.filter(invoice_type__in=["F1", "F3"]).exists()
    assert fact_numbers() == 0
