"""The barcode label Inventory asks for, seen from Printing (PRINTING-F12, INVENTORY-F25). No mocks: «Print barcode»
on the product sheet (``inventory.product.print_label``) calls ``printing.job.create`` by name, and the label lands
in the queue of the «Label» function. Without a printer of that function it waits there and the «Label» card of the
print queue says so (the card paints «Waiting, no printer» for a function with jobs and no active printer); the
first label printer a device reaches takes it, with the product's name, its SKU as the code and its price. A label
never comes out on the receipt printer, and a label asked in one hub wakes that hub's screens only.
"""

import pytest
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import A, B, ctx_for, printer, received, run
from apps.tax.models import TaxCategory

pytestmark = pytest.mark.django_db

SKU = "SHA-250"
TAX = "product.generic"


def product(scope=A):
    data = {"name": "Shampoo «Argan»", "sku": SKU, "price": 1210, "tax_category_key": TAX}
    return run("inventory.product.create", data, ctx_for(scope=scope))


def print_label(item, scope=A):
    """«Print barcode» on the product sheet of Inventory."""
    return run("inventory.product.print_label", {"id": str(item.id)}, ctx_for(scope=scope))


def card(usage: str = "label") -> dict:
    """The card of ``usage`` in the print queue (the summary the printers page shows)."""
    return next(row for row in run("printing.job.summary").usages if row.usage == usage).model_dump()


def claim(*printers, device: str = "Label station"):
    """The device next to ``printers`` asks for its next job (PRINTING-F18)."""
    return run("printing.job.claim", {"printers": [str(p.id) for p in printers], "device": device}).job


def test_without_a_label_printer_each_label_waits_in_its_queue_and_the_label_card_says_so():
    printer("Till")
    shampoo = product()

    first, second = print_label(shampoo), print_label(shampoo)

    assert (first.printer_name, second.printer_name) == (None, None)
    label = card()
    # No active printer and jobs waiting: the card's «Waiting, no printer», one job per press.
    assert (label["printers"], label["prints_on"], label["pending"]) == (0, None, 2)
    assert label["oldest_pending_at"] is not None
    assert card("receipt")["pending"] == 0
    queue = run("printing.job.list", {"search": SKU}).rows
    assert sorted((row.usage, row.status, row.printer_id) for row in queue) == [("label", "pending", None)] * 2


def test_the_waiting_label_comes_out_on_the_first_label_printer_a_device_reaches():
    shampoo = product()
    waiting = print_label(shampoo)
    labels = printer("Labels", usage="label", address="192.168.1.51")

    assert (card()["printers"], card()["prints_on"], card()["pending"]) == (1, "Labels", 1)
    job = claim(labels)

    assert (job.id, job.printer_id, job.document_type) == (waiting.job_id, labels.id, "barcode_label")
    assert {key: job.document[key] for key in ("product_name", "barcode", "price")} == {
        "product_name": "Shampoo «Argan»",
        "barcode": SKU,
        "price": 12.1,
    }
    assert (card()["pending"], card()["sent"]) == (0, 1)


def test_a_label_never_comes_out_on_the_receipt_printer():
    till = printer("Till")
    out = print_label(product())

    assert claim(till, device="Till") is None
    assert PrintJob.objects.values_list("status", "printer_id").get(pk=out.job_id) == (PrintJob.Status.PENDING, None)


def test_the_label_re_runs_the_label_card_and_the_queue():
    out = print_label(product())

    queued = OutboxEvent.objects.get(name="printing.job.queued")
    assert queued.payload == {"id": str(out.job_id), "usage": "label", "printer_id": None, "kind": "document"}
    assert {"printing.job.summary", "printing.job.list"} <= set(live_registry.affected([queued.name]))


@pytest.mark.django_db(transaction=True)
def test_a_label_asked_in_b_wakes_b_only(listen):
    # A transactional test before this one may have flushed the tax categories the migrations seed.
    TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
    shampoo = product(B)
    on_a, on_b = listen(A), listen(B)

    print_label(shampoo, B)

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["printing.job.queued"]})]
    assert received(on_a, timeout=0.3) == []
