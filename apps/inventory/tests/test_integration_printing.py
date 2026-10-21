"""The barcode label of a product, printed by the real Printing app, no mocks (INVENTORY-F25, PRINTING-F12).

Inventory asks Printing for the label by its operation (``printing.job.create``), never by its models: a
``barcode_label`` with the product's name, its SKU as the code and its price in units, for the printer of
the «Label» function. Each press is one label. Without a label printer the label waits in the queue and the
answer says so; without the queue (Printing not reachable for this person) Inventory says so with its own
code, so the screen opens the browser's print dialog instead.
"""

from decimal import Decimal

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.inventory.models import Product
from apps.printing.models import PrintJob

from .conftest import ctx_for, ctx_with

pytestmark = pytest.mark.django_db

TAX = "product.generic"


def run(name: str, data: dict, ctx=None):
    op = get(name)
    return op(ctx or ctx_for("hub_admin"), op.input.model_validate(data))


@pytest.fixture
def shampoo() -> Product:
    created = run(
        "inventory.product.create",
        {"name": "Shampoo «Argan»", "sku": "SHA-250", "price": 1210, "tax_category_key": TAX, "initial_stock": "4"},
    )
    return Product.objects.get(pk=created.id)


def label_printer(name: str = "Labels") -> None:
    run("printing.printer.create", {"name": name, "kind": "network", "address": "192.168.1.50", "usage": "label"})


def test_inventory_f25_the_label_goes_to_the_label_printer_with_name_code_and_price(shampoo):
    label_printer()

    out = run("inventory.product.print_label", {"id": str(shampoo.id)})

    job = PrintJob.objects.get(pk=out.job_id)
    assert (out.printer_name, job.printer.name, job.usage, job.document_type) == (
        "Labels",
        "Labels",
        "label",
        "barcode_label",
    )
    assert {key: job.document[key] for key in ("product_name", "barcode", "price")} == {
        "product_name": "Shampoo «Argan»",
        "barcode": "SHA-250",
        "price": 12.1,
    }
    assert (job.source_app, job.reference, job.copies) == ("inventory", "SHA-250", 1)


def test_inventory_f25_each_press_prints_one_more_label(shampoo):
    label_printer()

    first = run("inventory.product.print_label", {"product": "sha-250"})
    second = run("inventory.product.print_label", {"product": "Shampoo «Argan»"})

    assert first.job_id != second.job_id
    assert PrintJob.objects.filter(document_type="barcode_label").count() == 2


def test_inventory_f25_without_a_label_printer_the_label_waits_in_the_queue_and_says_so(shampoo):
    run("printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.60", "usage": "receipt"})

    out = run("inventory.product.print_label", {"id": str(shampoo.id)})

    assert out.printer_name is None
    job = PrintJob.objects.get(pk=out.job_id)
    assert (job.printer_id, job.status, job.usage) == (None, PrintJob.Status.PENDING, "label")


def test_inventory_f25_whoever_sees_products_prints_it_the_employee_included(shampoo):
    label_printer()

    out = run("inventory.product.print_label", {"id": str(shampoo.id)}, ctx_for("hub_employee"))

    assert PrintJob.objects.get(pk=out.job_id).created_by == "tester"
    with pytest.raises(PermissionDenied):
        run("inventory.product.print_label", {"id": str(shampoo.id)}, ctx_with("printing.print"))


def test_inventory_f25_without_the_print_queue_it_says_so_and_queues_nothing(shampoo):
    label_printer()

    with pytest.raises(Conflict) as refused:
        run("inventory.product.print_label", {"id": str(shampoo.id)}, ctx_with("inventory.view_product"))

    assert refused.value.code == "inventory.label_queue_unavailable"
    assert not PrintJob.objects.filter(document_type="barcode_label").exists()


def test_inventory_f25_a_deleted_product_has_no_label(shampoo):
    run("inventory.product.delete", {"id": str(shampoo.id)})

    with pytest.raises(NotFound):
        run("inventory.product.print_label", {"id": str(shampoo.id)})
    assert not PrintJob.objects.exists()


def test_inventory_f25_the_price_is_in_units_of_the_currency_never_in_cents(shampoo):
    run("inventory.product.update", {"id": str(shampoo.id), "price": 5})

    out = run("inventory.product.print_label", {"id": str(shampoo.id)})

    document = PrintJob.objects.get(pk=out.job_id).document
    # 5 cents: 0.05 €, and the printer is told to paint two decimals (inventory#101).
    assert (Decimal(str(document["price"])), document["decimals"]) == (Decimal("0.05"), 2)


def test_inventory_f25_a_sku_a_barcode_cannot_carry_is_refused_before_anything_is_queued():
    run("inventory.product.create", {"name": "Ñora", "sku": "ÑORA-1", "price": 300, "tax_category_key": TAX})
    label_printer()

    with pytest.raises(Conflict) as refused:
        run("inventory.product.print_label", {"product": "ÑORA-1"})

    assert refused.value.code == "inventory.sku_not_barcode"
    assert not PrintJob.objects.exists()
