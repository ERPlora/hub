"""The registry in control (PLAN-DB §2; plan 2026-10-22-fase-2-tenencia §3, S1).

``Hub`` and ``DemoCode`` moved from ``base`` to ``control`` keeping their tables (``base_hub``, ``base_democode``);
``Hub`` gains where its data lives (``db_name``: empty while it shares control's database, phase 1 until S5), its
schema (``schema_state``, ``schema_apps``), its ``cluster`` and ``is_platform``. ``Cluster`` and ``HubDue`` are new.
"""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

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
    assert (cluster.max_hubs, cluster.secret_name) == (0, "")
    assert str(cluster) == "erplora-prod (writer.example:5432)"
    hub = Hub.objects.create(slug="acme", cluster=cluster)
    assert hub.cluster == cluster


def test_the_code_of_before_still_inserts_a_cluster():
    """``max_hubs`` and ``secret_name`` have their default in the database (expand): 0 is no limit, empty the
    environment's own credentials."""
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO control_cluster (id, name, host, port, pooler_host, pooler_port, is_open, created_at) "
            "VALUES (%s, 'old-code', 'writer.example', 5432, '127.0.0.1', 6432, true, now())",
            [uuid.uuid7()],
        )
    cluster = Cluster.objects.get(name="old-code")

    assert (cluster.max_hubs, cluster.secret_name) == (0, "")


def test_a_hub_is_due_once_keyed_by_the_hub():
    from django.utils import timezone

    hub = Hub.objects.create(slug="acme")
    due = HubDue.objects.create(hub=hub, due_at=timezone.now())

    assert due.pk == hub.pk
    assert (due.lease_until, due.fiscal_oldest_pending_at, due.lease_owner) == (None, None, "")


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
        assert str(Cluster._meta.get_field("max_hubs").verbose_name) == "máximo de hubs"
        assert str(Cluster._meta.get_field("max_hubs").help_text) == "0 = sin límite."
        assert str(Cluster._meta.get_field("secret_name").verbose_name) == "secreto de credenciales"
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


# ── The copies of a hub's data and its nightly use (round 2026-10-30 of PLAN-DB, S2b) ────────────────────────────────


def test_a_dump_is_kept_by_its_key_newest_first():
    from control.models import HubDump

    hub = Hub.objects.create(slug="acme", db_name="hub_test_dump")
    older = HubDump.objects.create(
        hub=hub, kind=HubDump.Kind.RESET, key="k/20261030T100000Z-reset.dump", bytes=10, created_at="2026-10-30T10:00Z"
    )
    newer = HubDump.objects.create(
        hub=hub,
        kind=HubDump.Kind.OFFBOARDING,
        key="k/20261031T100000Z-offboarding.dump",
        bytes=0,
        created_at="2026-10-31T10:00Z",
        requested_by="Olga",
    )

    assert list(hub.dumps.all()) == [newer, older]
    assert newer.id.version == 7
    with pytest.raises(IntegrityError), transaction.atomic():
        HubDump.objects.create(hub=hub, kind="reset", key=older.key, bytes=1, created_at="2026-10-31T11:00Z")


def test_a_hub_without_a_reset_asked_has_none_and_one_asked_keeps_its_sections():
    hub = Hub.objects.create(slug="acme")
    hub.refresh_from_db()
    assert (hub.reset_requested_at, hub.reset_sections) == (None, None)

    Hub.objects.filter(pk=hub.pk).update(reset_requested_at="2026-10-31T10:00Z", reset_sections={"apps": ["table"]})
    hub.refresh_from_db()

    assert hub.reset_sections == {"apps": ["table"]}


def test_a_day_of_use_is_one_row_per_hub_and_day():
    from control.models import HubUsageDaily

    hub = Hub.objects.create(slug="acme", db_name="hub_test_usage")
    HubUsageDaily.objects.create(hub=hub, day="2026-10-30", db_bytes=1, measured_at="2026-10-31T00:15Z")

    with pytest.raises(IntegrityError), transaction.atomic():
        HubUsageDaily.objects.create(hub=hub, day="2026-10-30", db_bytes=2, measured_at="2026-10-31T00:16Z")
    row = HubUsageDaily.objects.get()
    assert (row.s3_bytes, row.active_users_1d, row.active_users_30d) == (0, 0, 0)


def test_a_person_counts_once_a_day_on_a_hub():
    from control.models import HubVisit

    HubVisit.objects.bulk_create(
        [HubVisit(host="acme", day="2026-10-30", saas_user_id="u1")] * 2, ignore_conflicts=True
    )
    HubVisit.objects.bulk_create([HubVisit(host="acme", day="2026-10-31", saas_user_id="u1")], ignore_conflicts=True)

    assert HubVisit.objects.count() == 2


def test_the_activity_of_a_day_is_one_row_per_hub_and_day_from_zero():
    from control.models import HubActivityDaily

    hub = Hub.objects.create(slug="acme", db_name="hub_test_activity")
    HubActivityDaily.objects.create(hub=hub, day="2026-10-30")

    with pytest.raises(IntegrityError), transaction.atomic():
        HubActivityDaily.objects.create(hub=hub, day="2026-10-30")
    row = HubActivityDaily.objects.get()
    assert (row.requests, row.peak_connections, row.busy_requests) == (0, 0, 0)


def test_a_visit_says_when_its_person_was_last_seen_or_nothing_yet():
    from control.models import HubVisit

    visit = HubVisit.objects.create(host="acme", day="2026-10-30", saas_user_id="u1")
    assert visit.last_seen_at is None

    HubVisit.objects.filter(pk=visit.pk).update(last_seen_at="2026-10-30T10:00Z")
    visit.refresh_from_db()
    assert visit.last_seen_at.isoformat() == "2026-10-30T10:00:00+00:00"


def test_a_night_of_measuring_is_one_row_per_day():
    from control.models import UsageRun

    UsageRun.objects.create(day="2026-10-30", started_at="2026-10-31T00:15Z")

    with pytest.raises(IntegrityError), transaction.atomic():
        UsageRun.objects.create(day="2026-10-30", started_at="2026-10-31T00:16Z")
    assert UsageRun.objects.get().finished_at is None


def test_the_copies_and_the_use_are_in_spanish():
    from django.utils import translation

    from control.models import HubDump, HubUsageDaily, HubVisit, UsageRun

    with translation.override("es"):
        assert str(HubDump._meta.verbose_name_plural) == "copias de los datos"
        assert [str(label) for label in HubDump.Kind.labels] == ["Antes de restablecer", "Al darse de baja"]
        assert str(HubDump._meta.get_field("bytes").verbose_name) == "tamaño (bytes)"
        assert str(HubDump._meta.get_field("requested_by").verbose_name) == "pedida por"
        assert str(HubUsageDaily._meta.verbose_name_plural) == "uso diario de los hubs"
        assert str(HubVisit._meta.verbose_name_plural) == "entradas diarias"
        assert str(UsageRun._meta.verbose_name_plural) == "mediciones nocturnas"
        assert str(Hub._meta.get_field("reset_requested_at").verbose_name) == "restablecimiento pedido"
        assert str(Hub._meta.get_field("reset_sections").verbose_name) == "restablecimiento"


# ── A hub's move to another cluster (round 2026-10-30b of PLAN-DB, decision 3; tranche S7) ──────────────────────────


def test_a_hub_is_moving_while_it_names_where_and_its_cluster_cannot_go_meanwhile():
    from django.db.models import ProtectedError

    target = Cluster.objects.create(name="next", host="writer-next.example")
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY)
    assert hub.moving_to is None

    hub.moving_to = target
    hub.save(update_fields=["moving_to"])

    assert list(target.incoming.all()) == [hub]
    with pytest.raises(ProtectedError):
        target.delete()


def test_a_moved_copy_is_one_per_database_and_server_the_settings_own_included():
    from control.models import MovedCopy

    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY)
    old = Cluster.objects.create(name="old", host="writer-old.example")
    name = f"{connection.settings_dict['NAME']}_move_{hub.id.hex}"
    MovedCopy.objects.create(hub=hub, cluster=old, db_name=name, moved_at="2026-10-31T10:00Z")
    MovedCopy.objects.create(hub=hub, cluster=None, db_name=name, moved_at="2026-10-31T11:00Z")

    for cluster in (old, None):
        with pytest.raises(IntegrityError), transaction.atomic():
            MovedCopy.objects.create(hub=hub, cluster=cluster, db_name=name, moved_at="2026-10-31T12:00Z")
    hub.delete()
    assert not MovedCopy.objects.exists()


def test_the_move_is_in_spanish():
    from django.utils import translation

    from control.models import MovedCopy

    with translation.override("es"):
        assert str(Hub._meta.get_field("moving_to").verbose_name) == "moviéndose a"
        assert str(MovedCopy._meta.verbose_name_plural) == "copias tras mover"


def test_a_leftover_of_an_undone_move_is_one_per_database_and_server_and_goes_with_its_hub():
    from control.models import LeftoverDatabase

    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    there = Cluster.objects.create(name="there", host="writer-there.example")
    LeftoverDatabase.objects.create(hub=hub, cluster=there, db_name=hub.db_name, noted_at="2026-10-31T10:00Z")
    with pytest.raises(IntegrityError), transaction.atomic():
        LeftoverDatabase.objects.create(hub=hub, cluster=there, db_name=hub.db_name, noted_at="2026-10-31T11:00Z")
    hub.delete()
    assert not LeftoverDatabase.objects.exists()


def test_a_moves_note_keeps_the_origins_schema_record_and_a_hub_says_when_its_move_was_asked_to_be_undone():
    from django.utils import translation

    from control.models import MovedCopy

    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY)
    note = MovedCopy.objects.create(
        hub=hub, db_name=f"hub_move_{hub.id.hex}", schema_state="behind", schema_apps={"base": "0001_initial"}
    )
    note.refresh_from_db()
    hub.refresh_from_db()
    assert (note.moved_at, note.schema_state, note.schema_apps) == (None, "behind", {"base": "0001_initial"})
    assert hub.move_undo_asked_at is None
    with translation.override("es"):
        assert str(Hub._meta.get_field("move_undo_asked_at").verbose_name) == "deshacer el traslado pedido"
