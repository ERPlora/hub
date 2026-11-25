"""Migration 0009 of the invoice app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, an issued invoice keeps every figure and withholds nothing, and the
code of before still issues on the new table; back, the columns go and the invoices stay."""

from decimal import Decimal

from apps.invoice.tests.test_migrations_due_date import issue, kept
from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "invoice"
BEFORE = [(APP, "0008_due_date")]
AFTER = [(APP, "0009_withholding")]
TABLE = "invoice_invoice"
ADDED = {"withholding_rate", "withholding_amount"}


def test_the_withholding_comes_with_0009_and_goes_with_its_reverse(database):
    old = migrate(database, BEFORE)
    issue(old, database, 1)
    assert not ADDED & columns(database, TABLE)

    new = migrate(database, AFTER)
    invoices = new.get_model(APP, "Invoice").objects.using(database.alias)
    assert ADDED <= columns(database, TABLE)
    # The deploy migrates first: the code of before issues on the new table until it is replaced.
    issue(old, database, 2)
    assert list(invoices.order_by("sequence").values_list("withholding_rate", "withholding_amount")) == [(None, 0)] * 2
    issued = issue(new, database, 3)
    invoices.filter(pk=issued.pk).update(withholding_rate=Decimal("15"), withholding_amount=150)
    expected = kept(new, database)
    assert [number for number, *_figures in expected] == [f"FACT-2026-00000{n}" for n in (1, 2, 3)]

    back = migrate(database, BEFORE)
    assert not ADDED & columns(database, TABLE)
    assert kept(back, database) == expected
