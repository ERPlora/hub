"""The templates every new hub is cloned from: which they are, and making each or bringing it up to date on its
server."""

import threading

import psycopg
import pytest
from django.db import connections

from base import catalog
from base.models.activation import AppActivation
from base.tenancy import names
from base.tenancy.bootstrap import admin_conninfo as bootstrap_conninfo
from base.tenancy.migrator import app_sets, hub_templates, schema, servers
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import (
    committed_database,
    make_cluster,
    make_database,
    make_hub,
    new_database,
    template_name,
)
from base.tenancy.tests.test_migrator import PLATFORM, control, leaves, migrate_to, tables_of

__all__ = ["committed_database", "make_cluster", "make_database", "make_hub", "new_database", "template_name"]


def database_oid(name: str) -> int | None:
    with hubs._maintenance() as conn:
        row = conn.execute("SELECT oid FROM pg_database WHERE datname = %s", [name]).fetchone()
    return None if row is None else row[0]


def rows(name: str, table: str) -> int:
    with hubs._maintenance(name) as conn:
        query = psycopg.sql.SQL("SELECT count(*) FROM {}").format(psycopg.sql.Identifier(table))
        return conn.execute(query).fetchone()[0]


def test_the_templates_are_the_platforms_and_one_per_vertical_cloned_from_it():
    """``hub_template_<vertical>`` = ``hub_template`` + the tables of ``template_apps(vertical)``; every template also
    carries every portable app's (``portable_apps``), so a sign-up is the clone alone, never ~60 s of migrations on
    Fargate."""
    platform, *verticals = hub_templates.templates()
    portable = set(app_sets.portable_apps())
    every = portable

    assert platform.db_name == names.template_db_name(control()) and platform.source is None
    assert set(platform.apps) == set(PLATFORM) | every
    assert [template.db_name for template in verticals] == [
        names.template_db_name(control(), vertical) for vertical in catalog.verticals.known_verticals()
    ]
    for vertical, template in zip(catalog.verticals.known_verticals(), verticals, strict=True):
        wanted = set(catalog.verticals.template_apps(vertical))
        assert template.source == platform.db_name
        assert set(template.apps) == set(PLATFORM) | every | (wanted & portable)
        assert set(template.left_out) == wanted - portable
        # A vertical's template holds its whole list: a hair salon is born with its staff.
        assert template.left_out == ()


def platform_and_vertical(template_name, apps=("tax",)) -> tuple[hub_templates.Template, hub_templates.Template]:
    """A platform's template as db-bootstrap leaves it, migrated, and a vertical's (not made yet) cloned from it."""
    platform = hub_templates.Template(db_name=template_name(), apps=PLATFORM)
    hubs.bootstrap_template(platform.db_name)
    hub_templates.ensure_template(platform)
    return platform, hub_templates.Template(db_name=template_name(), apps=(*PLATFORM, *apps), source=platform.db_name)


def test_a_missing_platform_template_is_refused_naming_its_server(template_name, make_cluster):
    """Only db-bootstrap makes a platform's template, with its roles, grants and default privileges: a plain one would
    let every role of the cluster in, and stay so."""
    template = hub_templates.Template(db_name=template_name(), apps=PLATFORM)
    cluster = make_cluster("second")
    on_cluster = servers.cluster_target(cluster)

    with pytest.raises(hub_templates.TemplateMissing, match="db-bootstrap") as settings_own:
        hub_templates.ensure_template(template)
    with pytest.raises(hub_templates.TemplateMissing, match=f"cluster {cluster.name}"):
        hub_templates.ensure_template(template, target=on_cluster)

    assert "the settings' server" in str(settings_own.value)
    assert settings_own.value.code == "template_missing"
    assert database_oid(template.db_name) is None


def test_a_verticals_template_is_cloned_from_the_platforms_with_every_app_off(template_name):
    platform, vertical = platform_and_vertical(template_name)

    applied = hub_templates.ensure_template(vertical)

    assert applied and all(name.split(".")[0] not in PLATFORM for name in applied)  # the platform came cloned
    assert hubs.table_names(vertical.db_name) == tables_of(vertical.apps)
    assert rows(vertical.db_name, AppActivation._meta.db_table) == 0  # a template has every app off
    hubs.assert_nobody_on(platform.db_name)  # nobody connected: both clonable
    hubs.assert_nobody_on(vertical.db_name)


def test_a_verticals_template_gets_its_platforms_access_never_publics(template_name):
    """``CREATE DATABASE … TEMPLATE`` copies no grant of the database: PUBLIC would connect to the new one."""
    platform, vertical = platform_and_vertical(template_name)

    hub_templates.ensure_template(vertical)

    assert hubs.database_access(vertical.db_name) == hubs.database_access(platform.db_name)
    with hubs._maintenance() as conn:
        allowed = conn.execute(
            "SELECT has_database_privilege(%s, %s, 'CONNECT'), has_database_privilege(%s, %s, 'CONNECT')",
            ["pg_read_all_settings", vertical.db_name, hubs.TEMPLATE_GRANTEE, vertical.db_name],
        ).fetchone()
    assert allowed == (False, True)


def test_a_verticals_template_made_open_before_is_closed_on_the_next_run(template_name):
    platform, vertical = platform_and_vertical(template_name)
    with hubs._maintenance() as conn:  # as a template made before this fix: PUBLIC's default access, nobody else's
        conn.execute(
            psycopg.sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                psycopg.sql.Identifier(vertical.db_name), psycopg.sql.Identifier(platform.db_name)
            )
        )
        conn.execute(
            psycopg.sql.SQL("GRANT CREATE ON DATABASE {} TO pg_read_all_settings").format(
                psycopg.sql.Identifier(vertical.db_name)
            )
        )

    hub_templates.ensure_template(vertical)

    assert hubs.database_access(vertical.db_name) == hubs.database_access(platform.db_name)


def test_a_clone_waits_for_whoever_holds_its_source_a_bounded_number_of_times(template_name, monkeypatch):
    """55006 («source database … is being accessed by other users»): PostgreSQL itself waits 5 s."""
    platform, vertical = platform_and_vertical(template_name)
    monkeypatch.setattr(hub_templates, "CLONE_RETRY_DELAY", 0.2)
    holder = psycopg.connect(**(bootstrap_conninfo() | {"dbname": platform.db_name}), autocommit=True)
    releaser = threading.Timer(6.5, holder.close)  # past the 5 s of PostgreSQL's own wait: one failed attempt
    releaser.start()
    try:
        hub_templates.ensure_template(vertical)
    finally:
        releaser.cancel()
        holder.close()

    assert hubs.table_names(vertical.db_name) == tables_of(vertical.apps)


def test_a_clone_gives_up_after_its_attempts(template_name, monkeypatch):
    platform, vertical = platform_and_vertical(template_name)
    monkeypatch.setattr(hub_templates, "CLONE_ATTEMPTS", 2)
    monkeypatch.setattr(hub_templates, "CLONE_RETRY_DELAY", 0)
    attempts = []
    real = hub_templates._clone_once

    def counted(*args, **kwargs):
        attempts.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(hub_templates, "_clone_once", counted)
    with psycopg.connect(**(bootstrap_conninfo() | {"dbname": platform.db_name}), autocommit=True):
        with pytest.raises(psycopg.errors.ObjectInUse):
            hub_templates.ensure_template(vertical)

    assert len(attempts) == 2
    assert database_oid(vertical.db_name) is None


def test_a_template_whose_list_changed_is_brought_up_to_date_never_rebuilt(template_name):
    name = template_name()
    hubs.create_database(name)
    hub_templates.ensure_template(hub_templates.Template(db_name=name, apps=(*PLATFORM, "tax")))
    oid = database_oid(name)

    # tax left the vertical's list and customer joined it.
    applied = hub_templates.ensure_template(hub_templates.Template(db_name=name, apps=(*PLATFORM, "customer")))

    assert {migration.split(".")[0] for migration in applied} == {"customer"}
    assert database_oid(name) == oid
    assert hubs.table_names(name) == tables_of({*PLATFORM, "tax", "customer"})


def test_an_app_that_left_a_templates_list_is_still_brought_to_the_leaf(template_name):
    name = template_name()
    hubs.create_database(name)
    hub_templates.ensure_template(hub_templates.Template(db_name=name, apps=PLATFORM))
    migrate_to(name, ("tax", "0001_initial"))  # on an older list, at an older code

    applied = hub_templates.ensure_template(hub_templates.Template(db_name=name, apps=PLATFORM))

    assert f"tax.{leaves()['tax']}" in applied


def test_a_template_another_run_created_meanwhile_is_migrated_not_refused(template_name, monkeypatch):
    """Two overlapping deploys may both find it missing: the second clone (42P04) is not a failure."""
    platform, vertical = platform_and_vertical(template_name)
    hubs.create_database(vertical.db_name)
    exists = hub_templates.database_exists
    monkeypatch.setattr(
        hub_templates, "database_exists", lambda name, **kwargs: False if name == vertical.db_name else exists(name, **kwargs)
    )

    assert "base.0001_initial" in hub_templates.ensure_template(vertical)
    assert hubs.table_names(vertical.db_name) == tables_of(vertical.apps)


def test_pending_lists_what_a_template_lacks_and_applies_nothing(template_name):
    template = hub_templates.Template(db_name=template_name(), apps=(*PLATFORM, "tax"))
    hubs.create_database(template.db_name)
    hub_templates.ensure_template(template)
    leaf = leaves()["tax"]
    with hubs._maintenance(template.db_name) as conn:  # as if the code had just gained tax's leaf
        conn.execute("DELETE FROM django_migrations WHERE app = 'tax' AND name = %s", [leaf])

    assert hub_templates.pending_template(template) == [f"tax.{leaf}"]
    assert hub_templates.pending_template(template) == [f"tax.{leaf}"]
    hubs.assert_nobody_on(template.db_name)


def test_pending_of_a_missing_template_is_what_making_it_applies_and_creates_nothing(template_name):
    template = hub_templates.Template(db_name=template_name(), apps=PLATFORM)
    leaf = leaves()

    pending = hub_templates.pending_template(template)

    assert {"base.0001_initial", f"base.{leaf['base']}", f"live.{leaf['live']}"} <= set(pending)
    assert database_oid(template.db_name) is None


def test_the_migrator_leaves_no_alias_of_its_own_registered(template_name, new_database, make_hub):
    """Each ``__ddl`` alias is forgotten once used: one left in the settings breaks every later test case, and in a
    long process every hub would leave one."""
    platform, vertical = platform_and_vertical(template_name)
    hub_templates.ensure_template(vertical)
    hub_templates.pending_template(vertical)
    schema.ensure_schema(make_hub(new_database))

    assert [alias for alias in connections.settings if alias.endswith(names.DDL_SUFFIX)] == []
