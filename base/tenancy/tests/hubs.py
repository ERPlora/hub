"""The tests' hubs with a database of their own (PLAN-DB §4 «Tests»; plan 2026-10-22-fase-2-tenencia §4, step 7).

Per test session (and xdist worker), next to its control database ``<control>``:

- ``<control>_template_test``: built by the migrator (``base.tenancy.migrator.migrate_apps``) through its ``__ddl``
  alias, with every hub app whose tables only reference the hub's own (:func:`portable_apps`);
- ``<control>_<hex of HUB_A_ID>`` and ``<control>_<hex of HUB_B_ID>``: cloned from it with
  ``CREATE DATABASE … TEMPLATE``, each with its identity row (``base_hub_identity``).

The names are the production rule's (``base.tenancy.names``), so two sessions or two workers never share one. They are
dropped when the session ends. The rows in control (``hub_a``, ``hub_b``) are the root ``conftest.py``'s fixtures.
:func:`watched` and :func:`assert_only_alias` see every statement of every thread by alias: «A never reaches B».
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

import psycopg
from django.apps import apps
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.backends.utils import CursorWrapper
from django.db.migrations.loader import MigrationLoader
from psycopg import sql

from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, inventory, migrator, names

HUB_A_ID = uuid.UUID("01a16000-0000-7000-8000-00000000000a")
HUB_B_ID = uuid.UUID("01a16000-0000-7000-8000-00000000000b")
#: Their aliases (``base.tenancy.connections.hub_alias``), registered for the whole session once built, so a test can
#: name them: ``pytest.mark.django_db(databases=HUB_DATABASES)`` wraps them in its transaction as it does ``default``.
HUB_A_ALIAS = f"hub_{HUB_A_ID.hex}"
HUB_B_ALIAS = f"hub_{HUB_B_ID.hex}"
HUB_DATABASES = ("default", HUB_A_ALIAS, HUB_B_ALIAS)
TEMPLATE_VERTICAL = "test"
#: What the tests keep in a hub's database between tests: the rest is emptied after each one.
KEPT_TABLES = frozenset({"django_migrations", "base_hub_identity"})


@dataclass(frozen=True)
class HubDatabases:
    control: str
    template: str
    a: str
    b: str
    apps: tuple[str, ...]


def _hub_classes(model) -> bool:
    return inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)


def portable_apps() -> tuple[str, ...]:
    """The hub apps whose tables reference only a hub's own, and whose migrations need no other app's.

    Phase 1 links some modules to control's users (``settings.AUTH_USER_MODEL``: staff, attendance, task,
    whatsapp_inbox and what depends on them): their tables cannot live in a hub's database until the hub's own
    staff comes (PLAN-DB §2), so the tests' template leaves them out.
    """
    hub_apps = {
        config.label
        for config in apps.get_app_configs()
        if config.name.startswith(inventory.HUB_MODULES_PACKAGE) or inventory.APP_CLASSES.get(config.label) == inventory.HUB
    }
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    needs = {
        label: {node[0] for leaf in graph.leaf_nodes() if leaf[0] == label for node in graph.forwards_plan(leaf)}
        & hub_apps
        for label in hub_apps
    }
    blocked = {
        label
        for label in hub_apps
        for model in apps.get_app_config(label).get_models(include_auto_created=True)
        if _hub_classes(model)
        for field in model._meta.get_fields()
        if field.is_relation and field.concrete and field.related_model is not None
        and inventory.classify(field.related_model) == inventory.CONTROL
    }
    while grown := {label for label in hub_apps - blocked if needs[label] & blocked}:
        blocked |= grown
    return tuple(sorted(hub_apps - blocked))


def hub_tables(app_labels) -> set[str]:
    """The tables a hub's database has for ``app_labels``: their hub's and contextual models'."""
    return {
        model._meta.db_table
        for label in app_labels
        for model in apps.get_app_config(label).get_models(include_auto_created=True)
        if _hub_classes(model)
    }


@contextmanager
def _maintenance(dbname: str = "postgres"):
    """A direct, autocommit connection with control's credentials (``CREATE``/``DROP DATABASE`` need one)."""
    settings = connections.settings["default"]
    with psycopg.connect(
        dbname=dbname,
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"],
        port=settings["PORT"],
        autocommit=True,
    ) as conn:
        yield conn


def _drop(conn, name: str, control: str) -> None:
    conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(names.identifier(name, control=control)))


def forget_aliases(before: dict) -> None:
    """Close and forget every alias registered since ``connections.settings`` was ``before``.

    Django's test case wraps, when it starts, every alias it was not told about, and unwraps them when it ends: an
    alias a test registered and left would break that unwrapping, so each test leaves the settings as it found them.
    """
    for alias in set(connections.settings) - set(before):
        connections[alias].close()
    connections.settings = before


def build() -> HubDatabases:
    """Make the template and both hubs' databases, then register both hubs' aliases for the rest of the session."""
    before = connections.settings
    try:
        built = _build()
    finally:
        forget_aliases(before)
    for hub_id, name in ((HUB_A_ID, built.a), (HUB_B_ID, built.b)):
        tenancy_connections.register_hub_alias(SimpleNamespace(id=hub_id, db_name=name, cluster=None))
    return built


def _build() -> HubDatabases:
    control = tenancy_connections.control_name()
    hubs = HubDatabases(
        control=control,
        template=names.template_db_name(control, TEMPLATE_VERTICAL),
        a=names.hub_db_name(control, HUB_A_ID),
        b=names.hub_db_name(control, HUB_B_ID),
        apps=portable_apps(),
    )
    with _maintenance() as conn:
        for name in (hubs.a, hubs.b, hubs.template):
            _drop(conn, name, control)
        conn.execute(sql.SQL("CREATE DATABASE {}").format(names.identifier(hubs.template, control=control)))
    ddl = tenancy_connections.register_ddl_alias(hubs.template)
    try:
        migrator.migrate_apps(ddl, hubs.apps)
    finally:
        # Nobody may stay connected to a template: its clone would fail.
        connections[ddl].close()
    with _maintenance() as conn:
        for name in (hubs.a, hubs.b):
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(name, control=control), names.identifier(hubs.template, control=control)
                )
            )
    for hub_id, name in ((HUB_A_ID, hubs.a), (HUB_B_ID, hubs.b)):
        alias = tenancy_connections.register_ddl_alias(name)
        try:
            identity.write(alias, hub_id)
        finally:
            connections[alias].close()
    return hubs


@contextmanager
def clone_of_the_template(hubs: HubDatabases, name: str) -> Iterator[str]:
    """The database ``name``, cloned from the session's template as an alta does, before its identity is written;
    dropped after the block (``WITH (FORCE)``: an alias the block left open does not keep it)."""
    with _maintenance() as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                names.identifier(name, control=hubs.control), names.identifier(hubs.template, control=hubs.control)
            )
        )
    try:
        yield name
    finally:
        with _maintenance() as conn:
            _drop(conn, name, hubs.control)


def drop(hubs: HubDatabases) -> None:
    for alias in (HUB_A_ALIAS, HUB_B_ALIAS):
        connections[alias].close()
    with _maintenance() as conn:
        for name in (hubs.a, hubs.b, hubs.template):
            _drop(conn, name, hubs.control)


def empty(name: str) -> None:
    """Delete every row a test left in the hub's database ``name``, its identity and migrations aside."""
    with _maintenance(name) as conn:
        tables = [
            row[0]
            for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
            if row[0] not in KEPT_TABLES
        ]
        if tables:
            conn.execute(
                sql.SQL("TRUNCATE {} CASCADE").format(sql.SQL(", ").join(sql.Identifier(table) for table in tables))
            )


def table_names(name: str) -> set[str]:
    """The tables of the database ``name``'s ``public`` schema."""
    with _maintenance(name) as conn:
        return {row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


@contextmanager
def watched() -> Iterator[dict[str, list[str]]]:
    """Every statement any thread sends, by alias: a wrapper at the cursor, under every connection of every thread
    (a ``connection.execute_wrapper`` on every alias at once, those registered while the block runs included).

    Scoped to the block (``mock.patch.object``): ``monkeypatch.undo()`` would also undo the test's other patches, the
    ``no_test_fallback`` one included."""
    sent: dict[str, list[str]] = {}
    real = CursorWrapper._execute

    def execute(self, sql, params, *ignored):
        sent.setdefault(self.db.alias, []).append(sql)
        return real(self, sql, params, *ignored)

    with mock.patch.object(CursorWrapper, "_execute", execute):
        yield sent


#: Tables of a hub's (or contextual) model that a block watched by :func:`assert_only_alias` may still name in control's
#: database, each with its reason. None: in control's, a hub's table is phase 1's shared data (``db_name=""``), nobody's
#: own, and a hub with its own database never reads it.
CONTROL_HUB_TABLES_ALLOWED: dict[str, str] = {}


def _hub_tables_named(statements: list[str]) -> list[str]:
    """The tables of hub (and contextual) models that ``statements`` name, quoted as Django quotes them."""
    tables = {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if _hub_classes(model) and model._meta.db_table not in CONTROL_HUB_TABLES_ALLOWED
    }
    return sorted({table for statement in statements for table in tables if f'"{table}"' in statement})


@contextmanager
def assert_only_alias(alias: str) -> Iterator[dict[str, list[str]]]:
    """The block reaches no hub's database but ``alias``'s (PLAN-DB §14.2): whatever any thread sends to another alias
    than ``alias`` fails it, whichever hub that alias is, and so does a statement to control's (``default``: the
    registry, the sessions) that names a hub's table, phase 1's shared data (``CONTROL_HUB_TABLES_ALLOWED`` aside).
    Yields the statements by alias (:func:`watched`)."""
    with watched() as sent:
        yield sent
    strays = {other: statements[:3] for other, statements in sent.items() if other not in (alias, DEFAULT_DB_ALIAS)}
    assert not strays, f"Only {alias} and control's database may be reached here, and these were too: {strays}"
    shared = _hub_tables_named(sent.get(DEFAULT_DB_ALIAS, []))
    assert not shared, f"Control's database was asked for phase 1's shared data of a hub's tables: {shared}"
