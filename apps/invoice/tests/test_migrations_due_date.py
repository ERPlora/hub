"""Migration 0008 of the invoice app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, an issued invoice keeps every figure and has no due date, and the
code of before still issues on the new table; back, the column goes and the invoices stay."""

import datetime as dt

from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "invoice"
BEFORE = [(APP, "0007_issuer_intra_eu_operator")]
AFTER = [(APP, "0008_due_date")]
DAY = dt.date(2026, 11, 24)


def issue(state, database, sequence: int):
    series, _created = state.get_model(APP, "InvoiceSeries").objects.using(database.alias).get_or_create(
        code="FACT", year=2026, defaults={"invoice_type": "F1"}
    )
    return state.get_model(APP, "Invoice").objects.using(database.alias).create(
        invoice_type="F1",
        series_id=series.pk,
        series_code="FACT",
        year=2026,
        sequence=sequence,
        number=f"FACT-2026-{sequence:06d}",
        issue_date=DAY,
        operation_date=DAY,
        issuer_name="Peluquería Ana SL",
        issuer_tax_id="B12345674",
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
        currency="EUR",
    )


def kept(state, database) -> list[tuple]:
    invoices = state.get_model(APP, "Invoice").objects.using(database.alias).order_by("sequence")
    return list(invoices.values_list("number", "issue_date", "operation_date", "total_amount"))


def test_the_due_date_comes_with_0008_and_goes_with_its_reverse(database):
    old = migrate(database, BEFORE)
    issue(old, database, 1)
    assert "due_date" not in columns(database, "invoice_invoice")

    new = migrate(database, AFTER)
    first = new.get_model(APP, "Invoice").objects.using(database.alias).get(sequence=1)
    assert first.due_date is None
    # The deploy migrates first: the code of before issues on the new table until it is replaced.
    issue(old, database, 2)
    expected = [(f"FACT-2026-00000{n}", DAY, DAY, 1210) for n in (1, 2)]
    assert kept(new, database) == expected

    back = migrate(database, BEFORE)
    assert "due_date" not in columns(database, "invoice_invoice")
    assert kept(back, database) == expected
