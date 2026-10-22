"""The registry in control (PLAN-DB §2; plan 2026-10-22-fase-2-tenencia §3, S1).

``Hub`` and ``DemoCode`` moved from ``base`` to ``control`` keeping their tables (``base_hub``, ``base_democode``);
``Hub`` gains where its data lives (``db_name``: empty while it shares control's database, phase 1 until S5), its
schema (``schema_state``, ``schema_apps``), its ``cluster`` and ``is_platform``. ``Cluster`` and ``HubDue`` are new.
"""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from base.tenancy import names
from control.models import Cluster, DemoCode, Hub, HubDue

pytestmark = pytest.mark.django_db


def test_the_registry_keeps_its_tables():
    assert Hub._meta.db_table == "base_hub"
    assert DemoCode._meta.db_table == "base_democode"
    assert Hub._meta.app_label == DemoCode._meta.app_label == "control"


def test_a_new_hub_shares_controls_database_with_its_schema_current():
    hub = Hub.objects.create(slug="acme")
    hub.refresh_from_db()

    assert (hub.db_name, hub.schema_state, hub.schema_apps, hub.cluster, hub.is_platform) == (
        "",
        Hub.SchemaState.CURRENT,
        {},
        None,
        False,
    )


def test_the_code_of_before_still_inserts_a_hub():
    """The new columns have their default in the database: an INSERT that does not name them works (expand)."""
    hub_id = uuid.uuid7()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO base_hub (id, slug, name, country, timezone, language, vertical, status, is_demo, "
            "demo_session_key, state, state_version, created_at, updated_at) VALUES "
            "(%s, 'old-code', '', '', '', '', '', 'ready', false, '', '{}', 0, now(), now())",
            [hub_id],
        )
    hub = Hub.objects.get(pk=hub_id)

    assert (hub.db_name, hub.schema_state, hub.schema_apps, hub.is_platform) == ("", "current", {}, False)


def test_a_database_name_is_a_hubs_of_this_control_database():
    hub = Hub(slug="acme")
    hub.db_name = names.hub_db_name(connection.settings_dict["NAME"], hub.id)
    hub.full_clean()

    hub.db_name = "postgres"
    with pytest.raises(ValidationError) as caught:
        hub.full_clean()
    assert "db_name" in caught.value.error_dict


def test_a_cluster_is_named_once_and_says_where_its_pgbouncer_listens():
    cluster = Cluster.objects.create(name="erplora-prod", host="writer.example", pooler_host="127.0.0.1")
    cluster.refresh_from_db()

    assert (cluster.port, cluster.pooler_port, cluster.is_open, cluster.pk.version) == (5432, 6432, True, 7)
    assert str(cluster) == "erplora-prod"
    hub = Hub.objects.create(slug="acme", cluster=cluster)
    assert hub.cluster == cluster


def test_a_hub_is_due_once_keyed_by_the_hub():
    from django.utils import timezone

    hub = Hub.objects.create(slug="acme")
    due = HubDue.objects.create(hub=hub, due_at=timezone.now())

    assert due.pk == hub.pk
    assert (due.lease_until, due.fiscal_oldest_pending_at) == (None, None)
