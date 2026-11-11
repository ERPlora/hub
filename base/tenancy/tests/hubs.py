"""The tests' hubs with a database of their own (PLAN-DB §4 «Tests»; plan 2026-10-22-fase-2-tenencia §4, step 7).

Per test session (and xdist worker), next to its control database ``<control>``:

- ``<control>_template_test``: created here and migrated as ``migrate_hubs`` migrates a template
  (``base.tenancy.migrator.ensure_template``), with every hub app whose tables only reference the hub's own
  (``migrator.portable_apps``);
- ``<control>_<hex of HUB_A_ID>`` and ``<control>_<hex of HUB_B_ID>``: cloned from it with
  ``CREATE DATABASE … TEMPLATE``, each with its identity row (``base_hub_identity``).

The names are the production rule's (``base.tenancy.names``), so two sessions or two workers never share one. They are
dropped when the session ends. The rows in control (``hub_a``, ``hub_b``) are the root ``conftest.py``'s fixtures.
:func:`watched` and :func:`assert_only_alias` see every statement of every thread by alias: «A never reaches B».
"""

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

import psycopg
import pytest
from django.apps import apps
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.backends.signals import connection_created
from django.db.backends.utils import CursorWrapper
from psycopg import sql

from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, inventory, migrator, names
from control.models import Cluster, Hub

HUB_A_ID = uuid.UUID("01a16000-0000-7000-8000-00000000000a")
HUB_B_ID = uuid.UUID("01a16000-0000-7000-8000-00000000000b")
#: Their aliases (``base.tenancy.connections.hub_alias``), registered for the whole session once built, so a test can
#: name them: ``pytest.mark.django_db(databases=HUB_DATABASES)`` wraps them in its transaction as it does ``default``.
#: Naming them is enough: the root conftest gets such a test ``hub_databases`` (``pytest_collection_modifyitems``).
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


#: The sessions clients hold open on a database. Only client backends: the server's own processes are listed with a
#: ``datname`` too, and they are nobody's to close. An autovacuum worker on ``pg_database`` (every ``CREATE DATABASE`` of
#: the suite dirties it) works from whichever database it is sent to, a database just made included: it counted as a
#: session in hub#819's CI.
CLIENT_SESSIONS_COLUMNS = "(pid, application_name, state, last query)"
CLIENT_SESSIONS = """
    SELECT pid, application_name, state, left(query, 100) FROM pg_stat_activity
    WHERE datname = %s AND backend_type = 'client backend' ORDER BY pid
"""
#: How long ``assert_nobody_on`` waits for the sessions on a database to end, and how often it looks: a client's
#: ``close()`` returns before its server process has left ``pg_stat_activity``, so a connection just closed is still
#: counted for a moment (hub#484's CI); one still there after the wait is a connection left open.
SESSIONS_END_WAIT = 5.0
SESSIONS_END_POLL = 0.05


def client_sessions_on(name: str) -> list[tuple]:
    """Who is connected to the database ``name`` now (:data:`CLIENT_SESSIONS`)."""
    with _maintenance() as conn:
        return conn.execute(CLIENT_SESSIONS, [name]).fetchall()


def assert_nobody_on(name: str, *, wait: float = SESSIONS_END_WAIT) -> None:
    """Fail unless every client's session on the database ``name`` has ended within ``wait`` seconds, naming the ones
    still there."""
    deadline = time.monotonic() + wait
    with _maintenance() as conn:  # autocommit: each look is a new snapshot of pg_stat_activity
        while True:
            left = conn.execute(CLIENT_SESSIONS, [name]).fetchall()
            if not left or time.monotonic() >= deadline:
                break
            time.sleep(SESSIONS_END_POLL)
    assert not left, f"still connected to {name} after {wait:g} s, as {CLIENT_SESSIONS_COLUMNS}: {left}"


def _drop(conn, name: str, control: str) -> None:
    conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(names.identifier(name, control=control)))


def on_the_test_database() -> bool:
    """``default`` is this session's test database, not the developer's: what the root conftest's ``django_db_setup``
    leaves it as."""
    connection = connections[DEFAULT_DB_ALIAS]
    return connection.settings_dict["NAME"] == connection.creation._get_test_db_name()


def _assert_on_the_test_database() -> None:
    assert on_the_test_database(), (
        f"default is {tenancy_connections.control_name()!r}, not this session's test database"
    )


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
        _assert_on_the_test_database()
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


#: The role a platform's template of the tests grants, as ``bootstrap_databases`` grants ``hub_admin``: one every
#: PostgreSQL 14+ has, so the tests create no role.
TEMPLATE_GRANTEE = "pg_monitor"


def bootstrap_template(name: str, *, control: str | None = None) -> None:
    """Make ``name`` as ``bootstrap_databases`` leaves a platform's template (``base.tenancy.bootstrap``): empty, no
    access for PUBLIC, ``CONNECT, TEMPORARY`` for one role and default privileges in ``public`` for it. The migrator
    never makes one (``migrator.TemplateMissing``)."""
    identifier = names.identifier(name, control=tenancy_connections.control_name() if control is None else control)
    grantee = sql.Identifier(TEMPLATE_GRANTEE)
    with _maintenance() as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(identifier))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(identifier))
        conn.execute(sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(identifier, grantee))
    with _maintenance(name) as conn:
        conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}").format(grantee))


def database_access(name: str) -> list[tuple[str, str, str, bool]]:
    """``(grantor, grantee, privilege, grantable)`` of the database ``name``, its default included (``acldefault``)."""
    with _maintenance() as conn:
        return sorted(
            conn.execute(
                "SELECT pg_get_userbyid(a.grantor), CASE WHEN a.grantee = 0 THEN 'PUBLIC' "
                "ELSE pg_get_userbyid(a.grantee) END, a.privilege_type, a.is_grantable "
                "FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a WHERE d.datname = %s",
                [name],
            ).fetchall()
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
        # And this thread's connection object, as ``migrator._forget_alias`` does: a later registration of the same
        # alias (another role, another server) would get the old object back, its old settings with it.
        try:
            del connections[alias]
        except AttributeError:
            pass
    connections.settings = before


def build() -> HubDatabases:
    """Make the template and both hubs' databases, then register both hubs' aliases for the rest of the session.

    Only under this session's test database: their names derive from ``default``'s, and they are dropped first."""
    _assert_on_the_test_database()
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
        conn.execute(sql.SQL("CREATE DATABASE {}").format(names.identifier(hubs.template, control=control)))
    # Migrated as migrate_hubs migrates a template: nobody stays connected to it afterwards, so it can be cloned.
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


# ── A hub's database copied: moved to another cluster (test_move) or restored from a copy (test_restore) ────────────

#: The table of its own a copied hub's database has: only the hub's database, never a template.
MARKER_TABLE = "w8a_marker"


def control_databases() -> set[str]:
    """The databases on the session's server named after its control database."""
    control = tenancy_connections.control_name()
    with _maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


def marker(name: str) -> list[str]:
    """What the hub's own table says in the database ``name``, in order."""
    with _maintenance(name) as conn:
        query = sql.SQL("SELECT note FROM {} ORDER BY note").format(sql.Identifier(MARKER_TABLE))
        return [row[0] for row in conn.execute(query)]


def says_it_is(name: str) -> list[uuid.UUID]:
    """Whom the database ``name`` says it is (``base_hub_identity``)."""
    with _maintenance(name) as conn:
        return [row[0] for row in conn.execute("SELECT hub_id FROM base_hub_identity")]


class CopiedHubs:
    """The rows and databases of a test that copies hubs' databases (committed: no test case there): the databases of
    the control database made after it was set up are dropped, and its rows deleted, by :meth:`clean`."""

    def __init__(self, template: str):
        self.template = template
        self.hubs: list[Hub] = []
        self.clusters: list[Cluster] = []
        self._before = control_databases()

    def cluster(self, name: str, **fields) -> Cluster:
        """A cluster's row on the session's server (CI has one)."""
        default = connections.settings["default"]
        values = {"host": default["HOST"], "port": default["PORT"], "pooler_host": ""}
        self.clusters.append(row := Cluster.objects.create(name=f"{name}-{uuid.uuid4().hex[:8]}", **(values | fields)))
        return row

    def database(self, hub_id: uuid.UUID, *notes: str) -> str:
        """The hub's own database on the session's server: a clone of the template with its identity and a table of its
        own holding ``notes``."""
        control = tenancy_connections.control_name()
        name = names.hub_db_name(control, hub_id)
        with _maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(name, control=control), names.identifier(self.template, control=control)
                )
            )
        with _maintenance(name) as conn:
            conn.execute("INSERT INTO base_hub_identity (hub_id) VALUES (%s)", [hub_id])
            conn.execute(sql.SQL("CREATE TABLE {} (note text)").format(sql.Identifier(MARKER_TABLE)))
            for note in notes:
                conn.execute(sql.SQL("INSERT INTO {} VALUES (%s)").format(sql.Identifier(MARKER_TABLE)), [note])
        return name

    def ready_hub(self, hub_id: uuid.UUID, name: str, **fields) -> Hub:
        """Its ready row in control, on the settings' own server unless ``fields`` say otherwise."""
        values = {
            "id": hub_id,
            "slug": f"acme-{hub_id.hex[-8:]}",
            "status": Hub.Status.READY,
            "db_name": name,
            "vertical": TEMPLATE_VERTICAL,
        }
        self.hubs.append(row := Hub.objects.create(**(values | fields)))
        return row

    def clean(self) -> None:
        control = tenancy_connections.control_name()
        with _maintenance() as conn:
            for name in sorted(control_databases() - self._before):
                _drop(conn, name, control)
        Hub.objects.filter(pk__in=[row.pk for row in self.hubs]).delete()
        Cluster.objects.filter(pk__in=[row.pk for row in self.clusters]).delete()


@contextmanager
def an_app_role() -> Iterator[str]:
    """A login role of the test's own that plays ``hub_app`` (password ``app``), dropped after it."""
    role = f"w8a_app_{uuid.uuid4().hex[:8]}"
    with _maintenance() as conn:
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'app'").format(sql.Identifier(role)))
    try:
        yield role
    finally:
        with _maintenance() as conn:
            for name in sorted(control_databases()):
                revoke = sql.SQL("REVOKE ALL ON DATABASE {} FROM {}")
                conn.execute(revoke.format(sql.Identifier(name), sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def app_roles(role: str):
    """The environment's roles with ``role`` as its ``hub_app`` (``base.tenancy.bootstrap.Names``)."""
    from base.tenancy import bootstrap

    return bootstrap.Names(hub_app=role, hub_admin="pg_monitor")


def reaches(role: str, name: str) -> bool:
    """Whether ``role`` connects to the database ``name``."""
    default = connections.settings["default"]
    try:
        with psycopg.connect(
            dbname=name, user=role, password="app", host=default["HOST"], port=default["PORT"], connect_timeout=5
        ):
            return True
    except psycopg.OperationalError:
        return False


def grant_connect(role: str, name: str) -> None:
    with _maintenance() as conn:
        grant = sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
        conn.execute(grant.format(sql.Identifier(name), sql.Identifier(role)))
