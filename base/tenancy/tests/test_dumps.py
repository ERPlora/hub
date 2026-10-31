"""A hub's database copied to the dumps bucket (round 2026-10-30 of PLAN-DB, decision 2 and proposals (f), (k), (m)).

``dump_hub`` runs ``pg_dump -Fc --no-owner --no-acl`` on the hub's own database as the migrator, on a direct connection
to its writer (never PgBouncer), with its password in the subprocess's environment only; uploads it to
``<hex>/<AAAAMMDDTHHMMSSZ>-<kind>.dump`` and keeps a ``HubDump`` row in control. A hub without its own database is
never dumped; without a bucket nothing is; a dump that fails or runs too long uploads nothing and says why, never
the password. ``presigned_url`` gives a link of 15 minutes.

Real databases (the session's ``hub_a`` and ``hub_b``, ``hubs.py``) and a real S3 server (moto's, ``s3.py``); the dump
is read back with ``pg_restore``.
"""

import datetime as dt
import subprocess
import urllib.parse
import urllib.request

import pytest
from django.utils import timezone
from psycopg.conninfo import conninfo_to_dict

from base.tenancy import dumps
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import make_cluster, make_hub, opened_at  # noqa: F401 (fixtures)
from base.tenancy.tests.s3 import aws_test_credentials, body, dumps_bucket, moto_s3, no_dumps_bucket, objects  # noqa: F401
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
    assert not any(name.startswith("PG") for name in env if name != "PGPASSWORD")
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
