"""A hub's database copied to the dumps bucket.

``dump_hub`` runs ``pg_dump -Fc --no-owner --no-acl`` on the hub's own database as the migrator, on a direct connection
to its writer (never PgBouncer), with its password in the subprocess's environment only; uploads it to
``<hex>/<AAAAMMDDTHHMMSSZ>-<kind>.dump`` and keeps a ``HubDump`` row in control. A hub without its own database is
never dumped; without a bucket nothing is; a dump that fails or runs too long uploads nothing and says why, never
the password. ``presigned_url`` gives a link of 15 minutes. ``stream_to_bucket`` (a move's copy) sends ``pg_dump``'s
output straight to a key, never through a file: the object is there only when ``pg_dump`` ended well.

Real databases (the session's ``hub_a`` and ``hub_b``, ``hubs.py``) and a real S3 server (moto's, ``s3.py``); the dump
is read back with ``pg_restore``.
"""

import datetime as dt
import itertools
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import pytest
from botocore.exceptions import ClientError
from django.utils import timezone
from psycopg.conninfo import conninfo_to_dict

from base.tenancy import dumps
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import make_cluster, make_hub, opened_at  # noqa: F401 (fixtures)
from base.tenancy.tests.s3 import (  # noqa: F401
    aws_test_credentials,
    body,
    client,
    dumps_bucket,
    moto_s3,
    no_dumps_bucket,
    nothing_kept,
    objects,
)
from control.models import Hub, HubDump

pytestmark = [pytest.mark.django_db(databases=hubs.HUB_DATABASES), pytest.mark.usefixtures("no_test_fallback")]

AT = dt.datetime(2026, 10, 31, 10, 15, 0, tzinfo=dt.UTC)


def restored(dump: bytes, tmp_path, *args: str) -> str:
    """What ``pg_restore`` reads in ``dump``, as SQL."""
    path = tmp_path / "copy.dump"
    path.write_bytes(dump)
    return subprocess.run(["pg_restore", *args, "--file=-", str(path)], check=True, capture_output=True, text=True).stdout


def test_a_hubs_database_is_dumped_to_its_key_and_kept_in_control(hub_a, dumps_bucket, moto_s3, tmp_path):
    made = dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, requested_by="Olga", now=AT)

    key = f"{hub_a.id.hex}/20261031T101500Z-reset.dump"
    stored = objects(moto_s3, dumps_bucket)
    copy = body(moto_s3, dumps_bucket, key)
    assert stored == {key: made.bytes}
    assert copy.startswith(b"PGDMP")  # pg_dump's custom format, for pg_restore
    assert HubDump.objects.get() == made
    assert (made.hub_id, made.kind, made.key, made.created_at, made.requested_by) == (
        hub_a.id,
        "reset",
        key,
        AT,
        "Olga",
    )
    listing = restored(copy, tmp_path, "--list")
    assert "base_hub_identity" in listing
    # --no-acl drops the privileges of the environment's roles; --no-owner applies at pg_restore for an archive
    # (PostgreSQL's manual), so who restores it chooses (pg_restore --no-owner).
    sql = restored(copy, tmp_path)
    assert "GRANT " not in sql and "REVOKE " not in sql
    assert "OWNER TO" not in restored(copy, tmp_path, "--no-owner")


def test_the_dump_of_a_is_as_data_and_never_reaches_b(hub_a, hub_b, dumps_bucket, moto_s3, tmp_path, opened_at):
    made = dumps.dump_hub(hub_a, kind=HubDump.Kind.OFFBOARDING, now=AT)

    data = restored(body(moto_s3, dumps_bucket, made.key), tmp_path, "--data-only", "--table=base_hub_identity")
    assert str(hub_a.id) in data
    assert str(hub_b.id) not in data
    assert made.key == f"{hub_a.id.hex}/20261031T101500Z-offboarding.dump"
    # No connection of Django was opened to B's database (pg_dump's own is to A's: its identity row above).
    assert all(database != hub_b.db_name for _host, database in opened_at)


def test_a_hub_without_its_own_database_is_never_dumped(dumps_bucket, moto_s3):
    shared = Hub.objects.get(slug="a")

    with pytest.raises(dumps.HubWithoutDatabase):
        dumps.dump_hub(shared, kind=HubDump.Kind.RESET, now=AT)

    assert objects(moto_s3, dumps_bucket) == {}
    assert not HubDump.objects.exists()


def test_without_a_bucket_nothing_is_dumped(hub_a, no_dumps_bucket):
    assert dumps.configured() is False

    with pytest.raises(dumps.DumpsUnavailable):
        dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)

    assert not HubDump.objects.exists()


def test_a_dump_that_fails_says_why_never_the_password_and_uploads_nothing(hub_a, dumps_bucket, moto_s3, settings):
    settings.DB_MIGRATOR_PASSWORD = "wrong-secret-6f1c"

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)

    assert "password authentication failed" in str(failed.value)
    assert "wrong-secret-6f1c" not in str(failed.value)
    assert objects(moto_s3, dumps_bucket) == {}
    assert not HubDump.objects.exists()


def test_the_password_goes_in_the_environment_never_in_the_command(hub_a, dumps_bucket, monkeypatch, settings):
    seen = []
    real = subprocess.Popen

    def watched(command, **kwargs):
        seen.append((command, kwargs["env"]))
        return real(command, **kwargs)

    monkeypatch.setattr(dumps.subprocess, "Popen", watched)

    dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)

    [(command, env)] = seen
    assert command[:4] == [dumps.pg_dump(), "--format=custom", "--no-owner", "--no-acl"]
    assert env["PGPASSWORD"] == settings.DB_MIGRATOR_PASSWORD
    assert {name for name in env if name.startswith("PG")} == {"PGPASSWORD", "PGGSSENCMODE"}
    dbname = conninfo_to_dict(command[-1].removeprefix("--dbname="))
    assert "password" not in dbname
    assert (dbname["dbname"], dbname["user"]) == (hub_a.db_name, settings.DB_MIGRATOR_USER)
    assert (dbname["host"], int(dbname["port"])) == (settings.DATABASES["default"]["HOST"], settings.DATABASES["default"]["PORT"])


def test_a_database_that_is_not_there_is_a_readable_failure(make_hub, dumps_bucket, moto_s3):
    from base.tenancy import connections, names
    import uuid

    missing = make_hub(names.hub_db_name(connections.control_name(), uuid.uuid7()))

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.dump_hub(missing, kind=HubDump.Kind.RESET, now=AT)

    assert missing.db_name in str(failed.value) and "does not exist" in str(failed.value)
    assert objects(moto_s3, dumps_bucket) == {}


def test_a_dump_that_runs_too_long_is_stopped_and_uploads_nothing(hub_a, dumps_bucket, moto_s3, monkeypatch):
    monkeypatch.setattr(dumps, "POLL_SECONDS", 0.01)

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT, timeout=0.0)

    assert "took longer than" in str(failed.value)
    assert objects(moto_s3, dumps_bucket) == {}
    assert not HubDump.objects.exists()


def test_while_it_dumps_its_heartbeat_beats_and_a_heartbeat_that_fails_stops_it(hub_a, dumps_bucket, moto_s3, monkeypatch):
    monkeypatch.setattr(dumps, "POLL_SECONDS", 0.0)
    beats = []

    class LeaseLost(Exception):
        pass

    def lost():
        beats.append(1)
        raise LeaseLost("another worker holds it now")

    with pytest.raises(LeaseLost):
        dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT, heartbeat=lost)

    assert beats == [1]
    assert objects(moto_s3, dumps_bucket) == {}
    assert not HubDump.objects.exists()


def test_a_bucket_that_refuses_the_upload_is_a_readable_failure(hub_a, dumps_bucket, moto_s3, monkeypatch):
    monkeypatch.setenv("HUB_DUMPS_BUCKET", "erplora-test-hub-dumps-not-there")

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)

    assert "could not be uploaded" in str(failed.value)
    assert not HubDump.objects.exists()


def test_two_dumps_in_the_same_second_get_two_keys(hub_a, dumps_bucket, moto_s3):
    first = dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)
    second = dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)

    assert first.key != second.key
    assert second.key.endswith("20261031T101501Z-reset.dump")
    assert set(objects(moto_s3, dumps_bucket)) == {first.key, second.key}


def test_the_link_is_signed_for_15_minutes_and_downloads_the_copy(hub_a, dumps_bucket, moto_s3):
    made = dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)
    before = timezone.now().replace(microsecond=0)

    url = dumps.presigned_url(made.key)

    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    signed_at = dt.datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == ["900"]
    assert before <= signed_at <= timezone.now()
    assert urllib.parse.urlsplit(url).path == f"/{dumps_bucket}/{made.key}"
    with urllib.request.urlopen(url) as answer:  # the tests' own S3 server
        assert answer.read() == body(moto_s3, dumps_bucket, made.key)


def test_without_a_bucket_there_is_no_link(no_dumps_bucket):
    with pytest.raises(dumps.DumpsUnavailable):
        dumps.presigned_url("0/20261031T101500Z-reset.dump")


def test_the_link_downloads_the_copy_as_a_file_named_after_the_business(hub_a, dumps_bucket, moto_s3):
    made = dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT)

    url = dumps.presigned_url(made.key, filename=dumps.file_name(hub_a.slug, made.key))

    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    wanted = 'attachment; filename="erplora-tenant-a-20261031T101500Z-reset.dump"'
    assert query["response-content-disposition"] == [wanted]
    with urllib.request.urlopen(url) as answer:  # the tests' own S3 server
        assert answer.headers["Content-Disposition"] == wanted


def test_a_copy_is_stopped_when_the_worker_stops_and_nothing_is_kept(hub_a, dumps_bucket, moto_s3):
    """The worker on its way out: pg_dump is killed and the work stays due."""
    with pytest.raises(dumps.DumpStopped):
        dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT, cancelled=lambda: True)

    assert not issubclass(dumps.DumpStopped, dumps.DumpError)  # never a failed copy: the reset is not marked failed
    assert objects(moto_s3, dumps_bucket) == {}
    assert not HubDump.objects.exists()


def test_a_stopped_copy_kills_pg_dump_at_once_even_while_it_waits_on_a_lock(hub_a, dumps_bucket, moto_s3):
    """pg_dump waiting on a table someone else locked: the stop is heard and pg_dump killed at
    once; without the kill the call would wait for the lock (released here after 8 s)."""
    import threading
    import time

    import psycopg

    from base.tenancy import connections as tenancy_connections

    holder = psycopg.connect(**tenancy_connections.migrator_conninfo(hub_a.db_name))
    # A table this test's own transaction never touched (it holds base_hub_identity's), within 5 s or a clean failure.
    holder.execute("SET lock_timeout = '5s'")
    holder.execute("LOCK TABLE django_migrations IN ACCESS EXCLUSIVE MODE")
    released = threading.Timer(8, holder.rollback)
    released.start()
    asked = time.monotonic()
    try:
        with pytest.raises(dumps.DumpStopped):
            dumps.dump_hub(hub_a, kind=HubDump.Kind.RESET, now=AT, cancelled=lambda: time.monotonic() - asked > 1.5)
        took = time.monotonic() - asked
    finally:
        released.cancel()
        holder.rollback()
        holder.close()

    assert took < 5, f"pg_dump was waited for {took:.1f} s instead of being killed"
    assert objects(moto_s3, dumps_bucket) == {}


# ── Control's own copy, before the businesses moved out ───────────────────────────────────────────────────────────


def test_control_is_copied_to_a_key_of_its_own_and_no_hub_s_copy_is_noted(hub_databases, dumps_bucket, moto_s3, tmp_path):
    from base.tenancy import connections as tenancy_connections

    noted = HubDump.objects.count()

    key = dumps.dump_control(kind=dumps.CUT, now=AT)

    assert key == f"{tenancy_connections.control_name()}/20261031T101500Z-cut.dump"
    assert objects(moto_s3, dumps_bucket)[key] > 0
    schema = restored(body(moto_s3, dumps_bucket, key), tmp_path, "--schema-only", "--table=base_hub")
    assert "CREATE TABLE public.base_hub " in schema
    assert HubDump.objects.count() == noted


def test_without_a_bucket_control_is_not_copied(hub_databases, no_dumps_bucket):
    with pytest.raises(dumps.DumpsUnavailable):
        dumps.dump_control(kind=dumps.CUT, now=AT)


# ── A move's copy: streamed to the bucket, never through a file ──────────────────────────────────────────────────────

MOVE_KEY = "0f0f/20261031T101500Z-move.dump"
#: S3's smallest part: what the tests stream in, so a copy of a few MiB goes up in several parts.
SMALLEST_PART = 5 * 1024 * 1024
#: A copy of three parts, every byte checked when it comes back.
LARGE = b"PGDMP" + bytes(range(256)) * (48 * 1024)


def a_pg_dump(tmp_path, monkeypatch, script: str) -> list[subprocess.Popen]:
    """``pg_dump`` replaced by ``script`` (Python, its own program): what a real one does at its edges, on demand. Each
    one the copy starts reaches it only once it runs, however loaded the machine is, counts the copy's ``waits`` for it
    to end, and is kept in the list returned to see how it ended."""
    program = tmp_path / "pg_dump"
    running = tmp_path / "pg_dump.running"
    program.write_text(f"#!{sys.executable}\nimport os, sys, time\nopen({str(running)!r}, 'w').close()\n{script}\n")
    program.chmod(0o755)
    started: list[subprocess.Popen] = []

    class PgDump(subprocess.Popen):
        waits = 0

        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs)
            while self.poll() is None and not running.exists():
                time.sleep(0.01)
            started.append(self)

        def wait(self, timeout=None):
            self.waits += 1
            return super().wait(timeout)

    monkeypatch.setattr(dumps, "pg_dump", lambda: str(program))
    monkeypatch.setattr(dumps.subprocess, "Popen", PgDump)
    return started


def killed(process: subprocess.Popen) -> bool:
    """Whether the copy killed ``process`` and waited for it (no zombie left), rather than letting it end on its own."""
    return process.returncode == -signal.SIGKILL


def test_a_database_is_streamed_to_its_key_never_through_a_file(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    seen = []
    real = subprocess.Popen

    def watched(command, **kwargs):
        seen.append((command, kwargs))
        return real(command, **kwargs)

    monkeypatch.setattr(dumps.subprocess, "Popen", watched)

    sent = dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    [(command, kwargs)] = seen
    monkeypatch.undo()
    assert command[:4] == [dumps.pg_dump(), "--format=custom", "--no-owner", "--no-acl"]
    assert not any(part.startswith("--file") for part in command) and kwargs["stdout"] == subprocess.PIPE
    copy = body(moto_s3, dumps_bucket, MOVE_KEY)
    assert objects(moto_s3, dumps_bucket) == {MOVE_KEY: sent} and copy.startswith(b"PGDMP")
    assert "base_hub_identity" in restored(copy, tmp_path, "--list")
    assert not HubDump.objects.exists()  # a move's copy is nobody's to download


def test_a_copy_larger_than_a_part_goes_up_whole_in_parts(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    monkeypatch.setattr(dumps, "STREAM_PART_BYTES", SMALLEST_PART)
    a_pg_dump(tmp_path, monkeypatch, "sys.stdout.buffer.write(b'PGDMP' + bytes(range(256)) * (48 * 1024))")

    sent = dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert sent == len(LARGE)
    assert body(moto_s3, dumps_bucket, MOVE_KEY) == LARGE
    assert client(moto_s3).head_object(Bucket=dumps_bucket, Key=MOVE_KEY)["ETag"].endswith('-3"')


@pytest.mark.parametrize("written", [10, 6 * 1024 * 1024], ids=["in-the-first-part", "after-a-part-went-up"])
def test_a_dump_that_fails_midway_keeps_nothing_and_says_why(
    hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path, written
):
    monkeypatch.setattr(dumps, "STREAM_PART_BYTES", SMALLEST_PART)
    a_pg_dump(
        tmp_path,
        monkeypatch,
        f"sys.stdout.buffer.write(b'PGDMP' + bytes({written})); sys.stdout.flush()\n"
        "sys.stderr.write('pg_dump: error: the connection to the server was lost\\n'); sys.exit(1)",
    )

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert "exit 1" in str(failed.value) and "the connection to the server was lost" in str(failed.value)
    assert nothing_kept(moto_s3, dumps_bucket)


def test_a_stream_that_fails_says_why_never_the_password(hub_a, dumps_bucket, moto_s3, settings):
    settings.DB_MIGRATOR_PASSWORD = "wrong-secret-7a2d"

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert "password authentication failed" in str(failed.value)
    assert "wrong-secret-7a2d" not in str(failed.value)
    assert nothing_kept(moto_s3, dumps_bucket)


def test_a_stream_that_runs_too_long_is_stopped_and_keeps_nothing(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    started = a_pg_dump(tmp_path, monkeypatch, "sys.stdout.buffer.write(b'PGDMP'); sys.stdout.flush(); time.sleep(60)")

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=0.5)

    [process] = started
    assert "took longer than 0.5 s" in str(failed.value) and killed(process)
    assert nothing_kept(moto_s3, dumps_bucket)


@pytest.mark.parametrize(
    ("script", "stopping"),
    [
        # Nothing written yet: the worker stops once the copy has looked once and waits on pg_dump's output.
        ("time.sleep(60)", lambda looks, process: looks > 0),
        # Its output closed but still running: the worker stops once the copy waits for it to end.
        (
            "sys.stdout.buffer.write(b'PGDMP'); sys.stdout.flush(); os.close(1); time.sleep(60)",
            lambda looks, process: process.waits > 0,
        ),
    ],
    ids=["before-any-output", "its-output-closed"],
)
def test_a_stream_is_stopped_when_the_worker_stops_and_keeps_nothing(
    hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path, script, stopping
):
    started = a_pg_dump(tmp_path, monkeypatch, script)
    looks = itertools.count()

    with pytest.raises(dumps.DumpStopped):
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60, cancelled=lambda: stopping(next(looks), started[0]))

    [process] = started
    assert killed(process) and nothing_kept(moto_s3, dumps_bucket)


def test_while_it_streams_its_heartbeat_beats_and_one_that_fails_stops_it(
    hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path
):
    monkeypatch.setattr(dumps, "POLL_SECONDS", 0.0)
    started = a_pg_dump(tmp_path, monkeypatch, "time.sleep(60)")
    beats = []

    class LeaseLost(Exception):
        pass

    def lost():
        beats.append(1)
        raise LeaseLost("another worker holds it now")

    with pytest.raises(LeaseLost):
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60, heartbeat=lost)

    [process] = started
    assert beats == [1] and killed(process)
    assert nothing_kept(moto_s3, dumps_bucket)


def test_its_heartbeat_waits_its_time_between_beats(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    monkeypatch.setattr(dumps, "POLL_SECONDS", 0.4)
    monkeypatch.setattr(dumps, "STOP_CHECK_SECONDS", 0.05)
    a_pg_dump(tmp_path, monkeypatch, "time.sleep(1.3); sys.stdout.buffer.write(b'PGDMP')")
    beats = []

    dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60, heartbeat=lambda: beats.append(time.monotonic()))

    assert 2 <= len(beats) <= 4, beats


def test_without_a_bucket_nothing_is_streamed_and_pg_dump_never_starts(hub_a, no_dumps_bucket, monkeypatch, tmp_path):
    started = a_pg_dump(tmp_path, monkeypatch, "")

    with pytest.raises(dumps.DumpsUnavailable):
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert started == []


def test_a_bucket_that_refuses_the_stream_is_a_readable_failure(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    monkeypatch.setenv("HUB_DUMPS_BUCKET", "erplora-test-hub-dumps-not-there")

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert "could not be uploaded" in str(failed.value)


def test_a_refused_upload_of_a_large_copy_stops_pg_dump_at_once(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    """The bucket refuses the first part while pg_dump still has more to give: it is killed, not waited for."""
    monkeypatch.setenv("HUB_DUMPS_BUCKET", "erplora-test-hub-dumps-not-there")
    monkeypatch.setattr(dumps, "STREAM_PART_BYTES", SMALLEST_PART)
    a_pg_dump(
        tmp_path, monkeypatch, "sys.stdout.buffer.write(bytes(6 * 1024 * 1024)); sys.stdout.flush(); time.sleep(60)"
    )
    asked = time.monotonic()

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    # Waited for, not killed, it would take its whole minute.
    assert "could not be uploaded" in str(failed.value) and time.monotonic() - asked < 10


def test_a_copy_of_exactly_two_parts_goes_up_in_two(hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path):
    monkeypatch.setattr(dumps, "STREAM_PART_BYTES", SMALLEST_PART)
    a_pg_dump(tmp_path, monkeypatch, f"sys.stdout.buffer.write(bytes(range(256)) * (2 * {SMALLEST_PART} // 256))")

    sent = dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert sent == 2 * SMALLEST_PART
    assert client(moto_s3).head_object(Bucket=dumps_bucket, Key=MOVE_KEY)["ETag"].endswith('-2"')


def test_an_abort_that_fails_keeps_the_reason_of_the_failure(
    hub_a, dumps_bucket, moto_s3, monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(dumps, "STREAM_PART_BYTES", SMALLEST_PART)
    a_pg_dump(
        tmp_path,
        monkeypatch,
        "sys.stdout.buffer.write(bytes(6 * 1024 * 1024)); sys.stdout.flush()\n"
        "sys.stderr.write('pg_dump: error: the connection to the server was lost\\n'); sys.exit(1)",
    )
    real = dumps.client

    def refusing_aborts():
        s3 = real()

        def abort(**kwargs):
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "not allowed"}}, "AbortMultipartUpload")

        s3.abort_multipart_upload = abort
        return s3

    monkeypatch.setattr(dumps, "client", refusing_aborts)

    with pytest.raises(dumps.DumpFailed) as failed:
        dumps.stream_to_bucket(hub_a, MOVE_KEY, timeout=60)

    assert "the connection to the server was lost" in str(failed.value)
    assert "base.tenancy.dumps.abort_failed" in caplog.text
    assert objects(moto_s3, dumps_bucket) == {}
