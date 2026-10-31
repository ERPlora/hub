"""The roles a hub's database is reached with, per cluster (round 2026-10-30, S2a; PLAN-DB §5 and §10; aws#23).

A hub on no cluster, or on one without a secret, uses the environment's roles: the default connection's for the app
(``hub_app``) and ``DB_MIGRATOR_USER`` for the migrator, which a process without it does not have (never the app's). A cluster with ``secret_name`` has its own, in two Secrets
Manager secrets under that prefix, ``…/app`` and ``…/migrator`` (the web may read only the first), each read once per
ten minutes and kept in the process; a secret that cannot be read is a readable failure, never the environment's roles
in its place. Where the cluster is comes from its row, never from the secrets. The web's alias of a hub carries the
app's role only and never asks for the migrator's secret.

The tests hand the module a fake Secrets Manager client (:class:`FakeSecrets`): no network, no mock of boto3.
"""

import json
import uuid
from types import SimpleNamespace

import pytest
from django.db import connections as django_connections

from base.tenancy import connections as tenancy_connections
from base.tenancy import credentials, names

#: A cluster's ``secret_name``: the prefix of its two secrets (aws#23), ``…/app`` and ``…/migrator``.
SECRET = "erplora/prod/clusters/cluster-2"
APP_SECRET, MIGRATOR_SECRET = f"{SECRET}/app", f"{SECRET}/migrator"
# Where the cluster is comes from its row (``control.Cluster``), never from the secrets' host and ports.
APP_VALUES = {
    "app_user": "hub_app",
    "app_password": "app-secret",
    "host": "secret-writer.example",
    "port": 9999,
    "pooler_host": "secret-pooler.example",
    "pooler_port": 9998,
}
MIGRATOR_VALUES = {
    "migrator_user": "hub_migrator",
    "migrator_password": "migrator-secret",
    "host": "secret-writer.example",
    "port": 9999,
}


class FakeSecrets:
    """Secrets Manager's ``get_secret_value`` over a dict; counts the reads; raises what it is told to."""

    def __init__(self, secrets: dict[str, object]):
        self.secrets = secrets
        self.reads: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict:  # noqa: N803 (boto3's own keyword)
        self.reads.append(SecretId)
        found = self.secrets[SecretId]
        if isinstance(found, Exception):
            raise found
        return {"Name": SecretId, "SecretString": found if isinstance(found, str) else json.dumps(found)}


@pytest.fixture(autouse=True)
def nothing_cached():
    credentials.forget()
    yield
    credentials.forget()


@pytest.fixture
def secrets(monkeypatch):
    fake = FakeSecrets({APP_SECRET: APP_VALUES, MIGRATOR_SECRET: MIGRATOR_VALUES})
    monkeypatch.setattr(credentials, "secrets_client", lambda: fake)
    return fake


@pytest.fixture
def clock(monkeypatch):
    now = SimpleNamespace(value=1000.0)
    monkeypatch.setattr(credentials, "_clock", lambda: now.value)
    return now


@pytest.fixture(autouse=True)
def restored_settings(monkeypatch):
    """Whatever a test registers is gone after it."""
    monkeypatch.setattr(django_connections, "settings", django_connections.settings)


def cluster(secret_name: str = SECRET, pooler_host: str = "pooler-2.example") -> SimpleNamespace:
    """A cluster as ``control.Cluster`` has it: its writer, its PgBouncer (if any) and the secret of its roles."""
    return SimpleNamespace(
        host="writer-2.example",
        port=5433,
        pooler_host=pooler_host,
        pooler_port=6433,
        secret_name=secret_name,
    )


def a_hub(on=None) -> SimpleNamespace:
    hub_id = uuid.uuid7()
    return SimpleNamespace(
        id=hub_id, db_name=names.hub_db_name(tenancy_connections.control_name(), hub_id), cluster=on
    )


def test_without_a_cluster_the_environments_roles_are_used(settings):
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = "hub_migrator", "env-migrator"
    default = settings.DATABASES["default"]

    app = credentials.credentials_for(None, credentials.APP)
    migrator = credentials.credentials_for(None, credentials.MIGRATOR)

    assert (app.user, app.password) == (default["USER"], default["PASSWORD"])
    assert (migrator.user, migrator.password) == ("hub_migrator", "env-migrator")


def test_without_a_migrators_role_there_is_no_migrator_never_the_apps_role(settings):
    """Fails closed (review of hub#469): a process without ``DB_MIGRATOR_*`` (the web) has no migrator, and the app's
    role (``hub_app``, ``DB_USER``) never stands in for it."""
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = "", ""

    with pytest.raises(credentials.CredentialsUnavailable, match="DB_MIGRATOR_USER"):
        credentials.credentials_for(None, credentials.MIGRATOR)
    with pytest.raises(credentials.CredentialsUnavailable, match="DB_MIGRATOR_USER"):
        credentials.credentials_for(cluster(secret_name=""), credentials.MIGRATOR)
    assert credentials.credentials_for(None, credentials.APP).user == settings.DATABASES["default"]["USER"]


def test_a_migrators_user_without_its_password_is_no_migrator_either(settings):
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = "hub_migrator", ""

    with pytest.raises(credentials.CredentialsUnavailable, match="DB_MIGRATOR_PASSWORD"):
        credentials.credentials_for(None, credentials.MIGRATOR)


def test_a_cluster_without_a_secret_uses_the_environments_roles(secrets):
    for role in (credentials.APP, credentials.MIGRATOR):
        assert credentials.credentials_for(cluster(secret_name=""), role) == credentials.credentials_for(None, role)
    assert secrets.reads == []


def test_a_cluster_with_a_secret_reads_the_one_of_each_role(secrets):
    app = credentials.credentials_for(cluster(), credentials.APP)
    migrator = credentials.credentials_for(cluster(), credentials.MIGRATOR)

    assert (app.user, app.password, migrator.user, migrator.password) == (
        "hub_app",
        "app-secret",
        "hub_migrator",
        "migrator-secret",
    )
    assert secrets.reads == [APP_SECRET, MIGRATOR_SECRET]


def test_no_other_role_is_asked_for(secrets):
    with pytest.raises(ValueError, match="admin"):
        credentials.credentials_for(cluster(), "admin")
    assert secrets.reads == []


def test_the_passwords_never_show_in_a_repr(secrets):
    shown = repr(credentials.credentials_for(cluster(), credentials.APP)) + repr(
        credentials.credentials_for(cluster(), credentials.MIGRATOR)
    )

    assert "app-secret" not in shown and "migrator-secret" not in shown


def test_a_secret_is_read_once_per_ten_minutes(secrets, clock):
    credentials.credentials_for(cluster(), credentials.APP)
    clock.value += credentials.SECRET_TTL_SECONDS - 1
    credentials.credentials_for(cluster(), credentials.APP)
    assert secrets.reads == [APP_SECRET]

    clock.value += 2
    credentials.credentials_for(cluster(), credentials.APP)
    assert secrets.reads == [APP_SECRET, APP_SECRET]


def test_a_secret_that_cannot_be_read_is_a_readable_failure_never_the_environments_roles(secrets):
    secrets.secrets[MIGRATOR_SECRET] = RuntimeError("AccessDeniedException: not allowed")

    with pytest.raises(credentials.CredentialsUnavailable, match=MIGRATOR_SECRET) as caught:
        credentials.credentials_for(cluster(), credentials.MIGRATOR)

    assert "AccessDeniedException" in str(caught.value)


@pytest.mark.parametrize(
    "broken",
    ["not json", json.dumps(["a", "list"]), json.dumps({"app_user": "hub_app"}), json.dumps({**APP_VALUES, "app_password": ""})],
    ids=["not-json", "not-an-object", "keys-missing", "empty-password"],
)
def test_a_secret_out_of_its_shape_is_a_readable_failure(secrets, broken):
    secrets.secrets[APP_SECRET] = broken

    with pytest.raises(credentials.CredentialsUnavailable, match=APP_SECRET):
        credentials.credentials_for(cluster(), credentials.APP)


def test_a_failed_read_is_not_kept_the_next_call_reads_again(secrets):
    secrets.secrets[APP_SECRET] = RuntimeError("throttled")
    with pytest.raises(credentials.CredentialsUnavailable):
        credentials.credentials_for(cluster(), credentials.APP)

    secrets.secrets[APP_SECRET] = APP_VALUES
    assert credentials.credentials_for(cluster(), credentials.APP).user == "hub_app"
    assert secrets.reads == [APP_SECRET, APP_SECRET]


def test_a_hubs_alias_on_a_cluster_reaches_its_pooler_with_the_apps_role_never_the_migrators(secrets):
    hub = a_hub(on=cluster())

    alias = tenancy_connections.register_hub_alias(hub)
    registered = django_connections.settings[alias]

    assert (registered["HOST"], registered["PORT"]) == ("pooler-2.example", 6433)
    assert (registered["USER"], registered["PASSWORD"]) == ("hub_app", "app-secret")
    # The web may read only ``…/app`` (aws#23): a hub's alias never asks for the migrator's secret.
    assert secrets.reads == [APP_SECRET]


def test_the_migrators_alias_and_connection_on_a_cluster_reach_its_writer_as_its_migrator(secrets):
    on = cluster()
    hub = a_hub(on=on)

    alias = tenancy_connections.register_ddl_alias(hub.db_name, cluster=on)
    ddl = django_connections.settings[alias]
    conninfo = tenancy_connections.migrator_conninfo("postgres", cluster=on)

    assert (ddl["HOST"], ddl["PORT"], ddl["USER"], ddl["PASSWORD"]) == (
        "writer-2.example",
        5433,
        "hub_migrator",
        "migrator-secret",
    )
    assert (conninfo["host"], conninfo["port"], conninfo["user"], conninfo["password"]) == (
        "writer-2.example",
        5433,
        "hub_migrator",
        "migrator-secret",
    )


def test_a_hubs_alias_without_a_cluster_keeps_the_settings_own(secrets):
    template = django_connections.settings[tenancy_connections.TEMPLATE_ALIAS]

    alias = tenancy_connections.register_hub_alias(a_hub())

    registered = django_connections.settings[alias]

    assert (registered["HOST"], registered["PORT"], registered["USER"]) == (
        template["HOST"],
        template["PORT"],
        template["USER"],
    )
    assert secrets.reads == []


def test_a_hubs_alias_on_a_cluster_without_a_pooler_reaches_its_writer_directly(secrets):
    """The task's PgBouncer sidecar only knows the settings' own cluster: another one without a pooler of its own is
    reached on its writer, with the app's role all the same."""
    alias = tenancy_connections.register_hub_alias(a_hub(on=cluster(pooler_host="")))
    registered = django_connections.settings[alias]

    assert (registered["HOST"], registered["PORT"], registered["USER"]) == ("writer-2.example", 5433, "hub_app")


def test_the_secrets_own_host_and_port_are_never_used_the_clusters_row_says_where(secrets):
    on = cluster()

    ddl_alias = tenancy_connections.register_ddl_alias(a_hub(on=on).db_name, cluster=on)

    ddl = django_connections.settings[ddl_alias]
    hub_alias = tenancy_connections.register_hub_alias(a_hub(on=on))
    alias = django_connections.settings[hub_alias]

    assert (ddl["HOST"], ddl["PORT"]) == (on.host, on.port)
    assert (alias["HOST"], alias["PORT"]) == (on.pooler_host, on.pooler_port)


@pytest.fixture
def tls_to_the_writer(monkeypatch):
    """Production's settings: the default connection reaches Aurora's writer with ``verify-full``; the hubs' template
    goes through the task's PgBouncer on loopback, without TLS options (``config/settings.py``)."""
    import copy

    current = django_connections.settings
    changed = {alias: copy.deepcopy(values) for alias, values in current.items()}
    changed["default"]["OPTIONS"] |= {"sslmode": "verify-full", "sslrootcert": "/etc/ssl/certs/rds-global-bundle.pem"}
    for option in ("sslmode", "sslrootcert"):
        changed[tenancy_connections.TEMPLATE_ALIAS]["OPTIONS"].pop(option, None)
    monkeypatch.setattr(django_connections, "settings", changed)


def test_a_hub_reached_on_its_clusters_writer_directly_keeps_the_writers_tls(secrets, tls_to_the_writer):
    """Review of hub#471 (I5): without a PgBouncer of its own, the hub's alias goes straight to the cluster's writer,
    so it carries the default connection's ``sslmode``/``sslrootcert`` (never a plain connection to Aurora)."""
    alias = tenancy_connections.register_hub_alias(a_hub(on=cluster(pooler_host="")))
    options = django_connections.settings[alias]["OPTIONS"]

    assert (options["sslmode"], options["sslrootcert"]) == ("verify-full", "/etc/ssl/certs/rds-global-bundle.pem")


def test_a_hub_reached_through_a_pgbouncer_keeps_the_templates_options(secrets, tls_to_the_writer):
    alias = tenancy_connections.register_hub_alias(a_hub(on=cluster()))
    options = django_connections.settings[alias]["OPTIONS"]

    assert "sslmode" not in options and "sslrootcert" not in options


# ── Rotation and a Secrets Manager that fails after a good read (review of hub#471, I4) ──────────────────────────────


def test_a_secret_that_fails_on_its_refresh_keeps_the_last_good_one_and_says_so(secrets, clock, caplog):
    first = credentials.credentials_for(cluster(), credentials.APP)
    clock.value += credentials.SECRET_TTL_SECONDS + 1
    secrets.secrets[APP_SECRET] = RuntimeError("ThrottlingException")

    kept = credentials.credentials_for(cluster(), credentials.APP)
    again = credentials.credentials_for(cluster(), credentials.APP)

    assert kept == again == first
    assert "base.tenancy.credentials.stale" in caplog.text and APP_SECRET in caplog.text
    # It is not asked again on every use: once more after a short wait.
    assert secrets.reads == [APP_SECRET, APP_SECRET]
    clock.value += credentials.STALE_RETRY_SECONDS + 1
    secrets.secrets[APP_SECRET] = APP_VALUES | {"app_password": "rotated"}
    assert credentials.credentials_for(cluster(), credentials.APP).password == "rotated"


def test_a_rotated_password_reaches_a_hubs_alias_already_registered_and_its_open_connection(secrets, clock):
    hub = a_hub(on=cluster())
    alias = tenancy_connections.register_hub_alias(hub)
    wrapper = django_connections[alias]
    assert wrapper.settings_dict["PASSWORD"] == "app-secret"

    secrets.secrets[APP_SECRET] = APP_VALUES | {"app_password": "rotated"}
    clock.value += credentials.SECRET_TTL_SECONDS + 1
    tenancy_connections.register_hub_alias(hub)

    assert django_connections.settings[alias]["PASSWORD"] == "rotated"
    assert django_connections[alias].settings_dict["PASSWORD"] == "rotated"


def test_another_threads_connection_takes_the_rotated_password_when_it_opens_the_hub_again(secrets, clock):
    import threading

    hub = a_hub(on=cluster())
    alias = tenancy_connections.register_hub_alias(hub)
    seen = {}

    def other_thread(step):
        tenancy_connections.register_hub_alias(hub)
        seen[step] = django_connections[alias].settings_dict["PASSWORD"]

    first = threading.Thread(target=other_thread, args=("before",))
    first.start()
    first.join()
    secrets.secrets[APP_SECRET] = APP_VALUES | {"app_password": "rotated"}
    clock.value += credentials.SECRET_TTL_SECONDS + 1
    tenancy_connections.register_hub_alias(hub)
    second = threading.Thread(target=other_thread, args=("after",))
    second.start()
    second.join()

    assert seen == {"before": "app-secret", "after": "rotated"}


def test_the_migrators_role_on_a_cluster_with_its_secret_is_that_secrets(secrets):
    """``migrate_hubs`` (``base.tenancy.migrator``) reaches a cluster with its own secret as that secret's migrator."""
    from base.tenancy import migrator

    assert migrator.migrator_credentials(cluster()) == ("hub_migrator", "migrator-secret")
    assert secrets.reads == [MIGRATOR_SECRET]

    credentials.forget()
    secrets.secrets[MIGRATOR_SECRET] = RuntimeError("AccessDeniedException")
    with pytest.raises(migrator.MigratorCredentialsMissing, match=MIGRATOR_SECRET):
        migrator.migrator_credentials(cluster())



def test_a_rotated_migrators_password_reaches_a_ddl_alias_already_registered(secrets, clock):
    """Re-review of hub#471 (b): a cluster's ``<db>__ddl`` takes the migrator's new password too, never the first one
    for the life of the process."""
    on = cluster()
    db_name = a_hub(on=on).db_name
    alias = tenancy_connections.register_ddl_alias(db_name, cluster=on)
    assert django_connections[alias].settings_dict["PASSWORD"] == "migrator-secret"

    secrets.secrets[MIGRATOR_SECRET] = MIGRATOR_VALUES | {"migrator_password": "rotated"}
    clock.value += credentials.SECRET_TTL_SECONDS + 1
    tenancy_connections.register_ddl_alias(db_name, cluster=on)

    assert django_connections.settings[alias]["PASSWORD"] == "rotated"
    assert django_connections[alias].settings_dict["PASSWORD"] == "rotated"
