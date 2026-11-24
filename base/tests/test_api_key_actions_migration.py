"""An API key's permissions move from four modes to read, create, update and delete (``base/0027``).

``full`` becomes every action on every app; ``read``, reading every app; ``write``, creating, updating and deleting on
every app; per app, ``read`` and ``write`` the same way app by app. What a key could do is what it can do. The mode
leaves the model but stays in the database, empty for the keys made after, for the code of before that still runs while
the deploy migrates. Going back gives every key a mode again and never more than it could do. These run on a business's
own database, cloned from the template for each test, through the migrator's alias as ``migrate_hubs`` runs them.
"""

import hashlib
import uuid

import pytest
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.tests import hubs

BEFORE = [("base", "0026_api_key_owner")]
AFTER = [("base", "0027_api_key_actions")]
EVERYTHING = ["read", "create", "update", "delete"]
WRITING = ["create", "update", "delete"]


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
    executor = MigrationExecutor(database)
    executor.loader.build_graph()
    executor.migrate(targets)
    return MigrationExecutor(database).loader.project_state(targets).apps


def key(models, alias: str, name: str, **fields):
    return models.get_model("base", "ApiKey").objects.using(alias).create(
        name=name, prefix="erpk_live_x", token_digest=hashlib.sha256(name.encode()).hexdigest(), **fields
    )


def scopes_by_name(models, alias: str) -> dict:
    return dict(models.get_model("base", "ApiKey").objects.using(alias).values_list("name", "scopes"))


def test_each_mode_becomes_what_it_let_a_key_do(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    key(old, alias, "Full", mode="full", scopes={})
    key(old, alias, "Read", mode="read", scopes={})
    key(old, alias, "Write", mode="write", scopes={})
    key(old, alias, "Shop", mode="per_app", scopes={"cart_checkout": ["read", "write"], "tax": ["read"]})
    key(old, alias, "Orders", mode="per_app", scopes={"sale": ["write"], "tax": []})

    new = migrate(database, AFTER)
    assert scopes_by_name(new, alias) == {
        "Full": {"*": EVERYTHING},
        "Read": {"*": ["read"]},
        "Write": {"*": WRITING},
        "Shop": {"cart_checkout": EVERYTHING, "tax": ["read"]},
        "Orders": {"sale": WRITING},
    }


def test_the_mode_leaves_the_model_and_stays_empty_in_the_database_for_new_keys(database):
    alias = database.alias
    new = migrate(database, AFTER)
    assert "mode" not in {field.name for field in new.get_model("base", "ApiKey")._meta.get_fields()}
    made = key(new, alias, "New", scopes={"tax": ["read"]})
    with database.cursor() as cursor:
        cursor.execute("SELECT mode FROM base_apikey WHERE id = %s", [made.id])
        assert cursor.fetchone() == (None,)


def test_going_back_gives_every_key_a_mode_and_never_more_than_it_could_do(database):
    alias = database.alias
    new = migrate(database, AFTER)
    key(new, alias, "Full", scopes={"*": EVERYTHING})
    key(new, alias, "Read", scopes={"*": ["read"]})
    key(new, alias, "Write", scopes={"*": WRITING})
    key(new, alias, "Reads and adds", scopes={"*": ["read", "create"]})
    key(new, alias, "Adds", scopes={"*": ["create"]})
    key(new, alias, "Shop", scopes={"cart_checkout": EVERYTHING, "tax": ["read", "update"], "sale": ["delete"]})

    old = migrate(database, BEFORE)
    kept = {row.name: (row.mode, row.scopes) for row in old.get_model("base", "ApiKey").objects.using(alias).all()}
    assert kept == {
        "Full": ("full", {}),
        "Read": ("read", {}),
        "Write": ("write", {}),
        "Reads and adds": ("read", {}),
        "Adds": ("per_app", {}),
        "Shop": ("per_app", {"cart_checkout": ["read", "write"], "tax": ["read"]}),
    }
