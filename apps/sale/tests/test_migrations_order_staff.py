"""Migration 0021 of the sale app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, every open check is served by «me» (nobody named); back, the
columns go and the checks stay."""

from apps.sale.tests.test_migrations_bill_printed_at import APP, TABLE, labels
from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

BEFORE = [(APP, "0020_order_bill_printed_at")]
AFTER = [(APP, "0021_order_staff")]


def test_who_serves_the_check_comes_with_0021_and_goes_with_its_reverse(database):
    old = migrate(database, BEFORE)
    old.get_model(APP, "Order").objects.using(database.alias).create(label="Table 6")
    assert {"staff_id", "staff_name"}.isdisjoint(columns(database, TABLE))

    new = migrate(database, AFTER)
    [check] = new.get_model(APP, "Order").objects.using(database.alias).all()
    assert {"staff_id", "staff_name"} <= set(columns(database, TABLE))
    assert (check.staff_id, check.staff_name) == (None, "")

    back = migrate(database, BEFORE)
    assert {"staff_id", "staff_name"}.isdisjoint(columns(database, TABLE))
    assert labels(back, database) == ["Table 6"]
