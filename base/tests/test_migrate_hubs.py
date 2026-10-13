"""``manage.py migrate_hubs``: what the ``hub-migrate`` task runs on every deploy (aws-next README).

Phase 1 migrates only the control database, through ``base.tenancy.migrator.migrate_control``
(its lock: ``test_migrator.py``). The command is thin: a one-line summary, and any failure exits
non-zero (a ``CommandError``), which the infra's ``task_failed`` rule reports.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError

from base.tenancy import migrator


def migrate_hubs() -> str:
    out = StringIO()
    call_command("migrate_hubs", stdout=out)
    return out.getvalue()


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
