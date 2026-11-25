"""A migration run on a business's own database, cloned from the template for the test, through the migrator's alias as
``migrate_hubs`` runs it."""

import uuid

import pytest
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.tests import hubs


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


def migrate(database, targets):
    """``database`` at ``targets``, and its models there."""
    executor = MigrationExecutor(database)
    executor.loader.build_graph()
    executor.migrate(targets)
    return MigrationExecutor(database).loader.project_state(targets).apps
