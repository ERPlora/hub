"""The schema migrator, phase 1: ``migrate_control`` (aws-next README, «Contrato app ↔ infra»).

The control database migrates under a session advisory lock on its own connection, so two
``hub-migrate`` tasks of overlapping deploys never migrate at once: the second waits, then finds
nothing left to apply. The lock is seen from another connection (another thread, another
connection of the pool), where advisory locks are visible whatever the test's transaction.
"""

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import DatabaseError, connection
from django.db.migrations.recorder import MigrationRecorder

from base.tenancy import migrator

WAIT = 10


def on_another_connection(fn):
    """Run ``fn`` on a thread of its own, so on another connection, and return what it returns."""

    def run():
        try:
            return fn()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(run).result(timeout=WAIT)


def lock_is_free() -> bool:
    """Whether another session may take the lock now (and leaves it free again)."""

    def attempt():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [migrator.LOCK_KEY])
            taken = cursor.fetchone()[0]
            if taken:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [migrator.LOCK_KEY])
        return taken

    return on_another_connection(attempt)


def sessions_waiting_for_the_lock() -> int:
    """Sessions blocked on the lock: a bigint key is (classid, objid) = its high and low 32 bits."""
    unsigned = migrator.LOCK_KEY & 0xFFFF_FFFF_FFFF_FFFF

    def count():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted "
                "AND classid = %s::oid AND objid = %s::oid AND objsubid = 1",
                [unsigned >> 32, unsigned & 0xFFFF_FFFF],
            )
            return cursor.fetchone()[0]

    return on_another_connection(count)


def test_the_lock_key_is_the_blake2b_of_its_name():
    digest = hashlib.blake2b(b"erplora.migrate_hubs", digest_size=8).digest()

    assert migrator.LOCK_KEY == int.from_bytes(digest, "big", signed=True)


@pytest.mark.django_db
def test_migrates_the_control_database_while_holding_the_lock(monkeypatch):
    calls = []

    def fake_migrate(*args, **kwargs):
        calls.append((args, kwargs, lock_is_free()))

    monkeypatch.setattr(migrator, "call_command", fake_migrate)

    assert lock_is_free()
    assert migrator.migrate_control() == 0

    [(args, kwargs, free_while_migrating)] = calls
    assert args == ("migrate",)
    assert kwargs["interactive"] is False
    assert kwargs["database"] == "default"
    assert free_while_migrating is False
    assert lock_is_free()


@pytest.mark.django_db
def test_counts_the_migrations_it_applied(monkeypatch):
    def fake_migrate(*args, **kwargs):
        MigrationRecorder(connection).record_applied("demo", "9999_made_up")

    monkeypatch.setattr(migrator, "call_command", fake_migrate)

    assert migrator.migrate_control() == 1


@pytest.mark.django_db
def test_releases_the_lock_when_the_migration_fails(monkeypatch):
    def broken_migrate(*args, **kwargs):
        raise DatabaseError("relation already exists")

    monkeypatch.setattr(migrator, "call_command", broken_migrate)

    with pytest.raises(DatabaseError, match="relation already exists"):
        migrator.migrate_control()

    assert lock_is_free()


@pytest.mark.django_db
def test_a_second_run_waits_until_the_first_one_ends(monkeypatch):
    order: list[str] = []
    first_is_migrating, first_may_end = threading.Event(), threading.Event()

    def fake_migrate(*args, **kwargs):
        name = threading.current_thread().name
        order.append(f"{name}:start")
        if name == "first":
            first_is_migrating.set()
            first_may_end.wait(WAIT)
        order.append(f"{name}:end")

    monkeypatch.setattr(migrator, "call_command", fake_migrate)

    def run():
        try:
            migrator.migrate_control()
        finally:
            connection.close()

    first = threading.Thread(target=run, name="first")
    second = threading.Thread(target=run, name="second")
    first.start()
    try:
        assert first_is_migrating.wait(WAIT)
        second.start()
        deadline = time.monotonic() + WAIT
        while sessions_waiting_for_the_lock() == 0 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert sessions_waiting_for_the_lock() == 1
        assert order == ["first:start"]
    finally:
        first_may_end.set()
        first.join(WAIT)
        if second.ident is not None:  # started
            second.join(WAIT)

    assert order == ["first:start", "first:end", "second:start", "second:end"]
    assert lock_is_free()
