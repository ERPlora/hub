"""The worker's ear on the businesses' channels (``base.hub_listener``): one connection of its own to control's
database, outside Django, that LISTENs on the channel of every business the worker serves and says, without waiting,
which of them were notified since it last asked. Real LISTEN and NOTIFY on the session's control database."""

import logging
import threading
import time

import psycopg
import pytest
from django.db import connection

from base import hub_listener

pytestmark = pytest.mark.django_db(transaction=True)

A, B, ELSEWHERE = "live_host_ear_a", "live_host_ear_b", "live_host_ear_elsewhere"


def notify(channel: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify(%s, %s)", [channel, '{"events":["demo.item.created"]}'])


def heard_soon(ear, channels, *, seconds: float = 3.0) -> frozenset[str] | None:
    """What ``ear`` hears on ``channels`` within ``seconds`` of real time: a notice takes a moment to arrive."""
    deadline = time.monotonic() + seconds
    while True:
        heard = ear.heard(channels)
        if heard is None or heard or time.monotonic() >= deadline:
            return heard
        time.sleep(0.05)


def gone_soon(pid: int, *, seconds: float = 3.0) -> bool:
    """Whether the server process ``pid`` leaves ``pg_stat_activity`` within ``seconds`` of real time: the server ends
    it on its own a moment after the client has closed the connection."""
    deadline = time.monotonic() + seconds
    with connection.cursor() as cursor:
        while True:
            cursor.execute("SELECT 1 FROM pg_stat_activity WHERE pid = %s", [pid])
            if cursor.fetchone() is None:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


@pytest.fixture
def ear():
    listening = hub_listener.Listener()
    yield listening
    listening.close()


def test_a_new_connection_counts_as_every_channel_heard_and_then_only_what_is_notified_is(ear):
    assert ear.heard({A, B}) is None  # what was notified before it listened is unknown

    notify(A)
    notify(ELSEWHERE)

    assert heard_soon(ear, {A, B}) == {A}
    assert ear.heard({A, B}) == frozenset()


def test_a_channel_no_longer_asked_for_is_no_longer_heard(ear):
    ear.heard({A, B})

    ear.heard({A})
    notify(B)
    notify(A)

    assert heard_soon(ear, {A}) == {A}


def test_a_channel_asked_for_later_is_heard_from_then_on(ear):
    ear.heard({A})

    ear.heard({A, B})
    notify(B)

    assert heard_soon(ear, {A, B}) == {B}


def test_a_lost_connection_is_made_again_and_counts_as_every_channel_heard(ear, caplog):
    ear.heard({A})
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_terminate_backend(%s)", [ear.pid])

    with caplog.at_level(logging.ERROR, logger="base.hub_listener"):
        assert heard_soon(ear, {A}) is None

    notify(A)
    assert heard_soon(ear, {A}) == {A}
    assert "base.worker.listen_lost" in caplog.text


def test_a_connection_it_cannot_make_is_logged_and_tried_again_after_a_pause_that_doubles(caplog):
    clock = [100.0]
    attempts = []

    def refused():
        attempts.append(clock[0])
        raise psycopg.OperationalError("connection refused")

    ear = hub_listener.Listener(connect=refused, backoff=(1.0, 4.0), clock=lambda: clock[0])
    with caplog.at_level(logging.ERROR, logger="base.hub_listener"):
        for step in range(12):
            clock[0] = 100.0 + step * 0.5
            assert ear.heard({A}) == frozenset()  # nothing heard: the look every minute covers it meanwhile

    assert attempts == [100.0, 101.0, 103.0]  # then 1 s, then 2 s, then 4 s at most
    assert "base.worker.listen_failed" in caplog.text
    ear.close()


def closed_a_moment_later() -> psycopg.Connection:
    """A real connection whose server process ends a moment after ``close()`` returns, as it may on a busy machine."""
    conn = hub_listener.connect()
    close = conn.close
    conn.close = lambda: threading.Timer(0.3, close).start()
    return conn


@pytest.mark.parametrize("connect", [hub_listener.connect, closed_a_moment_later], ids=["now", "a_moment_later"])
def test_close_ends_its_connection(connect):
    ear = hub_listener.Listener(connect=connect)
    ear.heard({A})
    pid = ear.pid

    ear.close()

    assert gone_soon(pid)
    assert ear.pid is None
