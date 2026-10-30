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
    assert (hub.attempts, hub.last_error, hub.next_attempt_at) == (0, "", None)


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


def test_a_hub_is_prepared_in_steps_and_ends_in_steps():
    """PLAN-DB §6: ``requested → creating → migrating → seeding → ready``, ``failed`` to retry; the way out of a
    business (``archiving``, ``dropping``) is declared for S2b."""
    assert [Hub.Status(value) for value in ("creating", "migrating", "seeding", "archiving", "dropping")] == [
        Hub.Status.CREATING,
        Hub.Status.MIGRATING,
        Hub.Status.SEEDING,
        Hub.Status.ARCHIVING,
        Hub.Status.DROPPING,
    ]
    assert max(len(value) for value in Hub.Status.values) <= Hub._meta.get_field("status").max_length


def test_a_failed_preparation_keeps_its_attempts_its_error_and_its_next_attempt():
    from django.utils import timezone

    hub = Hub.objects.create(slug="acme")
    assert (hub.attempts, hub.last_error, hub.next_attempt_at) == (0, "", None)

    later = timezone.now()
    Hub.objects.filter(pk=hub.pk).update(
        status=Hub.Status.FAILED, attempts=2, last_error="The template is in use.", next_attempt_at=later
    )
    hub.refresh_from_db()

    assert (hub.status, hub.attempts, hub.last_error, hub.next_attempt_at) == (
        "failed",
        2,
        "The template is in use.",
        later,
    )


def test_mark_due_makes_a_hub_due_and_only_ever_brings_it_forward():
    import datetime as dt

    from django.utils import timezone

    hub = Hub.objects.create(slug="acme")
    now = timezone.now()

    HubDue.mark_due(hub, now)
    HubDue.mark_due(hub, now + dt.timedelta(minutes=5))
    assert HubDue.objects.get(pk=hub.pk).due_at == now

    HubDue.mark_due(hub, now - dt.timedelta(minutes=1))
    assert HubDue.objects.get(pk=hub.pk).due_at == now - dt.timedelta(minutes=1)
    assert HubDue.objects.filter(pk=hub.pk).count() == 1


def test_mark_due_without_a_time_is_now():
    from django.utils import timezone

    hub = Hub.objects.create(slug="acme")
    before = timezone.now()

    HubDue.mark_due(hub)

    assert before <= HubDue.objects.get(pk=hub.pk).due_at <= timezone.now()


def test_its_words_are_translated():
    from django.apps import apps
    from django.utils import translation

    from base import registry
    from base.models import HubIdentity

    with translation.override("es"):
        assert str(apps.get_app_config("control").verbose_name) == "Control"
        assert str(Hub._meta.get_field("db_name").verbose_name) == "base de datos"
        assert str(Hub._meta.get_field("schema_state").verbose_name) == "esquema"
        assert [str(label) for label in Hub.SchemaState.labels] == ["Al día", "Atrasado"]
        assert str(Hub._meta.get_field("schema_apps").verbose_name) == "apps creadas"
        assert str(Hub._meta.get_field("is_platform").verbose_name) == "hub de la plataforma"
        assert str(Cluster._meta.verbose_name_plural) == "clústeres"
        assert str(Cluster._meta.get_field("host").verbose_name) == "host del escritor"
        assert str(Cluster._meta.get_field("pooler_port").verbose_name) == "puerto de PgBouncer"
        assert str(Cluster._meta.get_field("is_open").verbose_name) == "abierto a hubs nuevos"
        assert str(HubDue._meta.verbose_name_plural) == "hubs con trabajo pendiente"
        assert str(HubDue._meta.get_field("lease_until").verbose_name) == "reservado hasta"
        assert str(HubIdentity._meta.verbose_name) == "identidad del hub"
        assert registry.unavailable().message == "Este hub no se puede abrir ahora; inténtalo más tarde."
        assert [str(Hub.Status(value).label) for value in ("creating", "migrating", "seeding")] == [
            "Creando",
            "Migrando",
            "Sembrando datos",
        ]
        assert [str(Hub.Status(value).label) for value in ("archiving", "dropping")] == ["Archivando", "Borrando"]
        assert str(Hub._meta.get_field("attempts").verbose_name) == "intentos"
        assert str(Hub._meta.get_field("last_error").verbose_name) == "último error"
        assert str(Hub._meta.get_field("next_attempt_at").verbose_name) == "próximo intento"
