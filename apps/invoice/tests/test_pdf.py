"""The PDF of an invoice (INVOICE-F25): printed by the real WeasyPrint with real VeriFactu records, then opened and read
as whoever receives it does. It says what the A4 page says, word for word, and its QR is the record's."""

import base64
import dataclasses
import datetime as dt
from types import SimpleNamespace

import pytest
from django.utils import translation
from live.context import system_context
from live.errors import AppInactive, Conflict, NotFound, OperationError, PermissionDenied
from live.operations import UnknownOperation, registry

from apps.invoice.models import Invoice
from apps.invoice.queries.documents import render_document
from apps.invoice.queries.pdf import printed
from apps.invoice.services import issuing
from apps.invoice.tests.conftest import A, B, HUB_DB, ISSUER, ctx_for, deliver, run
from apps.invoice.tests.manual import HUNDRED, LINE, NOON, RECIPIENT, line, manual, stored, withheld
from apps.invoice.tests.printed import (
    A4,
    content,
    fonts_not_embedded,
    language,
    opened,
    out_of_the_margins,
    qr_urls,
    sizes,
    text,
    title,
    words,
    words_of_page,
)
from apps.verifactu.models import Record
from base import pdf
from base.models import Hub
from base.tenancy.context import use_hub

pytestmark = HUB_DB

BY_INVOICE = "verifactu.record.by_invoice"
#: The AEAT's own words around the QR, in Spanish whatever the reader's language (Orden HAC/1177/2024, art. 21).
LEGEND = words("QR tributario: VERI*FACTU")


def downloaded(answer, ctx=None, **more):
    return run("invoice.invoice.pdf", {"invoice_id": str(answer.id), **more}, ctx)


def page(answer, language="en", **more) -> str:
    """The A4 page of an invoice for a person who reads ``language``, without its QR."""
    return run("invoice.invoice.document", {"invoice_id": str(answer.id), **more}, ctx_for(language=language)).html


def record_url(answer) -> str:
    """The QR's address as the invoice's screen shows it."""
    return run(BY_INVOICE, {"invoice_id": str(answer.id)}).record.qr_url


def on_paper(out) -> str:
    """The words of the file, one space between them."""
    return " ".join(text(out).split())


# The kinds of invoice


def plain():
    return manual(notes="Pay by transfer")


def with_a_discount(charge, product):
    product()
    charge(
        "pdf-discount",
        [{"product": "SHA", "quantity": "2"}],
        discount_percent="10",
        document_type="invoice",
        **RECIPIENT,
    )
    return deliver("sale.sale.completed").invoice


def ticket(charge, product):
    product()
    charge("pdf-ticket")
    return deliver("sale.sale.completed").invoice


def substitute(charge, product):
    data = {"number": ticket(charge, product).number, **RECIPIENT}
    return run("invoice.invoice.substitute", data).invoice


def rectifying():
    data = {"number": withheld().number, "reason": "Wrong price"}
    return run("invoice.invoice.rectify", data).invoice


def of_a_return(charge, product):
    data = {"number": ticket(charge, product).number, "reason": "Broken"}
    return run("invoice.invoice.rectify", data).invoice


@pytest.fixture
def issued(charge, product, equivalence_surcharge, request):
    """``issued(kind)``: an invoice of each kind a business issues."""
    kinds = {
        "plain": plain,
        "several rates": lambda: manual(lines=[line(1000), line(2000, "10"), line(333, "4")]),
        "with a due date": lambda: manual(due_date="2026-12-24"),
        "with a withholding": withheld,
        "with the equivalence surcharge": lambda: manual(
            lines=[{**LINE, "tax_rate": None, "tax_category_key": "product.generic"}]
        ),
        "exempt": lambda: manual(lines=[{**LINE, "tax_rate": None, "tax_category_key": "service.health"}]),
        "with a discount": lambda: with_a_discount(charge, product),
        "ticket": lambda: ticket(charge, product),
        "substitute": lambda: substitute(charge, product),
        "rectifying": rectifying,
        "rectifying a ticket": lambda: of_a_return(charge, product),
    }
    return lambda kind: kinds[kind]()


KINDS = (
    "plain",
    "several rates",
    "with a due date",
    "with a withholding",
    "with the equivalence surcharge",
    "exempt",
    "with a discount",
    "ticket",
    "substitute",
    "rectifying",
    "rectifying a ticket",
)


@pytest.mark.parametrize("language_", ["en", "es"])
@pytest.mark.parametrize("kind", KINDS)
def test_it_says_what_the_a4_says_word_for_word_with_its_qr(issuer, at, issued, kind, language_):
    at(NOON)
    invoice = issued(kind)

    out = downloaded(invoice, ctx_for(language=language_))

    assert words(text(out)) == words_of_page(page(invoice, language_)) + LEGEND
    assert qr_urls(out) == [record_url(invoice)] == [Record.objects.get(invoice_id=invoice.id).qr_url]


def money(cents) -> str:
    return f"{'-' if cents < 0 else ''}€{abs(cents) / 100:,.2f}"


def price(cents) -> str:
    """A unit price: up to two decimals more than an amount, which a price without VAT may need."""
    whole, _point, decimals = f"{cents / 100:,.4f}".partition(".")
    return f"€{whole}.{decimals[:2]}{decimals[2:].rstrip('0')}"


def percent(rate) -> str:
    return f"{float(rate):g}%"


def day(date) -> str:
    return f"{date:%m/%d/%Y}"


def row_of(item) -> str:
    """A line as its row is read: what it is, how many, its price without VAT, its discount if any, its rate, its base."""
    discount = [money(item.discount_amount)] if item.discount_amount else []
    figures = [f"{float(item.quantity):g}", price(item.unit_price), *discount, percent(item.tax_rate), money(item.base_amount)]
    return " ".join([item.description, *figures])


def taxes_of(invoice) -> list[str]:
    """The rows of the breakdown, one per tax and one more for its surcharge."""
    rows = []
    for entry in invoice.tax_breakdown:
        exempt = entry["qualification"] == "exempt"
        label = f"Exempt ({entry['exempt_reason']})" if exempt else f"VAT {percent(entry['rate'])}"
        rows.append(f"{label} ({money(entry['base'])}) {money(entry['quota'])}")
        if float(entry["surcharge_rate"]):
            surcharge = f"Equivalence surcharge {percent(entry['surcharge_rate'])}"
            rows.append(f"{surcharge} ({money(entry['base'])}) {money(entry['surcharge_quota'])}")
    return rows


TITLES = {"F1": "INVOICE F1", "F2": "SIMPLIFIED INVOICE F2", "F3": "INVOICE F3"}


@pytest.mark.parametrize("kind", KINDS)
def test_each_datum_of_the_invoice_is_in_its_place(issuer, at, issued, kind):
    """What the invoice keeps, read row by row: nothing of the page it was printed from is trusted here."""
    at(NOON)
    invoice = stored(issued(kind))
    type_ = invoice.invoice_type

    paper = on_paper(downloaded(invoice))

    head = f"{TITLES.get(type_, f'RECTIFYING INVOICE {type_}')} No. {invoice.number} Date {day(invoice.issue_date)}"
    if invoice.due_date:
        head += f" Due date {day(invoice.due_date)}"
    parties = f"{invoice.issuer_name} {invoice.issuer_address} Tax ID: {invoice.issuer_tax_id}"
    if invoice.customer_name:
        customer = f"{invoice.customer_name} {invoice.customer_address} Tax ID: {invoice.customer_tax_id}"
    else:
        customer = ""
    totals = [f"Tax base {money(invoice.base_amount)}", *taxes_of(invoice), f"TOTAL {money(invoice.total_amount)}"]
    if invoice.withholding_rate is not None:
        totals.append(f"IRPF withholding {percent(invoice.withholding_rate)} {money(-invoice.withholding_amount)}")
        totals.append(f"Amount due {money(invoice.payable_amount)}")
    if invoice.rectifies_id:
        note = f"Rectifies invoice {invoice.rectifies.number}. Reason: {invoice.description}"
    else:
        note = invoice.notes
    rows = [row_of(item) for item in invoice.lines.all()]
    expected = [head, parties, customer, *rows, " ".join([*totals, note]).strip()]
    assert [said for said in expected if said not in paper] == []
    assert ("BILL TO" in paper) is bool(invoice.customer_name)


@pytest.mark.parametrize(("country", "total"), [("PL", "PLN 121.00"), ("JP", "¥12,100")])
def test_an_invoice_in_another_currency_prints_in_it_and_without_a_spanish_qr(issuer, country, total):
    Hub.objects.filter(slug=A.key).update(country=country)
    invoice = manual(lines=[HUNDRED])

    out = downloaded(invoice)

    assert total in on_paper(out) and "€" not in on_paper(out)
    assert (words(text(out)), qr_urls(out)) == (words_of_page(page(invoice)), [])


# The file


def test_it_is_an_a4_pdf_called_as_the_invoice(issuer):
    invoice = manual()

    out = downloaded(invoice)

    assert (out.filename, out.content_type) == (f"{invoice.number}.pdf", "application/pdf")
    assert content(out).startswith(b"%PDF-")
    assert sizes(out) == [A4]


def test_by_its_number_too(issuer):
    invoice = manual()

    assert run("invoice.invoice.pdf", {"number": invoice.number}).filename == f"{invoice.number}.pdf"


@pytest.mark.parametrize(
    ("format", "called"),
    [
        ("FACT/{year}/{seq:04d}", "FACT-2026-0001.pdf"),
        ("../{prefix} {year}:{seq:03d}", "X 2026-001.pdf"),
        ('<{year}>"{seq:03d}"|?*', "2026-001.pdf"),
        ("{year}\\{seq}.", "2026-1.pdf"),
    ],
)
def test_its_name_is_one_every_computer_takes(issuer, at, format, called):
    at(NOON)
    data = {"code": "ODD", "prefix": "X", "invoice_type": "F1", "year": 2026, "format": format}
    run("invoice.series.create", data)

    assert downloaded(manual(series_code="ODD")).filename == called


@pytest.mark.parametrize(("language_", "called"), [("en", "Invoice"), ("es", "Factura")])
def test_it_says_its_title_and_its_language_to_whoever_reads_it_aloud(issuer, language_, called):
    invoice = manual()

    out = downloaded(invoice, ctx_for(language=language_))

    assert (title(out), language(out)) == (f"{called} {invoice.number}", language_)


def test_every_sign_of_spanish_and_english_can_be_read_and_travels_in_the_file(issuer):
    signs = "ñÑ çÇ áéíóú ÁÉÍÓÚ üÜ ¿¡ €£ – — « » “ ” ‘ ’ … ª º · ½ ©"
    invoice = manual(lines=[{**LINE, "description": signs}], customer_name="Muñoz & Peña — «Reformas»")

    out = downloaded(invoice, ctx_for(language="es"))

    assert signs in on_paper(out) and "Muñoz & Peña — «Reformas»" in on_paper(out)
    assert fonts_not_embedded(out) == 0


def test_a_long_invoice_repeats_its_headers_and_ends_with_its_totals(issuer):
    invoice = manual(lines=[{**HUNDRED, "description": f"Service {n}"} for n in range(1, 101)])

    out = downloaded(invoice)

    pages = [page.get_textpage().get_text_bounded() for page in opened(out)]
    assert len(pages) > 2 and set(sizes(out)) == {A4}
    assert [n for n, said in enumerate(pages) if "DESCRIPTION" not in said] == []
    assert [n for n, said in enumerate(pages) if "TOTAL" in said] == [len(pages) - 1]
    assert [f"Service {n}" for n in range(1, 101) if f"Service {n}" not in "".join(pages)] == []
    assert "€12,100.00" in pages[-1]


@pytest.mark.parametrize("language_", ["en", "es"])
def test_nothing_goes_past_its_margins_whatever_the_number_and_the_dates(issuer, at, language_):
    at(NOON)
    data = {"code": "LONG", "prefix": "SERIE-DE-FACTURAS-X", "invoice_type": "F1", "year": 2026}
    run("invoice.series.create", {**data, "format": "{prefix}/{year}/{seq:09d}/ABCDEFGHIJKL"})

    for invoice in (manual(due_date="2026-12-24"), manual(series_code="LONG", due_date="2026-12-24")):
        out = downloaded(invoice, ctx_for(language=language_))
        assert out_of_the_margins(out) == [], invoice.number
        assert invoice.number in "".join(on_paper(out).split())


@pytest.mark.parametrize("where", ["customer_name", "customer_address", "notes", "description"])
def test_a_word_longer_than_the_paper_goes_on_in_the_next_line(issuer, where):
    endless = "W" * 120
    invoice = manual(lines=[{**LINE, "description": endless}]) if where == "description" else manual(**{where: endless})

    out = downloaded(invoice)

    assert out_of_the_margins(out) == []
    assert endless in "".join(on_paper(out).split())


def test_it_is_marked_as_a_copy_only_when_it_is_asked_for_as_one(issuer):
    invoice = manual()

    assert "COPY" not in on_paper(downloaded(invoice))
    assert "COPY" in on_paper(downloaded(invoice, duplicate=True))


# The language


def test_it_is_in_the_invoices_own_language_before_the_readers(issuer):
    """The invoice erplora.com issued keeps its payer's language."""
    invoice = manual()
    Invoice.objects.filter(pk=invoice.id).update(language="en")

    out = downloaded(invoice, ctx_for(language="es"))

    assert (language(out), title(out)) == ("en", f"Invoice {invoice.number}")
    assert words(text(out)) == words_of_page(page(invoice, "en")) + LEGEND


def test_the_readers_language_is_not_the_one_of_the_request_before(issuer):
    invoice = manual()

    with translation.override("es"):
        out = downloaded(invoice, ctx_for(language="en"))

    assert language(out) == "en"


# The QR


def test_an_invoice_without_a_record_says_what_its_a4_says_without_a_qr(issuer, monkeypatch):
    def absent(name):
        raise UnknownOperation(name)

    with monkeypatch.context() as without:
        without.setattr(issuing, "get_operation", absent)
        invoice = manual()
    assert not Record.objects.exists()

    out = downloaded(invoice)

    assert (words(text(out)), qr_urls(out)) == (words_of_page(page(invoice)), [])


def test_with_verifactu_off_it_has_no_qr_as_the_a4(issuer, monkeypatch):
    invoice = manual()

    def off(ctx, data):
        raise AppInactive("VeriFactu is off.")

    monkeypatch.setitem(registry, BY_INVOICE, dataclasses.replace(registry[BY_INVOICE], fn=off))

    assert qr_urls(downloaded(invoice)) == []


def test_without_verifactu_in_the_server_it_has_no_qr(issuer, monkeypatch):
    invoice = manual()
    monkeypatch.delitem(registry, BY_INVOICE)

    assert qr_urls(downloaded(invoice)) == []


def test_a_record_that_cannot_be_read_makes_no_pdf(issuer, monkeypatch):
    """Never an invoice without its QR."""
    invoice = manual()

    def unreadable(ctx, data):
        raise NotFound("Not now.", code="verifactu.not_now")

    monkeypatch.setitem(registry, BY_INVOICE, dataclasses.replace(registry[BY_INVOICE], fn=unreadable))

    with pytest.raises(Conflict) as refused:
        downloaded(invoice)
    assert refused.value.code == "invoice.record_unreadable"


def test_whoever_sees_the_invoice_gets_it_with_its_qr_without_verifactus_own_permission(issuer):
    invoice = manual()
    admin = ctx_for()
    person = dataclasses.replace(admin, permissions=admin.permissions - {"verifactu.view_record"})

    assert qr_urls(downloaded(invoice, person)) == [record_url(invoice)]


# What people write is never markup


INJECTED = '<b>Ana</b> & <img src="http://169.254.169.254/x.png"> {{ 7|add:7 }} &lt;i&gt; <!-- gone -->'


@pytest.mark.parametrize("where", ["customer_name", "customer_address", "notes"])
def test_what_is_written_of_a_customer_is_printed_as_it_was_written(issuer, where):
    invoice = manual(**{where: INJECTED})

    assert INJECTED in on_paper(downloaded(invoice))


def test_what_is_written_on_a_line_is_printed_as_it_was_written(issuer):
    invoice = manual(lines=[{**LINE, "description": INJECTED}])

    # A line's column is narrow: a long word of it goes on in the next line of the paper.
    assert "".join(INJECTED.split()) in "".join(on_paper(downloaded(invoice)).split())


def test_what_the_business_calls_itself_is_printed_as_it_was_written(issuer):
    run("invoice.issuer.update", {**ISSUER, "legal_name": "<i>Ana</i> & Co SL"})

    assert "<i>Ana</i> & Co SL" in on_paper(downloaded(manual()))


def test_nothing_is_asked_of_the_network(issuer, monkeypatch):
    asked = []
    fetcher = pdf.page_fetcher

    def noted():
        made = fetcher()
        fetch = made.fetch

        def spied(url, *args, **kwargs):
            asked.append(url.partition(":")[0])
            return fetch(url, *args, **kwargs)

        made.fetch = spied
        return made

    monkeypatch.setattr(pdf, "page_fetcher", noted)
    downloaded(manual(notes=INJECTED))

    assert set(asked) <= {"data"}


# Who gets it, and what cannot be done


def test_the_accountancy_firm_downloads_it(issuer):
    invoice = manual()

    assert downloaded(invoice, ctx_for("hub_accountant")).filename == f"{invoice.number}.pdf"


def test_an_employee_downloads_theirs_and_never_someone_elses(issuer, make_user):
    ana = dataclasses.replace(ctx_for("hub_employee"), actor=make_user("ana", role="hub_employee"))
    theirs, other = manual(ana), manual()

    assert downloaded(theirs, ana).filename == f"{theirs.number}.pdf"
    with pytest.raises(NotFound) as refused:
        downloaded(other, ana)
    assert refused.value.code == "invoice.not_found"


def test_without_permission_to_see_invoices_there_is_no_pdf(issuer):
    invoice = manual()
    admin = ctx_for()

    with pytest.raises(PermissionDenied):
        downloaded(invoice, dataclasses.replace(admin, permissions=admin.permissions - {"invoice.view_invoice"}))


def test_the_invoice_of_another_business_does_not_exist(issuer, hub_b):
    invoice = manual()

    with use_hub(hub_b), pytest.raises(NotFound):
        downloaded(invoice, ctx_for(scope=B))


def test_without_the_libraries_that_print_it_says_so(issuer, monkeypatch):
    invoice = manual()

    def missing():
        raise OSError("cannot load library 'libpango-1.0-0'")

    monkeypatch.setattr(pdf, "_weasyprint", missing)

    with pytest.raises(OperationError) as refused:
        downloaded(invoice)
    assert (refused.value.status, refused.value.code) == (503, "invoice.pdf_unavailable")


@pytest.mark.parametrize("language_", ["en", "es"])
def test_why_there_is_no_pdf_is_said_in_the_readers_language(issuer, monkeypatch, language_):
    invoice = manual()

    def missing():
        raise OSError("cannot load library 'libpango-1.0-0'")

    monkeypatch.setattr(pdf, "_weasyprint", missing)

    with translation.override("en" if language_ == "es" else "es"), pytest.raises(OperationError) as refused:
        downloaded(invoice, ctx_for(language=language_))
    with translation.override(language_):
        assert str(refused.value) == translation.gettext("The PDF cannot be made right now. Try again later.")


def test_it_changes_nothing_of_the_invoice(issuer):
    invoice = manual()
    before = Invoice.objects.values().get(pk=invoice.id)

    downloaded(invoice)

    assert Invoice.objects.values().get(pk=invoice.id) == before


def test_whoever_sends_it_prints_the_same_file(issuer):
    """What attaches the invoice to an e-mail calls the function the download calls."""
    invoice = manual()
    sent = dataclasses.replace(system_context(A), language="es")

    out = SimpleNamespace(content_base64=base64.b64encode(printed(sent, stored(invoice))))

    downloaded_by_a_person = downloaded(invoice, ctx_for(language="es"))
    assert text(out) == text(downloaded_by_a_person)
    assert qr_urls(out) == qr_urls(downloaded_by_a_person) == [record_url(invoice)]


def test_the_page_it_is_printed_from_is_the_a4_itself(issuer, monkeypatch):
    invoice = manual()
    pages = []
    render = pdf.render_pdf

    def spied(html):
        pages.append(html)
        return render(html)

    monkeypatch.setattr(pdf, "render_pdf", spied)
    downloaded(invoice)

    record = run(BY_INVOICE, {"invoice_id": str(invoice.id)}).record
    assert pages == [render_document(stored(invoice), qr={"url": record.qr_url, "svg": record.qr_svg})]


def test_the_dates_are_the_invoices(issuer, at):
    at(NOON)
    invoice = manual(due_date="2026-12-24", issue_date=dt.date(2026, 11, 20).isoformat())

    paper = on_paper(downloaded(invoice, ctx_for(language="es")))

    assert "20/11/2026" in paper and "24/12/2026" in paper
