"""The outbox's partial index of pending events, on every database the Hub has (hub#704).

``live`` declares it (``live/0003``) under the name ``base/0006`` deployed it with. A database that has it keeps that
very index, any other gets it, whichever of the two apps is migrated first, and none ever holds two: the index exists
if and only if ``live/0003`` is applied. Each test makes its databases, as ``test_migrator.py`` does, and looks at them
by the catalog, whatever the index is called.
"""

import io
import uuid

import pytest
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings

from base.tenancy import connections as tenancy_connections
from base.tenancy import migrator, names
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import (  # noqa: F401 (fixtures)
    committed_database,
    make_cluster,
    make_database,
    make_hub,
    new_database,
    template_name,
)

NAME = "base_outbox_pending"
#: As ``base/0006`` made it on every database deployed before ``live`` declared it.
DEPLOYED = f"CREATE INDEX IF NOT EXISTS {NAME} ON live_outboxevent (created_at, id) WHERE delivered_at IS NULL"
#: What PostgreSQL says it made.
DEFINITION = f"CREATE INDEX {NAME} ON public.live_outboxevent USING btree (created_at, id) WHERE (delivered_at IS NULL)"
LIVE_BEFORE = ("live", "0002_outboxevent_verbose_names")
LIVE_DECLARES = ("live", "0003_outbox_pending_index")
BASE_BEFORE = ("base", "0005_demo_code")
PLATFORM = ("base", "live")


def base_leaf() -> tuple[str, str]:
    leaves = dict(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())
    return ("base", leaves["base"])


def migrate_to(db_name: str, *nodes: tuple[str, str]) -> None:
    """Bring the database ``db_name`` to ``nodes``, in that order, and leave no alias registered."""
    alias = tenancy_connections.register_ddl_alias(db_name)
    try:
        for node in nodes:
            MigrationExecutor(connections[alias]).migrate([node])
    finally:
        migrator._forget_alias(alias)


def partial_indexes(db_name: str) -> list[tuple[int, str]]:
    """``(oid, definition)`` of every partial index of the outbox of ``db_name``: the oid tells it was never remade."""
    with hubs._maintenance(db_name) as conn:
        return conn.execute(
            "SELECT indexrelid::oid, pg_get_indexdef(indexrelid) FROM pg_index "
            "WHERE indrelid = 'live_outboxevent'::regclass AND indpred IS NOT NULL"
        ).fetchall()


def definitions(db_name: str) -> list[str]:
    return [definition for _oid, definition in partial_indexes(db_name)]


def as_deployed(db_name: str) -> None:
    """Leave ``db_name`` as the code before ``live`` declared the index did: ``base`` at its leaf, ``live`` at the
    migration before, the index made by ``base``."""
    migrate_to(db_name, base_leaf(), LIVE_BEFORE)
    with hubs._maintenance(db_name) as conn:
        conn.execute(DEPLOYED)


@pytest.fixture
def clone_of(db):
    """``clone_of(source)``: a new hub's database cloned from ``source``, as an alta does; all dropped after."""
    made = []

    def clone(source: str) -> str:
        made.append(names.hub_db_name(tenancy_connections.control_name(), uuid.uuid7()))
        migrator._clone(made[-1], source, migrator.cluster_target(None))
        return made[-1]

    yield clone
    for name in made:
        hubs.drop_database(name)


def test_an_empty_database_gets_it_once(new_database, make_hub):
    applied = migrator.ensure_schema(make_hub(new_database))

    assert "live.0003_outbox_pending_index" in applied
    assert definitions(new_database) == [DEFINITION]


def test_base_alone_does_not_make_it(new_database):
    migrate_to(new_database, base_leaf())

    assert definitions(new_database) == []


def test_live_migrated_before_base_is_no_failure(new_database, make_hub):
    migrate_to(new_database, LIVE_DECLARES)
    assert definitions(new_database) == [DEFINITION]

    migrator.ensure_schema(make_hub(new_database))

    assert definitions(new_database) == [DEFINITION]


def test_a_deployed_database_keeps_the_index_it_has(new_database, make_hub):
    as_deployed(new_database)
    before = partial_indexes(new_database)
    assert [definition for _oid, definition in before] == [DEFINITION]

    applied = migrator.ensure_schema(make_hub(new_database))

    assert "live.0003_outbox_pending_index" in applied
    assert partial_indexes(new_database) == before


def test_a_clone_of_a_template_from_before_keeps_the_one_it_has(template_name, clone_of, make_hub):
    template = template_name()
    hubs.create_database(template)
    as_deployed(template)
    clone = clone_of(template)
    before = partial_indexes(clone)
    assert [definition for _oid, definition in before] == [DEFINITION]

    applied = migrator.ensure_schema(make_hub(clone))

    assert "live.0003_outbox_pending_index" in applied
    assert partial_indexes(clone) == before


def test_a_template_from_before_keeps_the_one_it_has(template_name):
    template = template_name()
    hubs.create_database(template)
    as_deployed(template)
    before = partial_indexes(template)

    migrator.ensure_template(migrator.Template(db_name=template, apps=PLATFORM))

    assert partial_indexes(template) == before


def test_a_clone_of_a_template_up_to_date_has_it_once(template_name, clone_of, make_hub):
    template = template_name()
    hubs.bootstrap_template(template)
    migrator.ensure_template(migrator.Template(db_name=template, apps=PLATFORM))
    clone = clone_of(template)

    applied = migrator.ensure_schema(make_hub(clone))

    assert "live.0003_outbox_pending_index" not in applied
    assert definitions(clone) == [DEFINITION]


def test_going_back_on_base_leaves_it(new_database, make_hub):
    migrator.ensure_schema(make_hub(new_database))

    migrate_to(new_database, BASE_BEFORE)

    assert definitions(new_database) == [DEFINITION]


def test_going_back_on_live_takes_it_and_coming_forward_makes_it_again(new_database, make_hub):
    hub = make_hub(new_database)
    migrator.ensure_schema(hub)

    migrate_to(new_database, LIVE_BEFORE)
    assert definitions(new_database) == []

    migrator.ensure_schema(hub)
    assert definitions(new_database) == [DEFINITION]


@pytest.mark.parametrize("first", [LIVE_BEFORE, BASE_BEFORE], ids=["live_first", "base_first"])
def test_going_back_on_both_fails_in_neither_order(first, new_database, make_hub):
    migrator.ensure_schema(make_hub(new_database))
    second = BASE_BEFORE if first == LIVE_BEFORE else LIVE_BEFORE

    migrate_to(new_database, first, second)

    assert definitions(new_database) == []


def test_control_has_it_once(db):
    assert definitions(tenancy_connections.control_name()) == [DEFINITION]


def test_control_gets_it_under_the_routers_of_production(db):
    """The relay reads control's outbox too, and ``live.OutboxEvent`` is contextual. The suite's routers let every
    ``live`` migration reach control (``tests/legacy.py``); production's decide by the model the operation names."""
    control = connections[DEFAULT_DB_ALIAS]
    try:
        with override_settings(DATABASE_ROUTERS=["base.tenancy.router.TenantRouter"]):
            MigrationExecutor(control).migrate([LIVE_BEFORE])
            assert definitions(tenancy_connections.control_name()) == []

            MigrationExecutor(control).migrate([LIVE_DECLARES])
            assert definitions(tenancy_connections.control_name()) == [DEFINITION]
    finally:
        # Control's database is the session's: whatever failed above, the next test finds it at the leaf, indexed.
        MigrationExecutor(control).migrate([LIVE_DECLARES])
        if not definitions(tenancy_connections.control_name()):
            with hubs._maintenance(tenancy_connections.control_name()) as conn:
                conn.execute(DEPLOYED)


def test_makemigrations_has_nothing_to_write(db):
    output = io.StringIO()

    call_command("makemigrations", "--check", "--dry-run", stdout=output)

    assert "No changes detected" in output.getvalue()
