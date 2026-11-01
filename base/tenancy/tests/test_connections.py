"""Hot registration of a hub's alias (PLAN-DB §4 and §5; plan 2026-10-22-fase-2-tenencia §4, step 4).

A hub's alias is copied from the static ``hub_template`` alias (PgBouncer in transaction mode: no pool,
``CONN_MAX_AGE`` 0, no server-side cursors, no prepared statements) with the hub's database as ``NAME``, and swapped
in as a new ``connections.settings`` dict under a lock: the dict other threads are reading is never changed in place.
A hub without a database of its own (``db_name=""``) stays on ``default``; a template is never a hub's database, and
working in a hub leaves no connection open to the template it was cloned from (PLAN-DB §14.6).
"""

import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from django.db import connections as django_connections

from base.tenancy import connections, names
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs


def pgbouncer_safe(settings: dict) -> bool:
    """What PgBouncer in transaction mode needs of an alias (``tests/test_guardrails.py``, ``database_problems``).

    ``prepare_threshold`` must be there and ``None``: Django does not set it and psycopg 3 prepares a statement on
    its fifth run, which PgBouncer with ``max_prepared_statements=0`` (docker/pgbouncer-entrypoint.sh) then loses
    («prepared statement _pg3_N does not exist»)."""
    return (
        settings["CONN_MAX_AGE"] == 0
        and "pool" not in settings["OPTIONS"]
        and settings["DISABLE_SERVER_SIDE_CURSORS"] is True
        and "prepare_threshold" in settings["OPTIONS"]
        and settings["OPTIONS"]["prepare_threshold"] is None
        and not settings.get("ATOMIC_REQUESTS")
    )


@pytest.fixture(autouse=True)
def restored_settings(monkeypatch):
    """Whatever a test registers is gone after it (the same swap the module does)."""
    monkeypatch.setattr(django_connections, "settings", django_connections.settings)


def hub_with_database(**fields):
    hub_id = uuid.uuid7()
    return SimpleNamespace(
        id=hub_id, slug="acme", db_name=names.hub_db_name(connections.control_name(), hub_id), cluster=None, **fields
    )


def test_the_template_alias_goes_through_pgbouncer_safely():
    template = django_connections.settings[connections.TEMPLATE_ALIAS]

    assert template["CONN_MAX_AGE"] == 0
    assert "pool" not in template["OPTIONS"]
    assert template["DISABLE_SERVER_SIDE_CURSORS"] is True
    assert "prepare_threshold" in template["OPTIONS"] and template["OPTIONS"]["prepare_threshold"] is None
    assert pgbouncer_safe(template)
    # Named after the control database of the settings (hub_template, pre_hub_template); config/tests checks it.
    assert template["NAME"].endswith("_template")


def test_a_hub_with_its_database_gets_an_alias_copied_from_the_template():
    hub = hub_with_database()
    before = django_connections.settings
    frozen = dict(before)

    alias = connections.register_hub_alias(hub)

    assert alias == f"hub_{hub.id.hex}"
    registered = django_connections.settings[alias]
    template = django_connections.settings[connections.TEMPLATE_ALIAS]
    assert registered["NAME"] == hub.db_name
    assert {key: value for key, value in registered.items() if key != "NAME"} == {
        key: value for key, value in template.items() if key != "NAME"
    }
    assert registered["OPTIONS"] is not template["OPTIONS"]
    # A new dict was swapped in; the one other threads may be reading is as it was.
    assert django_connections.settings is not before
    assert before == frozen
    assert pgbouncer_safe(registered)


def test_registering_again_changes_nothing():
    hub = hub_with_database()
    connections.register_hub_alias(hub)
    after_first = django_connections.settings

    assert connections.register_hub_alias(hub) == f"hub_{hub.id.hex}"
    assert django_connections.settings is after_first


def test_an_alias_never_moves_to_another_database_while_the_process_runs():
    hub = hub_with_database()
    connections.register_hub_alias(hub)
    hub.db_name = names.demo_db_name(connections.control_name(), hub.id)

    with pytest.raises(connections.HubAliasConflict):
        connections.register_hub_alias(hub)


def test_two_threads_registering_the_same_hub_register_it_once():
    hub = hub_with_database()
    swaps = []
    barrier = threading.Barrier(2)
    seen = []

    original_copy = connections._copied

    def slow_copy(*args, **kwargs):
        # Wide enough for the other thread to look for the alias meanwhile.
        time.sleep(0.05)
        swaps.append(1)
        return original_copy(*args, **kwargs)

    connections._copied = slow_copy
    try:

        def register():
            barrier.wait()
            seen.append(connections.register_hub_alias(hub))

        threads = [threading.Thread(target=register) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        connections._copied = original_copy

    assert seen == [f"hub_{hub.id.hex}"] * 2
    assert len(swaps) == 1


def test_a_business_without_its_own_database_has_no_alias_and_never_gets_default():
    from base.tenancy.context import HubWithoutDatabase

    hub = SimpleNamespace(id=uuid.uuid7(), slug="a", db_name="", cluster=None)
    before = django_connections.settings

    with pytest.raises(HubWithoutDatabase):
        connections.alias_for(hub)
    with pytest.raises(HubWithoutDatabase):
        connections.open_hub_alias(hub)
    assert django_connections.settings is before


def test_a_name_that_is_no_hubs_database_registers_nothing():
    hub = SimpleNamespace(id=uuid.uuid7(), slug="acme", db_name="postgres", cluster=None)
    before = django_connections.settings

    with pytest.raises(names.InvalidDatabaseName):
        connections.register_hub_alias(hub)
    assert django_connections.settings is before


def test_a_hub_on_a_cluster_reaches_its_clusters_pgbouncer():
    cluster = SimpleNamespace(pooler_host="10.0.0.7", pooler_port=6440)
    hub = hub_with_database()
    hub.cluster = cluster

    alias = connections.register_hub_alias(hub)

    assert django_connections.settings[alias]["HOST"] == "10.0.0.7"
    assert django_connections.settings[alias]["PORT"] == 6440


def test_the_migrators_alias_is_the_same_database_reached_directly_without_a_pool():
    hub = hub_with_database()

    alias = connections.register_ddl_alias(hub.db_name)

    assert alias == f"{hub.db_name}__ddl"
    registered = django_connections.settings[alias]
    control = django_connections.settings["default"]
    assert registered["NAME"] == hub.db_name
    assert (registered["HOST"], registered["PORT"]) == (control["HOST"], control["PORT"])
    assert registered["CONN_MAX_AGE"] == 0
    assert "pool" not in registered["OPTIONS"]
    # Direct to the writer, no PgBouncer: it may prepare statements (guardrails exempt __ddl aliases).
    assert registered["DISABLE_SERVER_SIDE_CURSORS"] is True


def test_the_template_is_never_connected_to_by_registering():
    connections.register_hub_alias(hub_with_database())

    assert django_connections[connections.TEMPLATE_ALIAS].connection is None


@pytest.mark.parametrize("vertical", [None, "test", "hair_salon"])
def test_a_hub_naming_a_template_never_gets_an_alias(vertical):
    # A template's database is only cloned: a connection to it makes CREATE DATABASE … TEMPLATE fail (55006), and a
    # write in it would reach every hub cloned after. Only the migrator reaches it (``register_ddl_alias``).
    template = names.template_db_name(connections.control_name(), vertical)
    hub = SimpleNamespace(id=uuid.uuid7(), slug="acme", db_name=template, cluster=None)
    before = django_connections.settings

    with pytest.raises(names.InvalidDatabaseName, match="template"):
        connections.register_hub_alias(hub)
    with pytest.raises(names.InvalidDatabaseName):
        connections.alias_for(hub)
    assert django_connections.settings is before


def _sessions_on(database: str) -> int:
    """How many sessions of the server are connected to ``database`` now, this test's included (``pg_stat_activity``)."""
    with django_connections["default"].cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", [database])
        return cursor.fetchone()[0]


def _nobody_on(database: str, *, wait: float = 5.0) -> bool:
    """Whether every session on ``database`` ends within ``wait`` seconds: a connection just closed (a previous test's
    clone of the template) still counts for a moment, as its server process leaves ``pg_stat_activity`` after
    ``close()`` returns (hub#487, the CI of hub#471)."""
    deadline = time.monotonic() + wait
    while _sessions_on(database) and time.monotonic() < deadline:
        time.sleep(0.05)
    return _sessions_on(database) == 0


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_working_in_a_hub_leaves_no_connection_open_to_its_template(hub_a, hub_databases):
    assert _nobody_on(hub_databases.template)
    with use_hub(hub_a):
        with django_connections[hubs.HUB_A_ALIAS].cursor() as cursor:
            cursor.execute("SELECT 1")

    assert _sessions_on(hub_databases.a) >= 1
    assert _nobody_on(hub_databases.template)
    assert django_connections[connections.TEMPLATE_ALIAS].connection is None
    # No alias of this process reaches the template: the migrator's, which built it, was forgotten after.
    assert not [
        alias for alias, settings in django_connections.settings.items() if settings["NAME"] == hub_databases.template
    ]


@pytest.mark.django_db(transaction=True)
def test_a_thread_of_the_worker_closes_every_connection_it_opened_when_its_piece_ends():
    """The worker's slow passes run in threads of their own (base.worker.Background): each piece leaves no connection
    of its thread open, control's included (review of round 3: one helper of the tenancy, not django.db in the worker)."""
    left_open: list[bool] = []

    def piece() -> None:
        django_connections["default"].ensure_connection()
        connections.close_this_threads_connections()
        left_open.append(django_connections["default"].connection is not None)

    thread = threading.Thread(target=piece)
    thread.start()
    thread.join(10)

    assert left_open == [False]
