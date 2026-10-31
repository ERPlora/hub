"""``base.tenancy.bootstrap``: what ``manage.py bootstrap_databases`` runs (aws-next, «Contrato»).

Databases ``saas``, ``hub`` and ``hub_template``; the roles of PLAN-DB §10 with their passwords
(``*_PASSWORD``), timeouts (§12.2) and default privileges; ``vector`` in the template and in
``saas``; the ``shared`` schema of ``saas`` for ``hub_shared`` (round 16, PLAN §21; spec §3.3).
Here, what each role can and cannot do once bootstrapped; the command's output and exit codes are
``test_bootstrap_databases.py``, which reuses these helpers.

Run against the local Postgres (``compose.yaml``) as an emulated RDS master: a role with
``CREATEROLE`` and ``CREATEDB`` but no ``SUPERUSER``, which the local superuser creates and drops,
so the permission rules of PostgreSQL 16+ apply as on Aurora. Every database and role carries a
per-process prefix (``Names.with_prefix``): the real ``hub``/``saas`` and their roles are never
touched, and the fixtures drop everything prefixed at the end.

That master creates only trusted extensions (``pgcrypto``), so its tests name the ones they create.
Aurora's master also holds ``rds_superuser``, which creates ``vector``; pgvector is no trusted
extension, and locally only a superuser creates it: ``rds_cluster`` bootstraps with the local
superuser as the master, where pgvector is installed.
"""

import os
from dataclasses import dataclass

import psycopg
import pytest
from django.conf import settings as django_settings
from psycopg import errors, sql

from base.tenancy import bootstrap

#: The contract with aws-next (``stacks/prod/apps.tf``, task ``db-bootstrap``): role → variable.
VARIABLES = {
    "hub_app": "HUB_APP_PASSWORD",
    "saas_app": "SAAS_APP_PASSWORD",
    "hub_migrator": "HUB_MIGRATOR_PASSWORD",
    "saas_migrator": "SAAS_MIGRATOR_PASSWORD",
    "hub_admin": "HUB_ADMIN_PASSWORD",
    "hub_shared": "HUB_SHARED_PASSWORD",
}
MASTER_PASSWORD = "master-pw"


# ── Helpers ────────────────────────────────────────────────────────────────────────────────────


def server() -> dict:
    database = django_settings.DATABASES["default"]
    return {"host": database["HOST"], "port": database["PORT"], "connect_timeout": 5}


def superuser(dbname: str = "postgres") -> psycopg.Connection:
    database = django_settings.DATABASES["default"]
    return psycopg.connect(
        **server(),
        user=database["USER"],
        password=database["PASSWORD"],
        dbname=dbname,
        autocommit=True,
    )


def connect_as(role: str, password: str, dbname: str) -> psycopg.Connection:
    return psycopg.connect(
        **server(), user=role, password=password, dbname=dbname, autocommit=True
    )


def connect_error(role: str, password: str, dbname: str) -> str | None:
    """``None`` when ``role`` gets in; the server's reason otherwise."""
    try:
        connect_as(role, password, dbname).close()
    except psycopg.OperationalError as error:
        return str(error)
    return None


def allowed(conn: psycopg.Connection, statement: str) -> bool:
    try:
        conn.execute(statement)
    except errors.InsufficientPrivilege:
        return False
    return True


def show(conn: psycopg.Connection, setting: str) -> str:
    return conn.execute(sql.SQL("SHOW {}").format(sql.Identifier(setting))).fetchone()[
        0
    ]


def drop_prefixed(prefix: str) -> None:
    """Drop every database and role whose name starts with ``prefix``; the master last."""
    with superuser() as conn:
        databases = conn.execute(
            "SELECT datname FROM pg_database WHERE starts_with(datname, %s)", [prefix]
        ).fetchall()
        for (name,) in databases:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )
        roles = conn.execute(
            "SELECT rolname FROM pg_roles WHERE starts_with(rolname, %s) "
            "ORDER BY rolname = %s, rolname",
            [prefix, prefix + "master"],
        ).fetchall()
        for (name,) in roles:
            conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(name)))


def create_master(prefix: str, *, createrole: bool = True) -> dict:
    """An RDS-like master (``CREATEROLE``, ``CREATEDB``, no ``SUPERUSER``, ``pg_signal_backend`` with its ADMIN option
    as ``rds_superuser`` holds it); its libpq parameters."""
    name = prefix + "master"
    with superuser() as conn:
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER CREATEDB {} PASSWORD {}").format(
                sql.Identifier(name),
                sql.SQL("CREATEROLE" if createrole else "NOCREATEROLE"),
                sql.Literal(MASTER_PASSWORD),
            )
        )
        conn.execute(sql.SQL("GRANT pg_signal_backend TO {} WITH ADMIN OPTION").format(sql.Identifier(name)))
    return {**server(), "user": name, "password": MASTER_PASSWORD, "dbname": "postgres"}


def vector_available() -> bool:
    with superuser() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
            ).fetchone()
            is not None
        )


# ── Fixtures ───────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Cluster:
    prefix: str
    names: bootstrap.Names
    passwords: dict[str, str]
    master: dict

    def role(self, key: str) -> str:
        return self.prefix + key

    def connect(self, key: str, dbname: str) -> psycopg.Connection:
        return connect_as(self.role(key), self.passwords[key], dbname)

    def rerun(self, **kwargs) -> list:
        """The bootstrap again, with no extension but those the test names (the emulated master's are trusted)."""
        options = {
            "require_extensions": False,
            "template_extensions": (),
            "saas_extensions": (),
        }
        return bootstrap.bootstrap(
            passwords=self.passwords,
            names=self.names,
            conninfo=self.master,
            **options | kwargs,
        )


@pytest.fixture(scope="module")
def cluster():
    """One bootstrapped set of prefixed databases and roles for the read-mostly checks."""
    prefix = f"test_bsm_{os.getpid()}_"
    drop_prefixed(prefix)
    try:  # a failed bootstrap still drops what it left
        bootstrapped = Cluster(
            prefix=prefix,
            names=bootstrap.Names.with_prefix(prefix),
            passwords={role: f"pw-{role}" for role in VARIABLES},
            master=create_master(prefix),
        )
        bootstrapped.rerun()
        yield bootstrapped
    finally:
        drop_prefixed(prefix)


@pytest.fixture
def rds_cluster():
    """Prefixed names whose master is the local superuser, standing in for Aurora's ``rds_superuser``."""
    if not vector_available():
        pytest.skip("pgvector is not installed on this server")
    prefix = f"test_bsr_{os.getpid()}_"
    database = django_settings.DATABASES["default"]
    drop_prefixed(prefix)
    try:
        yield Cluster(
            prefix=prefix,
            names=bootstrap.Names.with_prefix(prefix),
            passwords={role: f"pw-{role}" for role in VARIABLES},
            master={
                **server(),
                "user": database["USER"],
                "password": database["PASSWORD"],
                "dbname": "postgres",
            },
        )
    finally:
        drop_prefixed(prefix)


# ── What the roles can and cannot do ───────────────────────────────────────────────────────────


def test_the_master_is_no_superuser(cluster):
    with superuser() as conn:
        rolsuper = conn.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = %s",
            [cluster.prefix + "master"],
        ).fetchone()[0]
    assert rolsuper is False


def test_owners_createdb_and_no_superuser_follow_plan_db(cluster):
    p = cluster.prefix
    with superuser() as conn:
        owners = dict(
            conn.execute(
                "SELECT datname, pg_get_userbyid(datdba) FROM pg_database "
                "WHERE starts_with(datname, %s)",
                [p],
            ).fetchall()
        )
        roles = conn.execute(
            "SELECT rolname, rolcreatedb, rolsuper FROM pg_roles WHERE starts_with(rolname, %s) "
            "AND rolname <> %s",
            [p, p + "master"],
        ).fetchall()
        createdb = {name: can_create for name, can_create, _super in roles}

    assert owners == {
        f"{p}hub": f"{p}hub_migrator",
        f"{p}hub_template": f"{p}hub_migrator",
        f"{p}saas": f"{p}saas_migrator",
    }
    assert createdb == {p + role: role == "hub_migrator" for role in VARIABLES}
    # PLAN-DB §14.6: no role of the platform is a superuser, hub_app least of all.
    assert {name: is_super for name, _can_create, is_super in roles} == {p + role: False for role in VARIABLES}


def test_hub_migrator_clones_the_template_into_a_hub_database(cluster):
    clone = cluster.prefix + "hub_clone"
    with cluster.connect("hub_migrator", "postgres") as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(clone), sql.Identifier(cluster.names.template)
            )
        )
        conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(clone)))


def test_app_roles_get_the_plan_timeouts_and_migrators_no_limit(cluster):
    n = cluster.names
    for key, dbname in (
        ("hub_app", n.control),
        ("saas_app", n.saas),
        ("hub_shared", n.saas),
    ):
        with cluster.connect(key, dbname) as conn:
            assert (show(conn, "statement_timeout"), show(conn, "lock_timeout")) == (
                "15s",
                "5s",
            )
    for key, dbname in (("hub_migrator", n.control), ("saas_migrator", n.saas)):
        with cluster.connect(key, dbname) as conn:
            assert (show(conn, "statement_timeout"), show(conn, "lock_timeout")) == (
                "0",
                "0",
            )


@pytest.mark.parametrize(
    ("key", "database", "gets_in"),
    [
        ("hub_app", "control", True),
        ("hub_admin", "control", True),
        ("hub_migrator", "control", True),
        ("hub_admin", "template", True),
        ("hub_migrator", "template", True),
        ("saas_app", "saas", True),
        ("saas_migrator", "saas", True),
        ("hub_shared", "saas", True),
        ("hub_app", "template", False),
        ("hub_app", "saas", False),
        ("hub_admin", "saas", False),
        ("saas_app", "control", False),
        ("saas_migrator", "control", False),
        ("hub_shared", "control", False),
        ("hub_shared", "template", False),
    ],
)
def test_public_cannot_connect_and_each_role_reaches_only_its_databases(
    cluster, key, database, gets_in
):
    error = connect_error(
        cluster.role(key), cluster.passwords[key], getattr(cluster.names, database)
    )

    if gets_in:
        assert error is None
    else:
        assert "permission denied for database" in error


def hub_from_template(cluster: Cluster) -> str:
    """A hub database cloned from the template and opened as the alta does (PLAN-DB §6, 1–2)."""
    hub = cluster.prefix + "hub_cloned"
    with cluster.connect("hub_migrator", "postgres") as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(hub), sql.Identifier(cluster.names.template)
            )
        )
        conn.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(hub))
        )
        conn.execute(
            sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}, {}").format(
                sql.Identifier(hub),
                sql.Identifier(cluster.role("hub_app")),
                sql.Identifier(cluster.role("hub_admin")),
            )
        )
    return hub


@pytest.mark.parametrize("database", ["control", "a hub cloned from the template"])
def test_hub_app_gets_dml_and_hub_admin_reads_what_hub_migrator_creates(
    cluster, database
):
    # The template's default privileges reach every hub through the clone; hub_app never connects
    # to the template itself (test_public_cannot_connect_and_each_role_reaches_only_its_databases).
    dbname = (
        cluster.names.control if database == "control" else hub_from_template(cluster)
    )
    try:
        with cluster.connect("hub_migrator", dbname) as conn:
            conn.execute(
                "CREATE TABLE sample "
                "(id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, name text)"
            )
        with cluster.connect("hub_app", dbname) as conn:
            assert allowed(conn, "INSERT INTO sample (name) VALUES ('a')")
            assert allowed(
                conn, "SELECT nextval(pg_get_serial_sequence('sample', 'id'))"
            )
            assert allowed(conn, "UPDATE sample SET name = 'b'")
            assert allowed(conn, "SELECT * FROM sample")
            assert allowed(conn, "DELETE FROM sample")
            assert not allowed(conn, "CREATE TABLE other (id int)")
        with cluster.connect("hub_admin", dbname) as conn:
            assert allowed(conn, "SELECT * FROM sample")
            assert not allowed(conn, "INSERT INTO sample (name) VALUES ('c')")
    finally:
        if database == "control":
            with cluster.connect("hub_migrator", dbname) as conn:
                conn.execute("DROP TABLE IF EXISTS sample")
        else:
            with cluster.connect("hub_migrator", "postgres") as conn:
                conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(dbname)))


@pytest.mark.parametrize("database", ["control", "a hub cloned from the template"])
def test_hub_app_reads_the_record_of_migrations_and_never_writes_it(cluster, database):
    # PLAN-DB §14.6: what says which schema a database has is the migrator's alone. The migrations run as hub_migrator
    # after the bootstrap (its default privileges give hub_app DML on every table it makes), and every hub is a clone
    # of the template.
    n = cluster.names
    for dbname in (n.control, n.template):
        with cluster.connect("hub_migrator", dbname) as conn:
            conn.execute(bootstrap.MIGRATIONS_TABLE_DDL)
            conn.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('base', '0001_initial', now())")
    dbname = n.control if database == "control" else hub_from_template(cluster)
    try:
        with cluster.connect("hub_app", dbname) as conn:
            assert allowed(conn, "SELECT app, name FROM django_migrations")
            assert not allowed(
                conn, "INSERT INTO django_migrations (app, name, applied) VALUES ('base', '9999_forged', now())"
            )
            assert not allowed(conn, "UPDATE django_migrations SET name = '9999_forged'")
            assert not allowed(conn, "DELETE FROM django_migrations")
            assert not allowed(conn, "TRUNCATE django_migrations")
    finally:
        if database != "control":
            with cluster.connect("hub_migrator", "postgres") as conn:
                conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(dbname)))


def test_a_record_of_migrations_hub_migrator_does_not_own_is_reported_never_left_writable(cluster):
    # A table made before this step by another role (the master, by hand): PostgreSQL only warns when who revokes is
    # not its owner, so the step checks what hub_app still holds and stops, naming the owner.
    foreign = cluster.prefix + "hub_foreign"
    with cluster.connect("hub_migrator", "postgres") as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(foreign)))
    try:
        with psycopg.connect(**{**cluster.master, "dbname": foreign}, autocommit=True) as conn:
            conn.execute(bootstrap.MIGRATIONS_TABLE_DDL)
            conn.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON django_migrations TO {}, {}").format(
                    sql.Identifier(cluster.role("hub_migrator")), sql.Identifier(cluster.role("hub_app"))
                )
            )

            with pytest.raises(bootstrap.BootstrapError, match=f"owned by {cluster.prefix}master"):
                bootstrap._migrations_table(conn, cluster.names)
    finally:
        with superuser() as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(foreign)))


def test_the_record_of_migrations_is_made_as_djangos_migrate_makes_it():
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder

    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.create_model(MigrationRecorder.Migration)

    assert editor.collected_sql == [bootstrap.MIGRATIONS_TABLE_DDL.replace(" IF NOT EXISTS", "") + ";"]


def test_hub_shared_writes_shared_app_and_reaches_nothing_in_public(cluster):
    saas = cluster.names.saas
    with cluster.connect("saas_migrator", saas) as conn:
        conn.execute("CREATE TABLE shared.app (id text PRIMARY KEY, name text)")
        conn.execute(
            "CREATE TABLE public.account "
            "(id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, email text)"
        )
    try:
        with cluster.connect("hub_shared", saas) as conn:
            assert allowed(
                conn, "INSERT INTO shared.app (id, name) VALUES ('demo', 'Demo')"
            )
            assert allowed(conn, "UPDATE shared.app SET name = 'Demo 2'")
            assert allowed(conn, "SELECT * FROM shared.app")
            assert not allowed(conn, "DELETE FROM shared.app")
            assert not allowed(conn, "SELECT * FROM public.account")
            assert not allowed(
                conn, "INSERT INTO public.account (email) VALUES ('a@b.c')"
            )
            assert not allowed(conn, "CREATE TABLE shared.other (id int)")
        with cluster.connect("saas_app", saas) as conn:
            assert allowed(conn, "SELECT * FROM shared.app")
            assert not allowed(conn, "INSERT INTO shared.app (id) VALUES ('other')")
            assert allowed(conn, "INSERT INTO public.account (email) VALUES ('a@b.c')")
            assert allowed(conn, "SELECT * FROM public.account")
    finally:
        with cluster.connect("saas_migrator", saas) as conn:
            conn.execute("DROP TABLE shared.app, public.account")


def test_a_rerun_restores_the_shared_grants_on_existing_tables(cluster):
    saas = cluster.names.saas
    with cluster.connect("saas_migrator", saas) as conn:
        conn.execute("CREATE TABLE shared.app_doc (id uuid PRIMARY KEY, body text)")
        conn.execute("REVOKE ALL ON shared.app_doc FROM " + cluster.role("hub_shared"))
    try:
        with cluster.connect("hub_shared", saas) as conn:
            assert not allowed(conn, "SELECT * FROM shared.app_doc")

        cluster.rerun()

        with cluster.connect("hub_shared", saas) as conn:
            assert allowed(conn, "SELECT * FROM shared.app_doc")
    finally:
        with cluster.connect("saas_migrator", saas) as conn:
            conn.execute("DROP TABLE shared.app_doc")


# ── Extensions ─────────────────────────────────────────────────────────────────────────────────


#: Where each extension list goes: the database (field of ``Names``) and a role that reads it.
EXTENSION_DATABASES = {"template": "hub_admin", "saas": "saas_migrator"}


@pytest.mark.parametrize("database", EXTENSION_DATABASES)
def test_an_extension_is_created_once(cluster, database):
    dbname = getattr(cluster.names, database)
    subject = f"extension pgcrypto on {dbname}"
    extensions = {f"{database}_extensions": ("pgcrypto",)}

    first = [str(step) for step in cluster.rerun(**extensions)]
    second = [str(step) for step in cluster.rerun(**extensions)]

    assert f"{subject}: created" in first
    assert f"{subject}: exists" in second
    with cluster.connect(EXTENSION_DATABASES[database], dbname) as conn:
        assert conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'"
        ).fetchone()


@pytest.mark.parametrize("database", EXTENSION_DATABASES)
def test_a_missing_extension_fails_in_production_and_is_skipped_locally(
    cluster, database
):
    missing = {f"{database}_extensions": ("erplora_no_such_extension",)}

    with pytest.raises(bootstrap.BootstrapError, match="erplora_no_such_extension"):
        cluster.rerun(**missing, require_extensions=True)
    steps = [str(step) for step in cluster.rerun(**missing)]

    assert (
        f"extension erplora_no_such_extension on {getattr(cluster.names, database)}: skipped "
        "(not available on this server)"
    ) in steps


def test_a_master_that_cannot_create_an_extension_fails_with_the_servers_reason(
    cluster,
):
    # What saas-migrate met in pre (saas#171) with vector; dblink is untrusted too, and in every image's contrib.
    reason = 'permission denied to create extension "dblink"'

    with pytest.raises(bootstrap.BootstrapError) as raised:
        cluster.rerun(saas_extensions=("dblink",), require_extensions=True)

    assert str(raised.value) == f"extension dblink on {cluster.names.saas}: {reason}"


def test_the_master_makes_vector_in_saas_so_the_saas_migration_only_finds_it(
    rds_cluster,
):
    # saas#171: saas_migrator runs pgvector's VectorExtension (CREATE EXTENSION IF NOT EXISTS vector), which
    # Aurora refuses it ("Must be rds_superuser"); PostgreSQL looks for the extension before it checks the role.
    n = rds_cluster.names
    migration = "CREATE EXTENSION IF NOT EXISTS vector"

    def run() -> list[str]:
        return [
            str(step)
            for step in bootstrap.bootstrap(
                passwords=rds_cluster.passwords, names=n, conninfo=rds_cluster.master
            )
        ]

    first, second = run(), run()

    for dbname in (n.template, n.saas):
        assert f"extension vector on {dbname}: created" in first
        assert f"extension vector on {dbname}: exists" in second
    with rds_cluster.connect("saas_migrator", n.saas) as conn:
        conn.execute(migration)
        assert conn.execute(
            "SELECT extowner::regrole::text FROM pg_extension WHERE extname = 'vector'"
        ).fetchone() == (rds_cluster.master["user"],)
    with superuser(n.saas) as conn:
        conn.execute("DROP EXTENSION vector")
    with (
        rds_cluster.connect("saas_migrator", n.saas) as conn,
        pytest.raises(errors.InsufficientPrivilege, match="vector"),
    ):
        conn.execute(migration)


# ── Inputs ─────────────────────────────────────────────────────────────────────────────────────


def test_read_passwords_maps_every_variable_and_names_all_the_missing_ones(monkeypatch):
    for role, variable in VARIABLES.items():
        monkeypatch.setenv(variable, f"pw-{role}")
    assert bootstrap.read_passwords() == {role: f"pw-{role}" for role in VARIABLES}

    monkeypatch.delenv("HUB_ADMIN_PASSWORD")
    monkeypatch.setenv("HUB_APP_PASSWORD", "")
    with pytest.raises(bootstrap.BootstrapError) as raised:
        bootstrap.read_passwords()
    assert "HUB_ADMIN_PASSWORD" in str(raised.value)
    assert "HUB_APP_PASSWORD" in str(raised.value)


def test_names_take_a_prefix_and_refuse_an_unsafe_one():
    assert bootstrap.Names() == bootstrap.Names(
        control="hub",
        template="hub_template",
        saas="saas",
        hub_app="hub_app",
        hub_migrator="hub_migrator",
        hub_admin="hub_admin",
        saas_app="saas_app",
        saas_migrator="saas_migrator",
        hub_shared="hub_shared",
    )
    assert bootstrap.Names.with_prefix("t_1_").template == "t_1_hub_template"
    for bad in ("Bad", "1abc_", "a-b_", 'x";drop', "a" * 52):
        with pytest.raises(ValueError, match="prefix"):
            bootstrap.Names.with_prefix(bad)


def test_admin_conninfo_is_the_default_connection_in_libpq_terms():
    database = django_settings.DATABASES["default"]

    conninfo = bootstrap.admin_conninfo()

    assert conninfo["user"] == database["USER"]
    assert conninfo["host"] == database["HOST"]
    assert conninfo["port"] == database["PORT"]
    assert "dbname" in conninfo
    assert not {"cursor_factory", "context", "prepare_threshold", "pool"} & set(
        conninfo
    )
    psycopg.conninfo.make_conninfo(**conninfo)  # only libpq keywords
