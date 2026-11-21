"""The paper of Sales on the receipt printer (PRINTING-F07, F08, F09; SALE-F21, F29): the receipt of a sale and
the bill of a check as the app of the device paints them (``crates/peripherals/src/escpos.rs``), composed from
the same figures the screen's paper lays out (``ReceiptPaper.vue``, ``PrebillModal.vue``). Real sales charged
and real checks valued by the till; Printing's own check of a document says the printer would take each one.
"""

import pytest
from django.utils import translation

from apps.printing import documents
from apps.sale import paper
from apps.sale.tests.conftest import HUB_DB, A, run
from apps.sale.tests.test_integration_combo_options import add_menu, charge, dish, menu, open_check, takeaway
from base.models import Hub

pytestmark = HUB_DB

#: The business as ``sale.letterhead.get`` names it (``test_letterhead.py``).
LETTERHEAD = {"name": "Bar Ana SL", "tax_id": "B12345674", "lines": ["Calle Mayor 1", "28001 Madrid"]}


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
    kind, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="Thank you!", duplicate=False)
    assert kind == "receipt"
    assert documents.problems(kind, document) is None
    # A simplified invoice names its issuer and its tax ID (RD 1619/2012, art. 7; hub#458).
    assert (document["business_name"], document["business_address"], document["vat_number"]) == (
        "Bar Ana SL",
        "Calle Mayor 1\n28001 Madrid",
        "B12345674",
    )
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
    assert (document["duplicate"], document["receipt_footer"]) == (False, "Thank you!")
    # Who charged it is added by whoever prints it, by name (hub#1985): never the account's internal id.
    assert "cashier" not in document
    assert paper.cashier("Bea Ruiz") == {"cashier": "Bea Ruiz"} and paper.cashier("") == {}
    assert "qr_data" not in document


def test_a_reprint_says_duplicate_and_a_business_without_issuer_prints_no_tax_id(bar):
    sale = charged()
    bare = {"name": "Bar Ana", "tax_id": "", "lines": []}
    _, document = paper.receipt(sale, letterhead=bare, footer="", duplicate=True)
    assert (document["duplicate"], document["business_name"]) == (True, "Bar Ana")
    assert not {"vat_number", "business_address", "receipt_footer"} & set(document)


def test_a_gift_a_voucher_line_and_the_discount_say_so_as_on_screen(bar):
    sale = charged(
        lines=[{"product": "COF", "quantity": "1", "is_gift": True}, {"product": "TAP", "quantity": "1"}],
        payments=[{"method": "card"}],
        discount_percent="10",
    )
    with translation.override("es"):
        _, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="Gracias", duplicate=False)
    assert document["items"][0]["name"] == "Coffee (Invitación)"
    # The discount is already inside the amounts: it is said under them, never subtracted again.
    assert "discount" not in document
    assert document["receipt_footer"].startswith("Descuento de ")
    assert document["receipt_footer"].endswith("ya aplicado en los importes de arriba.\nGracias")


def test_the_fiscal_qr_opens_the_paper_with_its_legal_texts(bar):
    sale = charged()
    record = {"qr_url": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674&numserie=T-1", "csv": ""}
    _, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="", duplicate=False, record=record)
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
    kind, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="", duplicate=False)
    assert kind == "invoice"
    assert documents.problems(kind, document) is None
    assert (
        document["vat_number"],
        document["customer_name"],
        document["customer_tax_id"],
        document["customer_address"],
    ) == ("B12345674", "Salón Ana SL", "B76543214", "Calle Real 2")
    assert document["tax_breakdown"] == [
        {"rate": float(row.rate_pct), "base": row.base / 100, "tax": row.tax / 100} for row in sale.breakdown
    ]


def test_the_bill_of_a_check_lists_what_is_owed_without_number_or_payment(bar):
    order = run(
        "sale.order.open",
        {"lines": [{"product": "COF", "quantity": "2"}, {"product": "TAP", "quantity": "1"}], "label": "Table 4"},
    )
    valued = run("sale.checkout.preview", {"order_id": str(order.id)})
    with translation.override("es"):
        document = paper.bill(valued, label="Table 4", letterhead=LETTERHEAD, decimals=2)
    assert documents.problems("prebill", document) is None
    assert (document["business_name"], document["customer_name"]) == ("Bar Ana SL", "Table 4")
    # The app's bill prints no `vat_number` (`render_prebill`, escpos.rs): the tax ID travels as a line of the address.
    assert document["business_address"] == "Calle Mayor 1\n28001 Madrid\nNIF: B12345674"
    assert [(item["name"], item["quantity"], item["total"]) for item in document["items"]] == [
        ("Coffee", 2.0, 3.0),
        ("Tapa", 1.0, 4.5),
    ]
    assert document["total"] == 7.5
    assert not {"receipt_id", "payment_method", "paid", "change", "qr_data"} & set(document)


def test_a_discount_in_a_currency_written_in_letters_keeps_the_code_off_the_figure(bar):
    # flow: money-text — the paper writes the amount as the screen does: «PLN 0.75» (no-break space), never «PLN0.75».
    Hub.objects.filter(slug=A.key).update(country="PL")
    for key in ("restaurant.drink", "restaurant.food"):  # a business charges by its own country's rules
        run("tax.rule.create", {"country_code": "PL", "tax_category_key": key, "rate_pct": "8"})
    sale = charged(payments=[{"method": "card"}], discount_percent="10")
    assert sale.currency == "PLN"
    with translation.override("en"):
        _, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="", duplicate=False)
    assert document["receipt_footer"] == "Discount of PLN\xa00.75, already applied to the amounts above."


def test_the_paper_says_when_the_sale_was_charged_and_when_the_bill_was_asked_on_the_businesss_clock(
    bar, night_elsewhere
):
    # The device printed its own hour: the paper brings the hour of what it says, written as the
    # app prints it. At 23:30 of the 2nd in Bogotá it is already the 3rd in Madrid.
    sale = charged()
    _, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="", duplicate=True)
    assert document["date"] == "02/11/2026 23:30"
    order = run("sale.order.open", {"lines": [{"product": "COF", "quantity": "1"}], "label": "Table 4"})
    valued = run("sale.checkout.preview", {"order_id": str(order.id)})
    assert paper.bill(valued, label="Table 4", letterhead=LETTERHEAD, decimals=2)["date"] == "02/11/2026 23:30"


def test_a_menu_in_one_line_prints_the_options_of_each_dish_with_it(menu):
    """SALE-F42: the steak of a menu eaten in, with its doneness and its cheese, under the menu as the screen shows it."""
    dishes, options = menu
    order_id = open_check()
    add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"], options["rare"], options["cheese"]))
    sale = run("sale.sale.get", {"sale_id": str(charge(order_id, "paper-menu-opts-1").id)})
    _kind, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="", duplicate=False)
    assert document["items"] == [
        {"name": "Menu of the day", "quantity": 1.0, "total": 16.5, "components": ["Lentils", "Steak (Rare, Cheese)"]}
    ]


def test_a_dish_of_a_split_menu_prints_its_options_once(takeaway):
    """SALE-F42: to take away, the sandwich names its cheese under it and its glass of wine goes on a line of its own;
    neither is named again as a dish of the menu."""
    dishes, options = takeaway
    order_id = open_check()
    add_menu(order_id, dish(dishes["SAN"], options["cheese"], options["wine"]), dish(dishes["BEE"]), combo="Sandwich and beer")
    sale = run("sale.sale.get", {"sale_id": str(charge(order_id, "paper-menu-opts-2").id)})
    _kind, document = paper.receipt(sale, letterhead=LETTERHEAD, footer="", duplicate=False)
    assert document["items"] == [
        {"name": "Sandwich", "quantity": 1.0, "total": 5.19, "modifiers": ["Cheese"]},
        {"name": "+ Glass of wine", "quantity": 1.0, "total": 1.42},
        {"name": "Beer", "quantity": 1.0, "total": 1.89},
    ]
