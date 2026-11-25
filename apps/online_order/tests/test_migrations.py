"""Online orders' migrations go both ways: 0001 makes the table of the tables' codes and going back drops it.

They run on a business's own database, cloned from the template for the test, through the migrator's alias as
``migrate_hubs`` runs them.
"""

import uuid

import pytest
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.tests import hubs

TABLE = "online_order_tablecode"


@pytest.fixture
def database(hub_databases, django_db_blocker):
    """The migrator's connection to a business's database cloned from the template for the test, dropped after it."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        database = connections[tenancy_connections.register_ddl_alias(name)]
        try:
            yield database
        finally:
            database.close()


def migrate(database, targets) -> None:
    executor = MigrationExecutor(database)
    executor.loader.build_graph()
    executor.migrate(targets)


def tables(database) -> set[str]:
    with database.cursor() as cursor:
        return set(database.introspection.table_names(cursor))


def test_0001_goes_back_and_forth(database):
    assert TABLE in tables(database)
    migrate(database, [("online_order", None)])
    assert TABLE not in tables(database)
    migrate(database, [("online_order", "0001_initial")])
    assert TABLE in tables(database)
    with database.cursor() as cursor:
        constraints = database.introspection.get_constraints(cursor, TABLE)
    unique = {tuple(found["columns"]) for found in constraints.values() if found["unique"] and not found["primary_key"]}
    assert {("table_id",), ("code",)} <= unique
