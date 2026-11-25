"""Migration 0010 of the invoice app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, an issued invoice keeps every figure and takes emails, and the code
of before still issues; back, the log goes and the invoices stay."""

from apps.invoice.tests.test_migrations_due_date import issue, kept
from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "invoice"
BEFORE = [(APP, "0009_withholding")]
AFTER = [(APP, "0010_invoice_email")]
TABLE = "invoice_invoiceemail"


def there(database) -> bool:
    with database.cursor() as cursor:
        return TABLE in database.introspection.table_names(cursor)


def test_the_log_of_emails_comes_with_0010_and_goes_with_its_reverse(database):
    old = migrate(database, BEFORE)
    issue(old, database, 1)
    assert not there(database)

    new = migrate(database, AFTER)
    assert {"to_address", "status", "sent_at", "attempt_key"} <= columns(database, TABLE)
    # The deploy migrates first: the code of before issues beside the new table until it is replaced.
    issue(old, database, 2)
    issued = issue(new, database, 3)
    emails = new.get_model(APP, "InvoiceEmail").objects.using(database.alias)
    emails.create(invoice_id=issued.pk, to_address="ana@example.com")
    emails.create(invoice_id=issued.pk, to_address="ana@example.com")
    assert list(emails.values_list("status", flat=True)) == ["queued", "queued"]
    expected = kept(new, database)
    assert [number for number, *_figures in expected] == [f"FACT-2026-00000{n}" for n in (1, 2, 3)]

    back = migrate(database, BEFORE)
    assert not there(database)
    assert kept(back, database) == expected
