"""The Excel of the issued invoices (INVOICE-F24): a spreadsheet opened for real, with one row per invoice and tax rate,
its figures as numbers, that adds up to what the list shows for the same search and filters.
"""

import base64
import datetime as dt
import io
import json
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from live.errors import PermissionDenied
from openpyxl import load_workbook

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import HUB_DB, ISSUER, ctx_for, run
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, B

pytestmark = HUB_DB

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
}
HEADERS = ["Number", "Date", "Customer", "Tax ID", "Taxable base", "Rate %", "Tax", "Total"]


def line(price=1000, rate="21", **more):
    return {"description": "Service", "quantity": "1", "unit_price": price, "tax_rate": rate, **more}


def manual(*lines, **more):
    return run("invoice.invoice.create", {"lines": list(lines) or [line()], **RECIPIENT, **more})


def export(ctx=None, **filters):
    return run("invoice.invoice.export", filters, ctx)


def opened(out):
    """The file's only sheet, opened as a spreadsheet program does: its headers and its rows as cells."""
    book = load_workbook(io.BytesIO(base64.b64decode(out.content_base64)))
    assert len(book.sheetnames) == 1
    headers, *rows = list(book.active.iter_rows())
    return [cell.value for cell in headers], rows


def values(out):
    """The rows of the file by header."""
    headers, rows = opened(out)
    return [dict(zip(headers, [cell.value for cell in row], strict=True)) for row in rows]


def totals(out):
    """``{number: (base, tax, total)}`` in cents: what each invoice's rows add up to in the file."""
    sums: dict[str, list[Decimal]] = {}
    for row in values(out):
        parts = sums.setdefault(row["Number"], [Decimal(0)] * 3)
        base, total = Decimal(str(row["Taxable base"])), Decimal(str(row["Total"]))
        tax = Decimal(str(row["Tax"])) + Decimal(str(row.get("Surcharge") or 0))
        for i, part in enumerate((base, tax, total)):
            parts[i] += part
    return {number: tuple(int(part * 100) for part in parts) for number, parts in sums.items()}


def listed(**filters):
    """``{number: (base, tax, total)}`` of the list: the figures the file must add up to."""
    rows = run("invoice.invoice.list", {"limit": 100, **filters}).rows
    return {row.number: (row.base_amount, row.tax_amount, row.total_amount) for row in rows}


# The file


def test_the_file_is_an_excel_with_a_row_for_each_invoice(issuer):
    invoice = manual()

    out = export()

    assert (out.content_type, out.filename) == (XLSX, "invoices.xlsx")
    assert values(out) == [
        {
            "Number": invoice.number,
            "Date": dt.datetime(timezone.localdate().year, timezone.localdate().month, timezone.localdate().day),
            "Customer": "Talleres Pérez SL",
            "Tax ID": "B12345674",
            "Taxable base": 10,
            "Rate %": 21,
            "Tax": 2.1,
            "Total": 12.1,
        }
    ]


def test_the_figures_are_numbers_the_date_a_date_and_the_tax_id_text(issuer):
    manual()

    headers, [row] = opened(export())

    cells = dict(zip(headers, row, strict=True))
    for header in ("Taxable base", "Rate %", "Tax", "Total"):
        assert cells[header].data_type == "n", header
        assert isinstance(cells[header].value, (int, float)), header
    assert cells["Date"].is_date
    for header in ("Number", "Customer", "Tax ID"):
        assert cells[header].data_type == "s", header


def test_a_customer_s_name_is_never_read_as_a_formula(issuer):
    manual(customer_name="=HYPERLINK(\"http://evil.example\")")

    _headers, [row] = opened(export())

    assert row[2].data_type == "s"
    assert row[2].value == "=HYPERLINK(\"http://evil.example\")"


def test_an_invoice_without_a_customer_leaves_its_cells_empty(issuer):
    run("invoice.invoice.create", {"series_code": "TICKET", "lines": [line(150, "10")]})

    [row] = values(export())

    assert (row["Customer"], row["Tax ID"], row["Total"]) == (None, None, 1.65)


# What each invoice adds up to


def test_several_rates_give_a_row_each_and_add_up_to_the_list(issuer):
    invoice = manual(line(1000, "21"), line(2000, "10"), line(500, "4"))

    rows = values(export())

    assert [(r["Number"], r["Rate %"], r["Taxable base"], r["Tax"], r["Total"]) for r in rows] == [
        (invoice.number, 21, 10, 2.1, 12.1),
        (invoice.number, 10, 20, 2, 22),
        (invoice.number, 4, 5, 0.2, 5.2),
    ]
    assert totals(export()) == listed()


def test_a_cent_of_rounding_is_not_lost(issuer):
    invoice = manual(line(333, "21"), line(333, "21"))

    [row] = values(export())

    assert (row["Taxable base"], row["Tax"], row["Total"]) == (6.66, 1.4, 8.06)
    assert totals(export()) == {invoice.number: (666, 140, 806)} == listed()


def test_an_exempt_line_shows_a_zero_rate_and_its_total_is_its_base(issuer):
    manual(line(5000, tax_category_key="service.health"))

    [row] = values(export())

    assert (row["Taxable base"], row["Rate %"], row["Tax"], row["Total"]) == (50, 0, 0, 50)


def test_the_equivalence_surcharge_has_its_own_columns_only_in_a_file_that_has_one(
    issuer, charge, product, equivalence_surcharge
):
    manual()
    assert opened(export())[0] == HEADERS
    product()
    charge("inv-sale-2345")

    headers, rows = opened(export())

    assert headers == [*HEADERS[:7], "Surcharge rate %", "Surcharge", "Total"]
    by_rate = {row[5].value: dict(zip(headers, [cell.value for cell in row], strict=True)) for row in rows}
    surcharged = by_rate[21]
    assert surcharged["Surcharge rate %"] == 5.2
    assert surcharged["Total"] == pytest.approx(surcharged["Taxable base"] + surcharged["Tax"] + surcharged["Surcharge"])
    # The invoice without a surcharge leaves its cells empty.
    plain = [r for r in values(export()) if r["Number"].startswith("FACT")]
    assert [(r["Surcharge rate %"], r["Surcharge"]) for r in plain] == [(None, None)]
    assert totals(export()) == listed()


# What the list counts


def test_a_rectifying_invoice_is_negative_and_the_cancelled_original_still_counts_as_in_the_list(issuer):
    original = manual(line(1000, "21"), line(2000, "10"))
    rectifying = run("invoice.invoice.rectify", {"number": original.number, "reason": "x"}).invoice

    out = export()

    assert totals(out) == listed() != {}
    assert set(totals(out)) == {original.number, rectifying.number}
    assert totals(out)[rectifying.number][2] == -3410 == -totals(out)[original.number][2]
    assert Invoice.objects.get(number=original.number).status == Invoice.Status.CANCELLED


def test_the_rows_go_in_the_order_of_their_date_and_number(issuer):
    first, second = manual(), manual()

    assert [row["Number"] for row in values(export())] == [first.number, second.number]


def test_the_file_takes_the_list_s_search_and_filters(issuer):
    wanted = manual(customer_name="Bar Pepe", customer_tax_id="12345678Z")
    manual(line(90000))
    run("invoice.invoice.create", {"series_code": "TICKET", "lines": [line(150, "10")]})

    assert [row["Number"] for row in values(export(search="pepe"))] == [wanted.number]
    assert list(totals(export(invoice_type="F2"))) == list(listed(invoice_type="F2"))
    assert totals(export(total_amount_from=50000)) == listed(total_amount_from=50000)
    assert totals(export(status="cancelled")) == {} == listed(status="cancelled")
    assert totals(export(series_code="FACT")) == listed(series_code="FACT")


# The period


def test_the_period_is_the_issue_date_of_the_business_s_clock(issuer, monkeypatch, in_business_a):
    # 23:30 of 31 October in the Canary Islands is 00:30 of 1 November in Madrid: the invoice belongs to October.
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.UTC))
    november = manual()
    # In another series: the days of a series go in the order of its numbers.
    run("invoice.series.create", {"code": "SHOP", "invoice_type": "F1", "year": 2026})
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 10, 31, 23, 30, tzinfo=dt.UTC))
    monkeypatch.setattr(in_business_a, "timezone", "Atlantic/Canary")
    october = manual(series_code="SHOP")

    assert [r["Number"] for r in values(export(issue_date_from="2026-10-01", issue_date_to="2026-10-31"))] == [
        october.number
    ]
    assert [r["Number"] for r in values(export(issue_date_from="2026-11-01", issue_date_to="2026-11-30"))] == [
        november.number
    ]
    # The older day first, whatever the order they were issued in.
    assert [r["Number"] for r in values(export())] == [october.number, november.number]


@pytest.mark.parametrize(
    ("dates", "name"),
    [
        ({"issue_date_from": "2026-10-01", "issue_date_to": "2026-10-31"}, "invoices-2026-10.xlsx"),
        ({"issue_date_from": "2026-10-05", "issue_date_to": "2026-10-12"}, "invoices-2026-10-05_2026-10-12.xlsx"),
        ({"issue_date_from": "2026-10-05", "issue_date_to": "2026-10-31"}, "invoices-2026-10-05_2026-10-31.xlsx"),
        ({"issue_date_from": "2026-10-05"}, "invoices.xlsx"),
    ],
)
def test_the_file_is_named_after_the_period(issuer, dates, name):
    assert export(**dates).filename == name


def test_an_empty_period_is_a_file_with_only_its_headers(issuer):
    out = export(issue_date_from="2020-01-01", issue_date_to="2020-01-31")

    assert opened(out) == (HEADERS, [])
    assert out.invoices == 0


def test_it_says_how_many_invoices_the_file_holds(issuer):
    manual(line(1000, "21"), line(2000, "10"))
    manual()

    assert export().invoices == 2


# Who downloads it


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_accountant"])
def test_whoever_sees_every_invoice_downloads_the_file(issuer, role):
    invoice = manual()

    assert [row["Number"] for row in values(export(ctx_for(role)))] == [invoice.number]


def test_an_employee_is_refused(issuer):
    manual()
    with pytest.raises(PermissionDenied):
        export(ctx_for("hub_employee"))


def test_the_route_refuses_an_employee_and_serves_the_accountant(issuer, make_user):
    manual()
    employee, accountant = Client(), Client()
    employee.force_login(make_user("ana", role="hub_employee"))
    accountant.force_login(make_user("gema", role="hub_accountant"))

    refused = employee.get("/api/invoice/invoices/export", HTTP_HOST=HOST)
    served = accountant.get("/api/invoice/invoices/export", HTTP_HOST=HOST)

    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")
    assert served.status_code == 200, served.content
    assert served.json()["content_type"] == XLSX
    assert load_workbook(io.BytesIO(base64.b64decode(served.json()["content_base64"])))


# Two businesses


def test_a_business_s_file_holds_only_its_own_invoices(issuer, hub_b):
    ours = manual()
    with use_hub(hub_b):
        run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
        theirs = run("invoice.invoice.create", {"lines": [line(7700)], **RECIPIENT}, ctx_for(scope=B))

    assert [row["Number"] for row in values(export())] == [ours.number]
    with use_hub(hub_b):
        assert [row["Number"] for row in values(export(ctx_for(scope=B)))] == [theirs.number]


# The words


def test_the_money_goes_in_the_units_of_its_currency(issuer):
    manual(line(1000, "21"))
    Invoice.objects.update(currency="JPY")

    [row] = values(export())

    assert (row["Taxable base"], row["Tax"], row["Total"]) == (1000, 210, 1210)


def test_the_headers_and_the_file_name_are_in_the_person_s_language(issuer):
    manual()

    out = export(ctx_for(language="es"))

    assert out.filename == "facturas.xlsx"
    assert opened(out)[0] == ["Número", "Fecha", "Cliente", "NIF", "Base imponible", "Tipo %", "Cuota", "Total"]


# The assistant


def test_the_file_is_handed_to_the_person_and_never_to_the_model(issuer):
    from live import assistant as shared
    from live.operations import get

    manual()
    ctx = ctx_for(language="es")
    call = {"call_id": "c1", "name": shared.tool_name("invoice.invoice.export"), "arguments": "{}"}
    function = {"name": call["name"], "arguments": call["arguments"]}
    asking = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": function}]}
    messages = [{"role": "user", "content": "Descárgame las facturas en Excel"}, asking]
    op = get("base.assistant.turn")

    plan = op(ctx, op.input.model_validate({"messages": messages, "pending": [call]})).model_dump(mode="json")

    [ran] = plan["executed"]
    assert (ran["file"]["filename"], ran["file"]["content_type"]) == ("facturas.xlsx", XLSX)
    assert load_workbook(io.BytesIO(base64.b64decode(ran["file"]["content"])))
    told = json.loads(plan["append"][0]["content"])
    assert "content_base64" not in told
    assert ran["file"]["content"] not in json.dumps(plan["messages"])
