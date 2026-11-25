"""The servers the migrator reaches: the settings' own and control's clusters, each through its writer and as the
migrator's own role. ``CREATE DATABASE … TEMPLATE`` clones only within a server, so each has its templates."""

import uuid
from dataclasses import replace

import psycopg
import pytest
from django.db import connections

from base.tenancy import names
from base.tenancy.migrator import hub_templates, schema, servers
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import (
    committed_database,
    make_cluster,
    make_database,
    make_hub,
    new_database,
    opened_at,
    same_server_by_another_name,
    template_name,
)
from base.tenancy.tests.test_migrator import PLATFORM, control, tables_of

__all__ = ["committed_database", "make_cluster", "make_database", "make_hub", "new_database", "opened_at", "template_name"]


def test_without_clusters_only_the_settings_own_server_is_migrated(db):
    settings = connections.settings["default"]

    assert servers.clusters_to_migrate() == [
        servers.ClusterTarget(
            name="",
            host=settings["HOST"],
            port=int(settings["PORT"]),
            migrator_user=settings["USER"],
            migrator_password=settings["PASSWORD"],
            control=control(),
        )
    ]


def test_the_open_clusters_and_the_closed_ones_with_hubs_are_migrated_through_their_writer(make_cluster, make_hub):
    opened_one = make_cluster("open", host="writer.open.internal", port=5433)
    closed_with_hubs = make_cluster("closed-with-hubs", is_open=False)
    make_hub(names.hub_db_name(control(), uuid.uuid7()), cluster=closed_with_hubs)
    make_cluster("closed-empty", is_open=False)
    asked = []

    def credentials(cluster):
        asked.append(cluster.name)
        return f"migrator-{cluster.name}", "its-secret"

    targets = servers.clusters_to_migrate(credentials=credentials)

    assert [target.name for target in targets] == sorted([opened_one.name, closed_with_hubs.name])
    assert sorted(asked) == sorted([opened_one.name, closed_with_hubs.name])
    target = next(target for target in targets if target.name == opened_one.name)
    assert target == servers.ClusterTarget(
        name=opened_one.name,
        host="writer.open.internal",
        port=5433,
        migrator_user=f"migrator-{opened_one.name}",
        migrator_password="its-secret",
        control=control(),
        cluster_id=opened_one.id,
    )
    assert "its-secret" not in repr(target)  # never in a log or a test's report


def test_without_the_migrators_credentials_it_refuses_never_falling_back_to_defaults(settings, monkeypatch):
    """The web's and the worker's ``default`` is ``hub_app``: the migrator never runs as it."""
    settings.DEBUG = False
    monkeypatch.setenv("DB_MIGRATOR_USER", "")
    monkeypatch.setenv("DB_MIGRATOR_PASSWORD", "")

    with pytest.raises(servers.MigratorCredentialsMissing, match="DB_MIGRATOR_USER") as raised:
        servers.migrator_credentials(None)

    assert raised.value.code == "migrator_credentials_missing"


def test_the_migrators_credentials_come_from_the_environment(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("DB_MIGRATOR_USER", "hub_migrator")
    monkeypatch.setenv("DB_MIGRATOR_PASSWORD", "its-password")

    assert servers.migrator_credentials(None) == ("hub_migrator", "its-password")


def test_local_development_migrates_as_its_one_role(settings, monkeypatch):
    """``DEBUG`` (a developer's machine, compose's Postgres): one role does everything, as in db-bootstrap's local
    mode."""
    settings.DEBUG = True
    monkeypatch.setenv("DB_MIGRATOR_USER", "")
    monkeypatch.setenv("DB_MIGRATOR_PASSWORD", "")
    default = connections.settings["default"]

    assert servers.migrator_credentials(None) == (default["USER"], default["PASSWORD"])


def test_the_settings_own_server_stays_while_a_hub_without_a_cluster_lives_on_it(make_cluster, make_hub):
    cluster = make_cluster("open")
    make_hub(names.hub_db_name(control(), uuid.uuid7()))  # on the settings' own server
    make_hub(names.hub_db_name(control(), uuid.uuid7()), cluster=cluster)

    assert [target.name for target in servers.clusters_to_migrate()] == ["", cluster.name]


def test_a_template_is_made_on_the_server_it_is_asked_for(template_name, opened_at, monkeypatch):
    target = replace(servers.clusters_to_migrate()[0], host=same_server_by_another_name())
    platform = hub_templates.Template(db_name=template_name(), apps=PLATFORM)
    hubs.bootstrap_template(platform.db_name)
    template = hub_templates.Template(db_name=template_name(), apps=PLATFORM, source=platform.db_name)
    ops_hosts = []
    connect = psycopg.connect

    def watched(*args, **kwargs):
        if kwargs.get("dbname") == hub_templates.OPS_DATABASE:
            ops_hosts.append(kwargs.get("host"))
        return connect(*args, **kwargs)

    monkeypatch.setattr(psycopg, "connect", watched)

    hub_templates.ensure_template(template, target=target)

    assert hubs.table_names(template.db_name) == tables_of(PLATFORM)
    assert ops_hosts and set(ops_hosts) == {target.host}  # CREATE DATABASE on that server
    assert {name for host, name in opened_at if host == target.host} == {template.db_name}
    assert not [name for host, name in opened_at if name == template.db_name and host != target.host]


def test_a_hub_on_a_cluster_is_migrated_through_that_clusters_writer(new_database, make_cluster, make_hub, opened_at):
    cluster = make_cluster("other-name", host=same_server_by_another_name())
    hub = make_hub(new_database, cluster=cluster)

    schema.ensure_schema(hub)

    assert {host for host, name in opened_at if name == new_database} == {cluster.host}
    assert hubs.table_names(new_database) == tables_of(PLATFORM)
