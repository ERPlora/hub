"""Migration 0022 of the sale app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, every tender has nothing added and keeps its change; the
database refuses a change that does not take what is added out. Back, the two columns go and a tender with something
added keeps the sale's part alone: what was handed over loses what was added, on the tender and on its sale."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction

from apps.sale.tests.test_migrations_bill_printed_at import APP
from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

BEFORE = [(APP, "0021_order_staff")]
AFTER = [(APP, "0022_salepayment_extra")]
TABLE = "sale_salepayment"
ADDED = {"extra", "extra_label"}


def tender(state, database, sequence: int, *, tendered: int, change: int, **added):
    """A cash tender of 45.00 € on a sale of its own, as a charge of that schema stores it."""
    alias = database.alias
    sale = state.get_model(APP, "Sale").objects.using(alias).create(
        number=f"20261122-{sequence:04d}",
        business_day=dt.date(2026, 11, 22),
        sequence=sequence,
        document_type="ticket",
        currency="EUR",
        total=4500,
        tendered_total=tendered,
        change_total=change,
        idempotency_key=f"migration-0022-{sequence}",
    )
    cash = state.get_model(APP, "PaymentMethod").objects.using(alias).get(type="cash", is_system=True)
    return state.get_model(APP, "SalePayment").objects.using(alias).create(
        sale=sale,
        position=1,
        method=cash,
        method_name="Cash",
        method_type="cash",
        amount=4500,
        tendered=tendered,
        change=change,
        **added,
    )


def tenders(state, database) -> list[tuple]:
    rows = state.get_model(APP, "SalePayment").objects.using(database.alias).order_by("sale__sequence")
    return [(row.amount, row.tendered, row.change, row.sale.tendered_total) for row in rows]


def test_what_is_added_comes_with_0022_and_its_reverse_leaves_the_sales_part_alone(database):
    old = migrate(database, BEFORE)
    tender(old, database, 1, tendered=5000, change=500)
    assert ADDED.isdisjoint(columns(database, TABLE))

    new = migrate(database, AFTER)
    assert ADDED <= columns(database, TABLE)
    [kept] = new.get_model(APP, "SalePayment").objects.using(database.alias).all()
    assert (kept.extra, kept.extra_label, kept.change) == (0, "", 500)
    # 50.00 € handed over for 45.00 € and 5.00 € of tip: no change.
    tender(new, database, 2, tendered=5000, change=0, extra=500, extra_label="Tip")
    with pytest.raises(IntegrityError), transaction.atomic(using=database.alias):
        tender(new, database, 3, tendered=5000, change=500, extra=500, extra_label="Tip")

    back = migrate(database, BEFORE)
    assert ADDED.isdisjoint(columns(database, TABLE))
    assert tenders(back, database) == [(4500, 5000, 500, 5000), (4500, 4500, 0, 4500)]
