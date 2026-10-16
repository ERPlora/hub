"""``manage.py migrate_hubs``: what the ``hub-migrate`` task runs on every deploy (aws-next README).

Phase 1 migrates only the control database, through ``base.tenancy.migrator.migrate_control``
(its lock: ``test_migrator.py``). The command is thin: a one-line summary, and any failure exits
non-zero (a ``CommandError``), which the infra's ``task_failed`` rule reports. ``--check`` applies
nothing: it lists what a run would apply and exits 1 if anything (the e2e's ``global-setup.ts``).
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection
from django.db.migrations.recorder import MigrationRecorder

from base.tenancy import migrator


def migrate_hubs() -> str:
    out = StringIO()
    call_command("migrate_hubs", stdout=out)
    return out.getvalue()


def migrate_hubs_check() -> tuple[int, str]:
    """``migrate_hubs --check``: its exit status (1 if anything is pending) and its output."""
    out = StringIO()
    try:
        call_command("migrate_hubs", "--check", stdout=out)
    except SystemExit as exit_:
        return exit_.code, out.getvalue()
    return 0, out.getvalue()


def applied() -> set[tuple[str, str]]:
    return set(MigrationRecorder(connection).applied_migrations())


@pytest.mark.django_db(transaction=True)
def test_migrates_the_control_database_and_a_second_run_applies_nothing():
    # A control database one module behind: demo's tables are gone, as before its first deploy.
    call_command("migrate", "demo", "zero", database="default", verbosity=0)
    try:
        first = migrate_hubs()
        second = migrate_hubs()
    finally:
        call_command("migrate", database="default", verbosity=0)

    assert "migrate_hubs: control database migrated, 1 migration(s) applied" in first
    assert "migrate_hubs: control database migrated, 0 migration(s) applied" in second


def test_a_failure_exits_non_zero_with_the_reason(monkeypatch):
    def broken_migrate_control(**kwargs):
        raise DatabaseError("could not connect to server")

    monkeypatch.setattr(migrator, "migrate_control", broken_migrate_control)

    with pytest.raises(CommandError, match="could not connect to server") as raised:
        migrate_hubs()

    assert raised.value.returncode != 0


@pytest.mark.django_db(transaction=True)
def test_check_lists_the_pending_migrations_exits_1_and_applies_nothing():
    # The control database one module behind, as a local database another branch left.
    call_command("migrate", "demo", "zero", database="default", verbosity=0)
    try:
        before = applied()
        status, out = migrate_hubs_check()
        after = applied()
    finally:
        call_command("migrate", database="default", verbosity=0)

    assert status == 1
    assert out.splitlines() == [
        "migrate_hubs: unapplied migrations in the control database:",
        "demo.0001_initial",
    ]
    assert after == before


@pytest.mark.django_db
def test_check_on_an_up_to_date_control_database_exits_0():
    status, out = migrate_hubs_check()

    assert status == 0
    assert out.splitlines() == [
        "migrate_hubs: the control database is up to date (phase 1: no hub databases yet).",
    ]


def test_check_that_cannot_read_the_database_exits_non_zero_with_the_reason(monkeypatch):
    def broken_pending_control():
        raise DatabaseError("could not connect to server")

    monkeypatch.setattr(migrator, "pending_control", broken_pending_control)

    with pytest.raises(CommandError, match="could not connect to server") as raised:
        migrate_hubs_check()

    assert raised.value.returncode != 0
