"""The copy of a move goes through the dumps bucket, never a file of the worker, and ``move.bucket._run`` feeds the
restore what it reads from there. The hubs and the passes are ``test_move.py``'s; their databases, ``conftest.py``'s."""

import re
import time

import psycopg
import pytest
from django.db import connections as django_connections

from base.tenancy import dumps, move
from base.tenancy.tests import hubs, s3
from base.tenancy.tests.hubs import marker, says_it_is
from base.tenancy.tests.s3 import aws_test_credentials, body, dumps_bucket, moto_s3, objects
from base.tenancy.tests.test_move import MARKER, fresh, nothing_checked_yet, run
from control.models import HubDump, MovedCopy

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


#: S3's smallest part: what these tests stream in, so a business of a few MiB goes up in several parts.
SMALLEST_PART = 5 * 1024 * 1024


class TestTheCopyGoesThroughTheBucket:
    """``pg_dump`` sends the copy to the dumps bucket as it makes it, and ``pg_restore`` reads it from there: the
    worker's disk never holds it, so no size stops a move. The copy is no business's to download (no ``HubDump``)."""

    def test_the_copy_is_in_the_bucket_and_never_in_a_file_of_the_worker(
        self, moves, moto_s3, dumps_bucket, monkeypatch
    ):
        hub = moves.hub(to=moves.cluster())
        started = s3.copy_programs(monkeypatch)

        assert run() == 1

        hub = fresh(hub)
        assert (hub.moving_to_id, hub.last_error) == (None, "") and marker(hub.db_name) == [MARKER]
        [key] = objects(moto_s3, dumps_bucket)
        assert re.fullmatch(rf"{hub.id.hex}/\d{{8}}T\d{{6}}Z-move\.dump", key)
        assert body(moto_s3, dumps_bucket, key).startswith(b"PGDMP")
        assert not HubDump.objects.exists()
        assert s3.how_it_was_copied(started) == s3.THROUGH_THE_BUCKET

    def test_a_business_larger_than_a_part_moves_whole(self, moves, monkeypatch):
        monkeypatch.setattr(dumps, "STREAM_PART_BYTES", SMALLEST_PART)
        hub = moves.hub(to=moves.cluster())
        # 12 MiB that do not compress: the copy goes up in three parts and comes back in many reads.
        with hubs._maintenance(hub.db_name) as conn:
            conn.execute("CREATE TABLE w8a_bulk (n int PRIMARY KEY, data bytea NOT NULL)")
            conn.execute(
                "INSERT INTO w8a_bulk SELECT n, decode(md5(n::text) || md5((n + 1)::text), 'hex') "
                "FROM generate_series(1, 393216) AS n"
            )
        fingerprint = "SELECT count(*), md5(string_agg(data, '' ORDER BY n)) FROM w8a_bulk"
        with hubs._maintenance(hub.db_name) as conn:
            before = conn.execute(fingerprint).fetchone()

        assert run() == 1

        hub = fresh(hub)
        assert (hub.moving_to_id, hub.last_error) == (None, "")
        with hubs._maintenance(hub.db_name) as conn:
            assert conn.execute(fingerprint).fetchone() == before
        assert says_it_is(hub.db_name) == [hub.id]

    def test_a_worker_that_stops_while_it_copies_leaves_the_move_to_the_next_one(
        self, moves, moto_s3, dumps_bucket, monkeypatch
    ):
        target = moves.cluster()
        hub = moves.hub(to=target)

        run(cancelled=s3.stopping_as(monkeypatch, dumps, "_pg_dump_command"))

        # Not a failure: the move is neither undone nor noted as failed, and half a copy is never kept.
        stopped = fresh(hub)
        assert (stopped.moving_to_id, stopped.last_error) == (target.pk, "")
        assert objects(moto_s3, dumps_bucket) == {}

        assert run() == 1

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.last_error) == (target.pk, None, "")
        assert marker(hub.db_name) == [MARKER]

    def test_without_a_bucket_the_business_is_never_closed_and_stays_where_it_was(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        monkeypatch.setenv("HUB_DUMPS_BUCKET", "")
        default = django_connections.settings["default"]
        # A session on its database before the pass: closing the origin would end it.
        session = psycopg.connect(
            dbname=hub.db_name,
            user=default["USER"],
            password=default["PASSWORD"],
            host=default["HOST"],
            port=default["PORT"],
        )
        try:
            assert run() == 1

            hub = fresh(hub)
            assert (hub.cluster_id, hub.moving_to_id, hub.status) == (None, None, "ready")
            assert hub.last_error.startswith("move_dump_failed:") and "HUB_DUMPS_BUCKET" in hub.last_error
            assert session.execute("SELECT 1").fetchone() == (1,)
        finally:
            session.close()
        assert marker(hub.db_name) == [MARKER]
        assert not MovedCopy.objects.filter(hub=hub).exists()

    def test_a_copy_that_cannot_be_read_back_puts_the_hub_back_with_its_data(
        self, moves, moto_s3, dumps_bucket, monkeypatch
    ):
        hub = moves.hub(to=moves.cluster())
        s3.lose_each_copy(monkeypatch, moto_s3, dumps_bucket)

        assert run() == 1

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.status) == (None, None, "ready")
        assert hub.last_error.startswith("move_restore_failed:")
        assert "could not be read from the bucket" in hub.last_error
        assert marker(hub.db_name) == [MARKER]

    def test_a_move_has_an_hour_for_each_half_of_its_copy(self, moves, monkeypatch):
        seen = []
        real_stream, real_run = dumps.stream_to_bucket, move.bucket._run

        def streamed(source, key, **kwargs):
            seen.append(("dump", kwargs["timeout"]))
            return real_stream(source, key, **kwargs)

        def ran(command, *args, **kwargs):
            seen.append(("restore", kwargs["timeout"]))
            return real_run(command, *args, **kwargs)

        monkeypatch.setattr(dumps, "stream_to_bucket", streamed)
        monkeypatch.setattr(move.bucket, "_run", ran)
        hub = moves.hub(to=moves.cluster())

        run()

        assert fresh(hub).last_error == "" and move.bucket.COPY_TIMEOUT_SECONDS == 60 * 60
        # The dump, then the restore's listing and the restore itself.
        assert seen == [("dump", 3600), ("restore", 3600), ("restore", 3600)]

    def test_a_dump_that_fails_puts_the_hub_back_and_says_why(
        self, moves, moto_s3, dumps_bucket, monkeypatch, tmp_path
    ):
        failing = tmp_path / "pg_dump"
        failing.write_text("#!/bin/sh\necho 'pg_dump: error: the connection to the server was lost' >&2\nexit 1\n")
        failing.chmod(0o755)
        monkeypatch.setattr(dumps, "pg_dump", lambda: str(failing))
        hub = moves.hub(to=moves.cluster())

        assert run() == 1

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.status) == (None, None, "ready")
        assert hub.last_error.startswith("move_dump_failed:")
        assert "the connection to the server was lost" in hub.last_error
        assert marker(hub.db_name) == [MARKER] and objects(moto_s3, dumps_bucket) == {}

    def test_every_read_of_the_copy_from_the_bucket_is_closed(self, moves, monkeypatch):
        opened, closed = [], []
        real = dumps.client

        def watched():
            s3 = real()
            get = s3.get_object

            def get_object(**kwargs):
                answer = get(**kwargs)
                body = answer["Body"]
                close = body.close
                opened.append(body)

                def closing():
                    closed.append(body)
                    close()

                body.close = closing
                return answer

            s3.get_object = get_object
            return s3

        monkeypatch.setattr(dumps, "client", watched)
        hub = moves.hub(to=moves.cluster())

        run()

        assert fresh(hub).last_error == ""
        # The listing reads only the start of it; the restore, all of it: both are closed.
        assert len(opened) == 2 and closed == opened


#: More than a pipe holds (64 KiB on Linux and macOS): a writer that is not read waits.
FEED = [bytes([n]) * (256 * 1024) for n in range(8)]


def feeding(*chunks: bytes):
    yield from chunks


class TestFeedingAProgram:
    """``move.bucket._run`` with a ``feed``: what it reads from the bucket goes to the program's input as it comes,
    while the stop, the heartbeat and the time limit are heard as when it waits."""

    def test_everything_reaches_the_program_in_order(self, tmp_path):
        out = tmp_path / "out"

        move.bucket._run(
            ["sh", "-c", f"cat > {out}"],
            "",
            tmp_path / "err",
            lambda: None,
            None,
            what="cat",
            feed=feeding(*FEED),
            timeout=30,
        )

        assert out.read_bytes() == b"".join(FEED)

    def test_a_program_that_ends_well_before_reading_it_all_is_done(self, tmp_path):
        move.bucket._run(
            ["sh", "-c", "head -c 10 > /dev/null"],
            "",
            tmp_path / "err",
            lambda: None,
            None,
            what="head",
            feed=feeding(*FEED),
            timeout=30,
        )

    def test_a_program_that_fails_says_why_even_before_reading_it_all(self, tmp_path):
        with pytest.raises(move.exceptions.MoveFailed) as failed:
            move.bucket._run(
                ["sh", "-c", "echo 'pg_restore: error: not an archive' >&2; exit 3"],
                "",
                tmp_path / "err",
                lambda: None,
                None,
                what="the restore of x",
                feed=feeding(*FEED),
            )

        assert failed.value.code == "move_restore_failed"
        assert "exit 3" in str(failed.value) and "not an archive" in str(failed.value)

    def test_a_program_that_never_reads_is_stopped_past_its_time(self, tmp_path):
        started = time.monotonic()

        with pytest.raises(move.exceptions.MoveFailed) as failed:
            move.bucket._run(
                ["sleep", "60"],
                "",
                tmp_path / "err",
                lambda: None,
                None,
                what="sleep",
                feed=feeding(*FEED),
                timeout=0.5,
            )

        assert "took longer than 0.5 s" in str(failed.value)
        assert time.monotonic() - started < 10

    def test_a_stop_is_heard_while_it_feeds(self, tmp_path):
        asked = time.monotonic()

        with pytest.raises(move.exceptions.MoveStopped):
            move.bucket._run(
                ["sleep", "60"],
                "",
                tmp_path / "err",
                lambda: None,
                lambda: time.monotonic() - asked > 0.5,
                what="sleep",
                feed=feeding(*FEED),
            )

        assert time.monotonic() - asked < 10

    def test_its_heartbeat_beats_while_it_feeds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dumps, "POLL_SECONDS", 0.5)
        monkeypatch.setattr(dumps, "STOP_CHECK_SECONDS", 0.05)
        beats = []

        move.bucket._run(
            ["sh", "-c", "sleep 1; cat > /dev/null"],
            "",
            tmp_path / "err",
            lambda: beats.append(1),
            None,
            what="cat",
            feed=feeding(*FEED),
            timeout=30,
        )

        assert 1 <= len(beats) <= 4, beats

    def test_a_program_slow_to_read_is_waited_for_not_spun_on(self, tmp_path):
        checks = []

        move.bucket._run(
            ["sh", "-c", "sleep 1.5; cat > /dev/null"],
            "",
            tmp_path / "err",
            lambda: None,
            lambda: checks.append(1) or False,
            what="cat",
            feed=feeding(*FEED),
            timeout=30,
        )

        assert len(checks) < 1000, len(checks)

    def test_its_feed_is_closed_at_once_when_the_program_fails(self, tmp_path):
        closed = []

        def tracked():
            try:
                yield from FEED
            finally:
                closed.append(True)

        with pytest.raises(move.exceptions.MoveFailed) as failed:
            move.bucket._run(
                ["sh", "-c", "exit 3"], "", tmp_path / "err", lambda: None, None, what="sh", feed=tracked(), timeout=30
            )

        # The failure still holds the run's frame: only closing the feed lets the copy's read from the bucket go now.
        assert "exit 3" in str(failed.value) and closed == [True]

    def test_what_the_feed_raises_stops_the_program_and_reaches_the_caller(self, tmp_path):
        def broken():
            yield FEED[0]
            raise move.exceptions.MoveFailed("move_restore_failed", "its copy could not be read from the bucket: gone")

        started = time.monotonic()

        with pytest.raises(move.exceptions.MoveFailed) as failed:
            move.bucket._run(
                ["sh", "-c", "cat > /dev/null; sleep 60"],
                "",
                tmp_path / "err",
                lambda: None,
                None,
                what="cat",
                feed=broken(),
                timeout=30,
            )

        assert "could not be read from the bucket" in str(failed.value)
        assert time.monotonic() - started < 10


def test_the_restore_leaves_out_the_extensions_and_the_public_schema_of_the_copy():
    # On Aurora only the master makes ``vector``: the destination's template has it, and the restore must neither drop
    # nor make it (nor the public schema, which holds its objects). The tests' superuser would not notice.
    listing = """;
; Archive created at 2026-10-31 18:00:00 UTC
3; 2615 2200 SCHEMA - public pg_database_owner
4; 0 0 COMMENT - SCHEMA public pg_database_owner
2; 3079 16385 EXTENSION - vector
5; 0 0 COMMENT - EXTENSION vector
230; 1259 16500 TABLE public base_hub_identity hub_migrator
4012; 0 16500 TABLE DATA public base_hub_identity hub_migrator
"""

    kept = move.bucket._kept_entries(listing)

    assert [line for line in kept if not line.startswith(";")] == [
        "230; 1259 16500 TABLE public base_hub_identity hub_migrator",
        "4012; 0 16500 TABLE DATA public base_hub_identity hub_migrator",
    ]
