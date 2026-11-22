"""A business registered for intra-EU operations (the ROI) says so on its issuer (INVOICE-F21): from then on its
documents print its EU VAT number (ESB12345674) on screen and on the A4 (INVOICE-F18), while VeriFactu's record and
its QR keep the bare tax ID, the only one the AEAT accepts. Each document keeps the mark with its copy of the issuer,
so a reprint says what the original said. Real operations, no mocks."""

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import HUB_DB, ISSUER, ctx_for, run
from apps.verifactu.models import Record

pytestmark = HUB_DB

TAX_ID = ISSUER["tax_id"]
VAT_NUMBER = f"ES{TAX_ID}"
LINE = {"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}
RECIPIENT = {"customer_name": "Talleres Pérez SL", "customer_tax_id": "76543210S", "customer_address": "Calle Luna 3"}


def issuer(registered: bool | None = None):
    data = ISSUER if registered is None else {**ISSUER, "intra_eu_operator": registered}
    return run("invoice.issuer.update", data)


def manual():
    return run("invoice.invoice.create", {"lines": [LINE], **RECIPIENT})


def printed(invoice) -> str:
    return run("invoice.invoice.get", {"invoice_id": str(invoice.id)}).issuer_vat_number


def a4(invoice) -> str:
    return run("invoice.invoice.document", {"invoice_id": str(invoice.id)}, ctx_for(language="es")).html


def test_an_issuer_is_not_registered_until_the_business_says_so():
    saved = issuer()

    assert (saved.intra_eu_operator, saved.vat_number) == (False, TAX_ID)
    got = run("invoice.issuer.get")
    assert (got.intra_eu_operator, got.vat_number) == (False, TAX_ID)


def test_a_registered_issuer_keeps_its_tax_id_and_prints_its_eu_vat_number():
    saved = issuer(registered=True)

    assert (saved.tax_id, saved.intra_eu_operator, saved.vat_number) == (TAX_ID, True, VAT_NUMBER)
    got = run("invoice.issuer.get")
    assert (got.tax_id, got.intra_eu_operator, got.vat_number) == (TAX_ID, True, VAT_NUMBER)


def test_unmarked_again_the_issuer_prints_its_tax_id_as_before():
    issuer(registered=True)

    saved = issuer(registered=False)

    assert (saved.intra_eu_operator, saved.vat_number) == (False, TAX_ID)


def test_its_invoice_and_its_a4_print_the_eu_vat_number_while_verifactu_keeps_the_bare_tax_id():
    issuer(registered=True)

    invoice = manual()

    got = run("invoice.invoice.get", {"invoice_id": str(invoice.id)})
    assert (got.issuer_tax_id, got.issuer_vat_number) == (TAX_ID, VAT_NUMBER)
    assert f"NIF: {VAT_NUMBER}" in a4(invoice)
    record = Record.objects.get(invoice_id=invoice.id)
    assert record.issuer_nif == TAX_ID
    assert f"<sum1:IDEmisorFactura>{TAX_ID}</sum1:IDEmisorFactura>" in record.xml
    assert f"nif={TAX_ID}&" in record.qr_url and VAT_NUMBER not in record.qr_url


def test_without_the_mark_the_invoice_and_its_a4_print_the_tax_id_as_kept():
    issuer()

    invoice = manual()

    assert printed(invoice) == TAX_ID
    html = a4(invoice)
    assert f"NIF: {TAX_ID}" in html and VAT_NUMBER not in html


def test_each_document_prints_the_mark_it_was_issued_with():
    issuer()
    before = manual()
    issuer(registered=True)
    during = manual()

    issuer(registered=False)

    assert [printed(before), printed(during), printed(manual())] == [TAX_ID, VAT_NUMBER, TAX_ID]
    assert Invoice.objects.get(id=during.id).issuer_intra_eu_operator is True


def test_a_rectifying_invoice_prints_what_its_original_printed():
    issuer(registered=True)
    original = manual()
    issuer(registered=False)

    rectified = run("invoice.invoice.rectify", {"invoice_id": str(original.id), "reason": "Wrong price"})

    assert printed(rectified.invoice) == VAT_NUMBER
