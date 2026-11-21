"""The receipt printer of the till that asks (PRINTING-F22): with two tills, each one's receipts, bills, shift reports and
drawer go to the receipt printer of the device that asks for them (the SPA names it in ``X-Device-Id``), and the
business's receipt printer takes the papers of a device with none of its own. Kitchen, bar, labels and A4 pages keep
the printer of their function in the business.
"""

import pytest

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import HUB_DB, RECEIPT, ctx_for, printer, run
from apps.printing.tests.test_services import EMPLOYEE, ITEM, MANAGER, on_device, register, take

pytestmark = HUB_DB

#: The two tills' own ids, as each one's SPA sends them in ``X-Device-Id``.
BAR_ID = "5a0c2d71-8e14-4b93-a6f2-3d7e9b1c0f45"
TERRACE_ID = "e2b94f10-37c6-4d8a-b5e1-6f0a2c9d7b38"
#: A device nobody set up here: the office's laptop, a waiter's phone.
LAPTOP_ID = "0d6e3b85-c7a2-4f19-8e40-b1d5a9f27c63"


@pytest.fixture
def tills():
    """The bar's till reaches «Till 1» and the kitchen, the terrace's «Till 2» and the kitchen."""
    till_1 = printer("Till 1", address="10.0.0.1")
    till_2 = printer("Till 2", address="10.0.0.2")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.3")
    register(till_1, kitchen, device=BAR_ID, name="Bar")
    terrace = register(till_2, kitchen, device=TERRACE_ID, name="Terrace")
    return {"Till 1": till_1, "Till 2": till_2, "Kitchen": kitchen, "terrace": terrace}


def queue_on(device: str | None, document_type: str = "receipt", document: dict | None = None, **more):
    """An employee on ``device`` asks for a paper (``printing.job.create``), as Sales and Cash do at the till."""
    data = {"document_type": document_type, "document": RECEIPT if document is None else document, **more}
    return run("printing.job.create", data, ctx=on_device(device, EMPLOYEE)).job


def printed_on(device: str | None, **more) -> str | None:
    return queue_on(device, **more).printer_name


def test_each_till_prints_its_receipts_on_its_own_receipt_printer(tills):
    assert printed_on(TERRACE_ID, source_ref="T-1") == "Till 2"
    assert printed_on(BAR_ID, source_ref="T-2") == "Till 1"


@pytest.mark.parametrize(
    ("document_type", "document"),
    [
        ("prebill", {"customer_name": "Table 4", "items": [ITEM], "total": 3.0}),
        ("cash_session_report", {"title": "Z report", "session": "S-1"}),
        ("delivery_note", {"title": "Delivery note A-1", "items": [ITEM]}),
    ],
)
def test_the_bill_the_shift_report_and_every_receipt_paper_go_to_the_till_that_asks(tills, document_type, document):
    assert queue_on(TERRACE_ID, document_type, document).printer_name == "Till 2"


def test_the_drawer_that_opens_is_the_one_of_the_till_that_charged(tills):
    run("printing.settings.update", {"open_drawer_on_sale": True})
    with_receipt = queue_on(TERRACE_ID, automatic=True, open_drawer=True, source_ref="T-1")
    assert (with_receipt.printer_name, with_receipt.kind, with_receipt.open_drawer) == ("Till 2", "document", True)
    run("printing.settings.update", {"print_receipt_on_sale": False})
    drawer_only = queue_on(TERRACE_ID, automatic=True, open_drawer=True, source_ref="T-2")
    assert (drawer_only.printer_name, drawer_only.kind, drawer_only.open_drawer) == ("Till 2", "drawer", True)
    assert not PrintJob.objects.filter(printer_id=tills["Till 1"].id).exists()


def test_kitchen_bar_labels_and_a4_pages_keep_the_printer_of_their_function_in_the_business(tills):
    printer("Bar", usage="bar", address="10.0.0.4")
    printer("Labels", usage="label", address="10.0.0.5")
    printer("Office", kind="system", address="")
    order = {"items": [ITEM]}
    assert queue_on(TERRACE_ID, "kitchen_order", order).printer_name == "Kitchen"
    assert queue_on(TERRACE_ID, "kitchen_order", order, usage="bar").printer_name == "Bar"
    label = {"product_name": "Shampoo", "barcode": "SHA-1", "price": 9.5}
    assert queue_on(TERRACE_ID, "barcode_label", label).printer_name == "Labels"
    assert queue_on(TERRACE_ID, "generic", {"title": "Invoice"}, format="a4", html="<p>Invoice</p>").printer_name == "Office"


def test_a_printer_named_by_the_caller_still_wins(tills):
    assert printed_on(TERRACE_ID, printer="Till 1") == "Till 1"


# ── A till that reaches several receipt printers: the one chosen in Settings, else the first by name ──


def test_with_several_of_its_own_the_till_prints_on_the_one_chosen_in_settings(tills):
    printer("Till 3", address="10.0.0.6")
    register(tills["Till 2"], printer("Till 4", address="10.0.0.7"), device=TERRACE_ID, name="Terrace")
    # None chosen: its first by name.
    assert printed_on(TERRACE_ID, source_ref="T-1") == "Till 2"
    run("printing.settings.update", {"receipt_printer": "Till 4"})
    assert printed_on(TERRACE_ID, source_ref="T-2") == "Till 4"
    # The one chosen is not this till's: its first by name, never a printer it does not reach.
    run("printing.settings.update", {"receipt_printer": "Till 3"})
    assert printed_on(TERRACE_ID, source_ref="T-3") == "Till 2"
    assert printed_on(BAR_ID, source_ref="T-4") == "Till 1"


def test_an_inactive_printer_of_the_till_is_passed_over_for_another_of_its_own(tills):
    register(tills["Till 2"], printer("Till 4", address="10.0.0.7"), device=TERRACE_ID, name="Terrace")
    run("printing.printer.update", {"printer": "Till 2", "is_active": False})
    assert printed_on(TERRACE_ID) == "Till 4"


def test_the_computer_printer_a_till_reaches_never_takes_its_receipts(tills):
    """The computer's printer prints A4 pages: a till that reaches it and a receipt printer prints receipts on the
    latter, and an A4 page still goes to the business's computer printer."""
    office = printer("A4 office", kind="system", address="")
    register(office, tills["Till 2"], device=TERRACE_ID, name="Terrace")
    assert printed_on(TERRACE_ID) == "Till 2"
    assert queue_on(TERRACE_ID, "generic", {"title": "Invoice"}, format="a4", html="<p>Invoice</p>").printer_name == "A4 office"


# ── A device with no receipt printer of its own prints on the business's ───────────────────────────


@pytest.mark.parametrize("device", [None, LAPTOP_ID], ids=["no device", "a device nobody set up"])
def test_from_anywhere_else_the_receipt_goes_to_the_business_receipt_printer(tills, device):
    assert printed_on(device, source_ref="T-1") == "Till 1"
    run("printing.settings.update", {"receipt_printer": "Till 2"})
    assert printed_on(device, source_ref="T-2") == "Till 2"


def test_a_till_set_up_only_for_the_kitchen_prints_its_receipts_on_the_business_one(tills):
    register(tills["Kitchen"], device=LAPTOP_ID, name="Kitchen tablet")
    run("printing.settings.update", {"receipt_printer": "Till 2"})
    assert printed_on(LAPTOP_ID) == "Till 2"


def test_the_assistant_or_an_api_key_without_a_device_gets_the_business_one(tills):
    out = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx=ctx_for(EMPLOYEE))
    assert out.job.printer_name == "Till 1"


# ── If it fails (PRINTING-F22 «Si falla») ─────────────────────────────────────────────────────────


def test_a_receipt_waits_for_its_till_printer_and_never_goes_to_another_till(tills):
    """Till 2 out of paper: the terrace's receipt fails there and goes back to its queue; the bar's till never takes
    it (it would print the terrace's receipt and open the bar's drawer), and a retry keeps it on Till 2."""
    queued = queue_on(TERRACE_ID, source_ref="T-1")
    assert take(tills["Till 1"], device=BAR_ID) is None
    taken = take(tills["Till 2"], device=TERRACE_ID)
    assert taken.id == queued.id
    run(
        "printing.job.fail",
        {"job_id": str(queued.id), "device": TERRACE_ID, "attempt": 1, "error": "out of paper"},
        ctx=ctx_for(EMPLOYEE),
    )
    assert take(tills["Till 1"], device=BAR_ID) is None
    retried = run("printing.job.retry", {"job_id": str(queued.id)})
    assert (retried.printer_name, retried.status) == ("Till 2", "pending")


def test_with_its_printer_deactivated_the_till_queue_and_its_next_receipts_go_to_the_business_one(tills):
    waiting = queue_on(TERRACE_ID, source_ref="T-1")
    run("printing.printer.update", {"printer": "Till 2", "is_active": False}, ctx=ctx_for(MANAGER))
    assert PrintJob.objects.get(pk=waiting.id).printer_id == tills["Till 1"].id
    assert printed_on(TERRACE_ID, source_ref="T-2") == "Till 1"


def test_a_retired_till_prints_its_next_receipts_on_the_business_one(tills):
    run("printing.device.retire", {"device_id": str(tills["terrace"].id)}, ctx=ctx_for(MANAGER))
    assert printed_on(TERRACE_ID) == "Till 1"


def test_with_no_active_receipt_printer_nothing_has_a_printer_to_wait_for(tills):
    for name in ("Till 1", "Till 2"):
        run("printing.printer.update", {"printer": name, "is_active": False}, ctx=ctx_for(MANAGER))
    assert queue_on(TERRACE_ID).printer_id is None


# ── Printing → Printers: the «Receipt» card says where the receipt goes from the device that looks ──


def prints_on(device: str | None, usage: str) -> str | None:
    summary = run("printing.job.summary", ctx=on_device(device, EMPLOYEE))
    return next(row.prints_on for row in summary.usages if row.usage == usage)


def test_the_summary_says_the_receipt_prints_on_the_printer_of_the_device_that_looks(tills):
    assert (prints_on(TERRACE_ID, "receipt"), prints_on(BAR_ID, "receipt")) == ("Till 2", "Till 1")
    assert (prints_on(None, "receipt"), prints_on(LAPTOP_ID, "receipt")) == ("Till 1", "Till 1")
    # The kitchen's printer is the business's, whoever looks.
    assert prints_on(TERRACE_ID, "kitchen") == "Kitchen"
