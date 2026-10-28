"""The paper of Sales on the receipt printer (PRINTING-F07, F08, F09; SALE-F21, F29): the receipt of a sale and
the bill of a check as the app of the device paints them (``crates/peripherals/src/escpos.rs``), composed from
the same figures the screen's paper lays out (``ReceiptPaper.vue``, ``PrebillModal.vue``). Real sales charged
and real checks valued by the till; Printing's own check of a document says the printer would take each one.
"""

import pytest
from django.utils import translation

from apps.printing import documents
from apps.sale import paper
from apps.sale.tests.conftest import run
from base.models import Hub

pytestmark = pytest.mark.django_db

HEADER = "Bar Ana\nCalle Mayor 1\n28001 Madrid"


@pytest.fixture
def bar(product):
    product("Coffee", "COF", 150, "restaurant.drink")
    product("Tapa", "TAP", 450, "restaurant.food")


def charged(key="paper-sale-1", lines=None, payments=None, **more):
    out = run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": lines or [{"product": "COF", "quantity": "2"}, {"product": "TAP", "quantity": "1"}],
            "payments": payments or [{"method": "cash", "tendered": 1000}],
            **more,
        },
    )
    return run("sale.sale.get", {"sale_id": str(out.id)})


def test_a_ticket_says_what_the_screen_paper_says(bar):
    sale = charged()
    kind, document = paper.receipt(sale, header=HEADER, footer="Thank you!", decimals=2, duplicate=False)
    assert kind == "receipt"
    assert documents.problems(kind, document) is None
    assert (document["business_name"], document["business_address"]) == ("Bar Ana", "Calle Mayor 1\n28001 Madrid")
    # The number Invoicing gave it in the very charge; the sale's own only while it has none.
    assert document["receipt_id"] == (sale.invoice_number or sale.number)
    assert document["items"] == [
        {"name": "Coffee", "quantity": 2.0, "total": 3.0},
        {"name": "Tapa", "quantity": 1.0, "total": 4.5},
    ]
    # Money in units, as the renderer prints it; the totals add up as the screen's.
    assert (document["total"], document["paid"], document["change"]) == (7.5, 10.0, 2.5)
    assert round(document["subtotal"] + document["tax_amount"], 2) == document["total"]
    assert document["payment_method"] == sale.payment_method_name
    assert (document["cashier"], document["duplicate"], document["receipt_footer"]) == (sale.created_by, False, "Thank you!")
    assert "qr_data" not in document


def test_a_reprint_says_duplicate_and_a_business_without_header_is_my_business(bar):
    sale = charged()
    with translation.override("es"):
        _, document = paper.receipt(sale, header="  \n", footer="", decimals=2, duplicate=True)
    assert (document["duplicate"], document["business_name"]) == (True, "Mi negocio")
    assert "business_address" not in document and "receipt_footer" not in document


def test_a_gift_a_voucher_line_and_the_discount_say_so_as_on_screen(bar):
    sale = charged(
        lines=[{"product": "COF", "quantity": "1", "is_gift": True}, {"product": "TAP", "quantity": "1"}],
        payments=[{"method": "card"}],
        discount_percent="10",
    )
    with translation.override("es"):
        _, document = paper.receipt(sale, header=HEADER, footer="Gracias", decimals=2, duplicate=False)
    assert document["items"][0]["name"] == "Coffee (Invitación)"
    # The discount is already inside the amounts: it is said under them, never subtracted again.
    assert "discount" not in document
    assert document["receipt_footer"].startswith("Descuento de ")
    assert document["receipt_footer"].endswith("ya aplicado en los importes de arriba.\nGracias")


def test_the_fiscal_qr_opens_the_paper_with_its_legal_texts(bar):
    sale = charged()
    record = {"qr_url": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674&numserie=T-1", "csv": ""}
    _, document = paper.receipt(sale, header=HEADER, footer="", decimals=2, duplicate=False, record=record)
    assert (document["qr_data"], document["qr_heading"], document["qr_legend"]) == (
        record["qr_url"],
        "QR tributario:",
        "VERI*FACTU",
    )


def test_a_full_invoice_carries_both_parties_and_its_breakdown(bar):
    sale = charged(
        document_type="invoice",
        customer_name="Salón Ana SL",
        customer_tax_id="B76543214",
        customer_address="Calle Real 2",
        payments=[{"method": "card"}],
    )
    kind, document = paper.receipt(
        sale,
        header=HEADER,
        footer="",
        decimals=2,
        duplicate=False,
        issuer_tax_id="B12345674",
        customer_tax_id="B76543214",
        customer_address="Calle Real 2",
    )
    assert kind == "invoice"
    assert documents.problems(kind, document) is None
    assert (document["vat_number"], document["customer_name"], document["customer_tax_id"]) == (
        "B12345674",
        "Salón Ana SL",
        "B76543214",
    )
    assert document["tax_breakdown"] == [
        {"rate": float(row.rate_pct), "base": row.base / 100, "tax": row.tax / 100} for row in sale.breakdown
    ]


def test_the_bill_of_a_check_lists_what_is_owed_without_number_or_payment(bar):
    order = run(
        "sale.order.open",
        {"lines": [{"product": "COF", "quantity": "2"}, {"product": "TAP", "quantity": "1"}], "label": "Table 4"},
    )
    valued = run("sale.checkout.preview", {"order_id": str(order.id)})
    document = paper.bill(valued, label="Table 4", header=HEADER, decimals=2)
    assert documents.problems("prebill", document) is None
    assert (document["business_name"], document["customer_name"]) == ("Bar Ana", "Table 4")
    assert [(item["name"], item["quantity"], item["total"]) for item in document["items"]] == [
        ("Coffee", 2.0, 3.0),
        ("Tapa", 1.0, 4.5),
    ]
    assert document["total"] == 7.5
    assert not {"receipt_id", "payment_method", "paid", "change", "qr_data"} & set(document)


def test_a_discount_in_a_currency_written_in_letters_keeps_the_code_off_the_figure(bar):
    # flow: money-text — the paper writes the amount as the screen does: «PLN 0.75» (no-break space), never «PLN0.75».
    Hub.objects.filter(slug="a").update(country="PL")
    sale = charged(payments=[{"method": "card"}], discount_percent="10")
    assert sale.currency == "PLN"
    with translation.override("en"):
        _, document = paper.receipt(sale, header=HEADER, footer="", decimals=2, duplicate=False)
    assert document["receipt_footer"] == "Discount of PLN\xa00.75, already applied to the amounts above."
