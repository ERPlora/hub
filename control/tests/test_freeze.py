"""The freeze switch of control (hub#930; PLAN-DB round 2026-11-04e, «Congelar»).

While a database upgrade runs with Blue/Green nothing may change a schema (logical replication copies no DDL): ERPlora's
staff freezes the platform with ``control.freeze.set`` (the Hub admin, ``hubs.erplora.com/admin``) and lifts it the same
way. While it is on, the worker makes, drops and moves no database and sets up no app's tables, and ``migrate_hubs``
refuses to start (``base/tests/test_worker.py``, ``base/tests/test_migrate_hubs.py``); the relay, the tasks and the
sends to the AEAT go on. ``control.freeze.get`` says how it stands (who, since when, why) and how many hubs the worker
is still working on (their ``hub_due`` lease held): what the staff waits to see at 0 before creating the Blue/Green.

Only the platform's admins (staff and superuser) or the platform itself set it; support reads it; a customer neither.
Setting it is idempotent: a freeze asked while frozen keeps the freeze in course as it was, and a lift while lifted
changes nothing; each real change records its event in control's outbox, in the same transaction. One row at most.
"""

import datetime as dt
import uuid
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, connection, migrations, transaction
from django.utils import timezone
from live.context import system_context
from live.errors import PermissionDenied
from live.models import OutboxEvent

from base.registry import REGISTRY_SCOPE
from control import queries, services
from control.models import Freeze, Hub, HubDue
from control.schemas import FreezeGetIn, FreezeIn
from control.tests.test_services import as_actor, person

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_ctx():
    return as_actor(person("root", is_staff=True, is_superuser=True, first_name="Ana", last_name="Root"))


@pytest.fixture
def support_ctx():
    return as_actor(person("support", is_staff=True))


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("created_at")]


def freeze(ctx, reason: str = "Aurora upgrade with Blue/Green"):
    return services.freeze_set(ctx, FreezeIn(frozen=True, reason=reason))


def lift(ctx):
    return services.freeze_set(ctx, FreezeIn(frozen=False))


class TestGet:
    def test_never_set_it_is_not_frozen(self, support_ctx):
        out = queries.freeze_get(support_ctx, FreezeGetIn())

        assert (out.frozen, out.reason, out.since, out.by, out.working) == (False, "", None, "", 0)

    def test_it_counts_the_hubs_the_worker_still_works_on_and_no_lease_that_ran_out(self, support_ctx):
        now = timezone.now()
        working = Hub.objects.create(slug="acme", status=Hub.Status.CREATING)
        done = Hub.objects.create(slug="other", status=Hub.Status.FAILED)
        HubDue.objects.create(hub=working, due_at=now, lease_until=now + dt.timedelta(seconds=60), lease_owner="w1")
        HubDue.objects.create(hub=done, due_at=now, lease_until=now - dt.timedelta(seconds=1), lease_owner="w1")

        assert queries.freeze_get(support_ctx, FreezeGetIn()).working == 1

    def test_it_counts_the_separate_copies_the_worker_still_makes_under_their_own_lease(self, support_ctx):
        # A separate copy (hub#1213) makes a database without the hub's lease: the upgrade waits for it too.
        from control.models import RestoredCopy

        now = timezone.now()
        hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
        for lease_until in (now + dt.timedelta(seconds=60), now - dt.timedelta(seconds=1), None):
            RestoredCopy.objects.create(
                hub=hub,
                restore_point=now,
                db_name=f"hub_copy_{uuid.uuid7().hex}",
                asked_by="root",
                lease_owner="w1" if lease_until else "",
                lease_until=lease_until,
            )

        assert queries.freeze_get(support_ctx, FreezeGetIn()).working == 1

    def test_the_platform_reads_it_too(self):
        assert queries.freeze_get(system_context(REGISTRY_SCOPE), FreezeGetIn()).frozen is False

    @pytest.mark.parametrize("flags", [{}, {"is_superuser": True}])
    def test_a_customer_or_a_superuser_who_is_no_staff_may_not_read_it(self, flags):
        with pytest.raises(PermissionDenied):
            queries.freeze_get(as_actor(person("someone", **flags)), FreezeGetIn())


class TestSet:
    def test_a_platform_admin_freezes_with_why_and_its_event(self, admin_ctx, support_ctx):
        before = timezone.now()

        out = freeze(admin_ctx)

        row = Freeze.objects.get()
        assert (row.frozen, row.reason, row.by) == (True, "Aurora upgrade with Blue/Green", "Ana Root")
        assert row.since >= before
        assert (out.frozen, out.reason, out.by, out.since) == (True, row.reason, "Ana Root", row.since)
        assert events("control.freeze.started") == [{"reason": "Aurora upgrade with Blue/Green"}]
        # Support sees it as it is.
        seen = queries.freeze_get(support_ctx, FreezeGetIn())
        assert (seen.frozen, seen.reason, seen.by, seen.since) == (True, row.reason, "Ana Root", row.since)

    def test_freezing_again_keeps_the_freeze_in_course_as_it_was_and_records_nothing(self, admin_ctx):
        first = freeze(admin_ctx)
        other = as_actor(person("root2", is_staff=True, is_superuser=True))

        again = freeze(other, reason="something else")

        row = Freeze.objects.get()
        assert (row.frozen, row.reason, row.by, row.since) == (True, first.reason, "Ana Root", first.since)
        assert (again.reason, again.by, again.since) == (first.reason, "Ana Root", first.since)
        assert len(events("control.freeze.started")) == 1

    def test_lifting_it_says_who_and_when_and_records_how_long_it_lasted(self, admin_ctx):
        started = freeze(admin_ctx)
        lifter = as_actor(person("ops", is_staff=True, is_superuser=True))

        out = lift(lifter)

        row = Freeze.objects.get()
        assert (row.frozen, row.reason, row.by) == (False, "", "ops")
        assert row.since >= started.since
        assert (out.frozen, out.by, out.since) == (False, "ops", row.since)
        assert events("control.freeze.lifted") == [{"frozen_since": started.since.isoformat()}]

    def test_lifting_what_is_not_frozen_changes_nothing_and_records_nothing(self, admin_ctx):
        out = lift(admin_ctx)

        assert out.frozen is False
        assert not Freeze.objects.filter(frozen=True).exists()
        assert events("control.freeze.lifted") == []
        assert events("control.freeze.started") == []

    def test_it_can_be_frozen_again_after_a_lift(self, admin_ctx):
        freeze(admin_ctx)
        lift(admin_ctx)

        freeze(admin_ctx, reason="second window")

        assert Freeze.objects.get().reason == "second window"
        assert len(events("control.freeze.started")) == 2

    def test_the_platform_itself_may_freeze_and_lift(self):
        platform = system_context(REGISTRY_SCOPE)

        assert freeze(platform).by == "system"
        assert lift(platform).frozen is False

    @pytest.mark.parametrize("flags", [{"is_staff": True}, {}, {"is_superuser": True}])
    def test_support_a_customer_or_a_superuser_who_is_no_staff_may_not(self, flags):
        with pytest.raises(PermissionDenied):
            freeze(as_actor(person("someone", **flags)))

        assert not Freeze.objects.filter(frozen=True).exists()
        assert events("control.freeze.started") == []

    def test_its_reason_is_bounded_and_trimmed(self):
        assert FreezeIn(frozen=True, reason="  upgrade  ").reason == "upgrade"
        with pytest.raises(ValueError):
            FreezeIn(frozen=True, reason="x" * 501)


class TestTheWorkersRead:
    """``queries.active_freeze``: the plain read of the worker (once per tick) and of ``migrate_hubs``, no operation."""

    def test_none_while_never_frozen_or_lifted(self, admin_ctx):
        assert queries.active_freeze() is None
        freeze(admin_ctx)
        lift(admin_ctx)

        assert queries.active_freeze() is None

    def test_the_freeze_in_course_while_frozen(self, admin_ctx):
        freeze(admin_ctx)

        active = queries.active_freeze()

        assert (active.frozen, active.reason, active.by) == (True, "Aurora upgrade with Blue/Green", "Ana Root")

    def test_a_control_database_without_its_table_yet_is_not_frozen(self, admin_ctx):
        """``migrate_hubs`` reads it before it migrates control: the first deploy with the switch has no table yet."""
        freeze(admin_ctx)
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE control_freeze RENAME TO control_freeze_away")

        try:
            assert queries.active_freeze() is None
            # The read rolled back to its own savepoint: the transaction it ran in goes on.
            assert Hub.objects.count() >= 0
        finally:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE control_freeze_away RENAME TO control_freeze")

    def test_any_other_failure_of_the_read_is_raised(self, monkeypatch):
        from django.db import ProgrammingError

        def broken(*args, **kwargs):
            raise ProgrammingError("permission denied for table control_freeze")

        monkeypatch.setattr(Freeze.objects, "filter", broken)

        with pytest.raises(ProgrammingError):
            queries.active_freeze()


class TestOneRow:
    def test_a_second_row_is_refused_by_the_database(self):
        # Control's migration made the first (a test that flushed the tables before may have taken it away).
        Freeze.objects.get_or_create()

        with pytest.raises(IntegrityError), transaction.atomic():
            Freeze.objects.create(frozen=True)

    def test_control_s_migration_makes_the_one_row_not_frozen_and_steps_back(self):
        migration = import_module("control.migrations.0010_freeze").Migration
        [seed] = [op for op in migration.operations if isinstance(op, migrations.RunPython)]
        Freeze.objects.all().delete()

        with connection.schema_editor() as editor:
            seed.code(django_apps, editor)
            seed.code(django_apps, editor)

        assert list(Freeze.objects.values_list("frozen", flat=True)) == [False]
        assert seed.reversible
