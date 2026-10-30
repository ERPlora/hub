"""The tests' hubs with a database of their own (PLAN-DB §4 «Tests»; plan 2026-10-22-fase-2-tenencia §4, step 7).

Per test session (and xdist worker), next to its control database ``<control>``:

- ``<control>_template_test``: built as ``migrate_hubs`` builds a template (``base.tenancy.migrator.ensure_template``),
  with every hub app whose tables only reference the hub's own (``migrator.portable_apps``);
- ``<control>_<hex of HUB_A_ID>`` and ``<control>_<hex of HUB_B_ID>``: cloned from it with
  ``CREATE DATABASE … TEMPLATE``, each with its identity row (``base_hub_identity``).

The names are the production rule's (``base.tenancy.names``), so two sessions or two workers never share one. They are
dropped when the session ends. The rows in control (``hub_a``, ``hub_b``) are the root ``conftest.py``'s fixtures.
"""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import psycopg
import pytest
from django.apps import apps
from django.db import connections
from django.db.backends.signals import connection_created
from psycopg import sql

from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, inventory, migrator, names
from control.models import Cluster, Hub

HUB_A_ID = uuid.UUID("01a16000-0000-7000-8000-00000000000a")
HUB_B_ID = uuid.UUID("01a16000-0000-7000-8000-00000000000b")
#: Their aliases (``base.tenancy.connections.hub_alias``), registered for the whole session once built, so a test can
#: name them: ``pytest.mark.django_db(databases=HUB_DATABASES)`` wraps them in its transaction as it does ``default``.
HUB_A_ALIAS = f"hub_{HUB_A_ID.hex}"
HUB_B_ALIAS = f"hub_{HUB_B_ID.hex}"
HUB_DATABASES = ("default", HUB_A_ALIAS, HUB_B_ALIAS)
TEMPLATE_VERTICAL = "test"
#: The hubs the root conftest's ``local_hubs`` writes for every test with a database.
LOCAL_HUBS = ("a", "b")
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


@pytest.fixture(name="db")
def committed_database(django_db_setup, django_db_blocker):
    """The test database without a test case around it, for a test of the migrator: what it writes is committed.

    The migrator registers ``<db_name>__ddl`` aliases as it goes, which a Django test case refuses (an alias in the
    settings that is not in its ``databases``). Imported into a test module, it shadows pytest-django's ``db`` there:
    that name is what makes pytest-django set up the test database for any selection of those tests, which never
    reach the developer's own database (``default`` is checked to be the test database).
    """
    from base.models import AppActivation
    from control.models import Hub

    with django_db_blocker.unblock():
        connection = connections["default"]
        assert connection.settings_dict["NAME"] == connection.creation._get_test_db_name(), (
            f"default is {connection.settings_dict['NAME']!r}, not this session's test database"
        )
        before = set(Hub.objects.filter(slug__in=LOCAL_HUBS).values_list("slug", flat=True))
        yield
        # The root conftest's local_hubs writes them for any test with a db: committed here, so taken back.
        added = set(LOCAL_HUBS) - before
        AppActivation.objects.filter(host__in=added).delete()
        Hub.objects.filter(slug__in=added).delete()


def create_database(name: str) -> None:
    """An empty database ``name``, one of this session's control database's names (``base.tenancy.names``)."""
    with _maintenance() as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {}").format(names.identifier(name, control=tenancy_connections.control_name()))
        )


def drop_database(name: str, *, control: str | None = None) -> None:
    """Drop the database ``name`` (one of ``control``'s names, default this session's) if it exists, whoever is still
    connected to it."""
    with _maintenance() as conn:
        _drop(conn, name, tenancy_connections.control_name() if control is None else control)


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
        apps=migrator.portable_apps(),
    )
    with _maintenance() as conn:
        for name in (hubs.a, hubs.b, hubs.template):
            _drop(conn, name, control)
    # As migrate_hubs makes a template: nobody stays connected to it, so it can be cloned.
    migrator.ensure_template(migrator.Template(db_name=hubs.template, apps=hubs.apps))
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


# ── For the migrator's tests (base/tenancy/tests/test_migrator.py, base/tests/test_migrate_hubs.py) ───────────────


@pytest.fixture
def make_cluster(db):
    """``make_cluster(name, **fields)``: a cluster's row in control, deleted after the test (and its hubs')."""
    made = []

    def make(name: str, **fields) -> Cluster:
        fields.setdefault("host", connections.settings["default"]["HOST"])
        fields.setdefault("port", connections.settings["default"]["PORT"])
        made.append(Cluster.objects.create(name=f"{name}-{uuid.uuid4().hex[:8]}", pooler_host="pgbouncer", **fields))
        return made[-1]

    yield make
    Cluster.objects.filter(pk__in=[cluster.pk for cluster in made]).delete()


@pytest.fixture
def make_hub(db, make_cluster):
    """``make_hub(db_name, **fields)``: a ready hub's row in control, deleted after the test."""
    made = []

    def make(db_name: str = "", **fields) -> Hub:
        fields.setdefault("id", uuid.uuid7())
        fields.setdefault("status", Hub.Status.READY)
        made.append(Hub.objects.create(slug=f"t-{uuid.uuid4().hex[:12]}", db_name=db_name, **fields))
        return made[-1]

    yield make
    Hub.objects.filter(pk__in=[hub.pk for hub in made]).delete()


@pytest.fixture
def make_database(db):
    """``make_database()``: a new empty database named as a hub's of this control database; all dropped after."""
    made = []

    def make() -> str:
        made.append(names.hub_db_name(tenancy_connections.control_name(), uuid.uuid7()))
        create_database(made[-1])
        return made[-1]

    yield make
    for name in made:
        drop_database(name)


@pytest.fixture
def new_database(make_database):
    """An empty database named as a hub's of this session's control database, dropped after the test."""
    return make_database()


@pytest.fixture
def template_name(db):
    """``template_name()``: the name of a template of this control database that does not exist yet (each call a
    new vertical); every one is dropped after the test."""
    made = []

    def make() -> str:
        made.append(names.template_db_name(tenancy_connections.control_name(), f"t{uuid.uuid4().hex[:12]}"))
        return made[-1]

    yield make
    for name in made:
        drop_database(name)


@pytest.fixture
def opened_at():
    """``(host, database)`` of every connection Django opened during the test."""
    seen: list[tuple[str, str]] = []

    def record(sender, connection, **kwargs):
        seen.append((connection.settings_dict["HOST"], connection.settings_dict["NAME"]))

    connection_created.connect(record)
    yield seen
    connection_created.disconnect(record)


def same_server_by_another_name() -> str:
    """The settings' own database server, named otherwise: a second «cluster» on the same Postgres."""
    host = connections.settings["default"]["HOST"]
    others = {"127.0.0.1": "localhost", "localhost": "127.0.0.1"}
    assert host in others, f"the tests' database host {host!r} has no second name to stand for another cluster"
    return others[host]
