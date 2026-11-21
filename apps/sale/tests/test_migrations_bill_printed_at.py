"""Migration 0020 of the sale app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, every open check has its bill unprinted; back, the column goes
and the checks stay."""

from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "sale"
BEFORE = [(APP, "0019_orderline_allergy")]
AFTER = [(APP, "0020_order_bill_printed_at")]
TABLE = "sale_order"


def labels(state, database) -> list[str]:
    return list(state.get_model(APP, "Order").objects.using(database.alias).values_list("label", flat=True))


def test_the_bill_printed_at_comes_with_0020_and_goes_with_its_reverse(database):
    old = migrate(database, BEFORE)
    old.get_model(APP, "Order").objects.using(database.alias).create(label="Table 4")
    assert "bill_printed_at" not in columns(database, TABLE)

    new = migrate(database, AFTER)
    [check] = new.get_model(APP, "Order").objects.using(database.alias).all()
    assert ("bill_printed_at" in columns(database, TABLE), check.bill_printed_at) == (True, None)

    back = migrate(database, BEFORE)
    assert "bill_printed_at" not in columns(database, TABLE)
    assert labels(back, database) == ["Table 4"]
