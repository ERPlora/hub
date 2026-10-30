"""The roles a hub's database is reached with, per cluster (round 2026-10-30, S2a; PLAN-DB §5 and §10; aws#23).

A hub on no cluster, or on one without a secret, uses the environment's roles: the default connection's for the app
(``hub_app``) and ``DB_MIGRATOR_USER`` for the migrator. A cluster with ``secret_name`` has its own, in two Secrets
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


def test_without_a_migrators_role_the_migrator_is_the_default_connections_own(settings):
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = "", ""
    default = settings.DATABASES["default"]

    found = credentials.credentials_for(None, credentials.MIGRATOR)

    assert (found.user, found.password) == (default["USER"], default["PASSWORD"])


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
