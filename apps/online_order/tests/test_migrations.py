"""Online orders' migrations go both ways: 0001 makes the table of the tables' codes, 0002 the tables of the orders a
table sends and their lines, and going back drops them.

They run on a business's own database, cloned from the template for the test, through the migrator's alias as
``migrate_hubs`` runs them.
"""

from django.db.migrations.executor import MigrationExecutor

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

TABLE = "online_order_tablecode"


def tables(database) -> set[str]:
    with database.cursor() as cursor:
        return set(database.introspection.table_names(cursor))


def test_0001_goes_back_and_forth(database):
    assert TABLE in tables(database)
    # None of the app's migrations: the shared ``migrate`` reads the models at its targets, and there are none.
    MigrationExecutor(database).migrate([("online_order", None)])
    assert TABLE not in tables(database)
    migrate(database, [("online_order", "0001_initial")])
    assert TABLE in tables(database)
    with database.cursor() as cursor:
        constraints = database.introspection.get_constraints(cursor, TABLE)
    unique = {tuple(found["columns"]) for found in constraints.values() if found["unique"] and not found["primary_key"]}
    assert {("table_id",), ("code",)} <= unique


ORDERS = {"online_order_order", "online_order_orderline"}


def test_0002_goes_back_and_forth(database):
    assert ORDERS <= tables(database)
    migrate(database, [("online_order", "0001_initial")])
    assert not ORDERS & tables(database)
    assert TABLE in tables(database)
    migrate(database, [("online_order", "0002_order")])
    assert ORDERS <= tables(database)
