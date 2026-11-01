"""What a business does during the day, counted in each process and written to control every minute (BASE-F40; PLAN-HUB
§66): its requests, the most transactions it had at once, the requests that found no room, and who has activity.

Counting never reaches the network and never makes a request wait; what could not be written stays for the next pass; a
hub that went away does not stop the others; and a process that serves no requests (the worker, a command, these tests
unless they say so) counts nothing.
"""

import datetime as dt
import logging
import threading
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection, connections
from django.utils import timezone

from base import meter, services
from control.models import Hub, HubActivityDaily, HubVisit

DAY = dt.date(2026, 3, 10)
NEXT_DAY = DAY + dt.timedelta(days=1)
NOON = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.UTC)
ANA, OLGA = "saas-ana", "saas-olga"
ACME = uuid.UUID("0199c4b0-0000-7000-8000-00000000d001")
GLOBEX = uuid.UUID("0199c4b0-0000-7000-8000-00000000d002")


@pytest.fixture
def at(monkeypatch):
    """The meter's clock, moved by the test: ``at(moment)``."""
    moved = {"now": NOON}
    monkeypatch.setattr(meter.timezone, "now", lambda: moved["now"])

    def move(moment: dt.datetime) -> None:
        moved["now"] = moment

    return move


@pytest.fixture
def counting(monkeypatch):
    """This process counts, from nothing."""
    monkeypatch.setattr(meter, "_recording", True)
    monkeypatch.setattr(meter, "_activity", {})
    monkeypatch.setattr(meter, "_seen", {})


@pytest.fixture
def acme(db):
    return Hub.objects.create(id=ACME, slug="acme", status="ready")


@pytest.fixture
def globex(db):
    return Hub.objects.create(id=GLOBEX, slug="globex", status="ready")


def row(hub, day=DAY):
    return HubActivityDaily.objects.get(hub=hub, day=day)


def refuses(*args, **kwargs):
    raise RuntimeError("control is away")


# ── Counting ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_process_that_was_not_started_counts_nothing(monkeypatch, at):
    monkeypatch.setattr(meter, "_activity", {})
    monkeypatch.setattr(meter, "_seen", {})
    assert meter._recording is False

    meter.count_request(ACME)
    meter.note_peak(ACME, 3)
    meter.count_busy(ACME)
    meter.note_seen("acme", ANA)

    assert meter.unflushed(ACME, "acme") == meter.Unflushed()


def test_each_figure_counts_by_hub(counting, at):
    meter.count_request(ACME)
    meter.count_request(ACME)
    meter.count_request(GLOBEX)
    meter.count_busy(ACME)
    meter.note_peak(ACME, 2)
    meter.note_peak(ACME, 5)
    meter.note_peak(ACME, 3)

    assert meter.unflushed(ACME, "acme") == meter.Unflushed(requests=2, peak=5, busy=1)
    assert meter.unflushed(GLOBEX, "globex") == meter.Unflushed(requests=1)


def test_the_people_seen_are_of_their_host(counting, at):
    meter.note_seen("acme", ANA)
    meter.note_seen("acme", ANA)
    meter.note_seen("acme", OLGA)
    meter.note_seen("globex", OLGA)

    assert meter.unflushed(ACME, "acme").people == frozenset({ANA, OLGA})
    assert meter.unflushed(GLOBEX, "globex").people == frozenset({OLGA})


def test_a_figure_of_yesterday_is_not_today_s(counting, at):
    at(dt.datetime(2026, 3, 10, 23, 59, 50, tzinfo=dt.UTC))
    meter.count_request(ACME)
    meter.note_peak(ACME, 4)
    meter.note_seen("acme", ANA)
    at(dt.datetime(2026, 3, 11, 0, 0, 10, tzinfo=dt.UTC))
    meter.count_request(ACME)

    assert meter.unflushed(ACME, "acme") == meter.Unflushed(requests=1)


def test_the_day_is_utc_s_whatever_the_moment_s_zone(counting, at):
    madrid = dt.timezone(dt.timedelta(hours=2))
    at(dt.datetime(2026, 3, 11, 1, 0, tzinfo=madrid))  # 23:00 UTC of the 10th
    meter.count_request(ACME)

    assert list(meter._activity) == [(ACME, DAY)]


# ── Writing it down ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_pass_writes_each_hub_and_day_and_leaves_nothing_behind(counting, at, acme, globex):
    meter.count_request(ACME)
    meter.count_request(ACME)
    meter.note_peak(ACME, 2)
    meter.count_busy(ACME)
    meter.count_request(GLOBEX)

    meter.flush()

    assert (row(acme).requests, row(acme).peak_connections, row(acme).busy_requests) == (2, 2, 1)
    assert (row(globex).requests, row(globex).peak_connections, row(globex).busy_requests) == (1, 0, 0)
    assert meter.unflushed(ACME, "acme") == meter.Unflushed()


def test_the_next_pass_adds_to_the_row_and_the_peak_keeps_the_highest(counting, at, acme):
    meter.count_request(ACME)
    meter.count_busy(ACME)
    meter.note_peak(ACME, 4)
    meter.flush()
    meter.count_request(ACME)
    meter.count_busy(ACME)
    meter.note_peak(ACME, 1)
    meter.flush()

    assert (row(acme).requests, row(acme).peak_connections, row(acme).busy_requests) == (2, 4, 2)


def test_a_pass_across_midnight_writes_each_day_in_its_row(counting, at, acme):
    at(dt.datetime(2026, 3, 10, 23, 59, 50, tzinfo=dt.UTC))
    meter.count_request(ACME)
    at(dt.datetime(2026, 3, 11, 0, 0, 10, tzinfo=dt.UTC))
    meter.count_request(ACME)
    meter.count_request(ACME)

    meter.flush()

    assert (row(acme).requests, row(acme, NEXT_DAY).requests) == (1, 2)


def test_a_person_seen_gets_the_day_s_visit_with_the_last_moment(counting, at, acme):
    meter.note_seen("acme", ANA)
    later = NOON + dt.timedelta(seconds=30)
    at(later)
    meter.note_seen("acme", ANA)

    meter.flush()

    visit = HubVisit.objects.get(host="acme", day=DAY, saas_user_id=ANA)
    assert visit.last_seen_at == later


def test_the_next_moment_updates_the_visit_a_login_left(counting, at, acme):
    HubVisit.objects.create(host="acme", day=DAY, saas_user_id=ANA)
    meter.note_seen("acme", ANA)

    meter.flush()

    assert HubVisit.objects.get(host="acme", day=DAY, saas_user_id=ANA).last_seen_at == NOON


def test_a_session_open_for_days_counts_on_each_of_them(counting, at, acme):
    meter.note_seen("acme", ANA)
    meter.flush()
    at(NOON + dt.timedelta(days=1))
    meter.note_seen("acme", ANA)
    meter.flush()

    assert set(HubVisit.objects.values_list("day", flat=True)) == {DAY, NEXT_DAY}
    assert services.active_people("acme", NEXT_DAY, 30) == (1, 1)
    # So the sweep keeps looking into a hub whose session never logged in again (base.worker).
    assert services.hubs_visited_since(NEXT_DAY) == {"acme"}


def test_a_pass_with_nothing_to_write_touches_nothing(counting, at, db, django_assert_num_queries):
    with django_assert_num_queries(0):
        meter.flush()


# ── What goes wrong ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_what_could_not_be_written_stays_for_the_next_pass_and_the_others_go_on(counting, at, acme, globex, monkeypatch, caplog):
    written = services.activity_recorded

    def refuses_acme(hub_id, *args, **kwargs):
        if hub_id == ACME:
            raise RuntimeError("control is away for this one")
        return written(hub_id, *args, **kwargs)

    meter.count_request(ACME)
    meter.note_peak(ACME, 2)
    meter.count_request(GLOBEX)
    with monkeypatch.context() as patch, caplog.at_level(logging.ERROR, logger="base.meter"):
        patch.setattr(services, "activity_recorded", refuses_acme)
        meter.flush()

    assert row(globex).requests == 1
    assert not HubActivityDaily.objects.filter(hub=acme).exists()
    assert "base.meter.not_written" in caplog.text
    assert meter.unflushed(ACME, "acme") == meter.Unflushed(requests=1, peak=2)

    meter.count_request(ACME)
    meter.note_peak(ACME, 1)
    meter.flush()

    assert (row(acme).requests, row(acme).peak_connections) == (2, 2)
    assert row(globex).requests == 1


def test_the_people_that_could_not_be_written_stay_for_the_next_pass(counting, at, acme, monkeypatch, caplog):
    meter.note_seen("acme", ANA)
    with monkeypatch.context() as patch, caplog.at_level(logging.ERROR, logger="base.meter"):
        patch.setattr(services, "people_seen", refuses)
        meter.flush()
    assert "base.meter.not_written" in caplog.text
    assert not HubVisit.objects.exists()
    assert meter.unflushed(ACME, "acme").people == frozenset({ANA})

    meter.flush()

    assert HubVisit.objects.get(host="acme", saas_user_id=ANA).last_seen_at == NOON


def test_a_person_seen_while_the_pass_failed_keeps_the_latest_moment(counting, at, acme, monkeypatch):
    meter.note_seen("acme", ANA)
    later = NOON + dt.timedelta(seconds=30)

    def fails_after_a_new_moment(*args, **kwargs):
        at(later)
        meter.note_seen("acme", ANA)
        raise RuntimeError("away")

    with monkeypatch.context() as patch:
        patch.setattr(services, "people_seen", fails_after_a_new_moment)
        meter.flush()

    assert meter._seen == {("acme", DAY, ANA): later}


def test_a_hub_that_went_away_does_not_stop_the_others_and_is_forgotten(counting, at, globex, caplog):
    gone = uuid.UUID("0199c4b0-0000-7000-8000-00000000d0ff")
    meter.count_request(gone)
    meter.count_request(GLOBEX)

    with caplog.at_level(logging.ERROR, logger="base.meter"):
        meter.flush()

    assert row(globex).requests == 1
    assert caplog.text == ""
    assert meter.unflushed(gone, "gone") == meter.Unflushed()


def test_a_failed_pass_never_reaches_who_counts(counting, at, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(services, "activity_recorded", refuses)
        meter.count_request(ACME)
        meter.flush()
        meter.count_request(ACME)

    assert meter.unflushed(ACME, "acme").requests == 2


@pytest.mark.django_db(transaction=True)
def test_several_tasks_writing_at_once_lose_nothing(at):
    """Every task's pass, at the same time on the same row: the first ones may race to create it."""
    hub = Hub.objects.create(id=ACME, slug="acme", status="ready")
    failures = []
    barrier = threading.Barrier(5)

    def one_task(peak: int) -> None:
        try:
            barrier.wait(5)
            services.activity_recorded(ACME, DAY, requests=3, peak=peak, busy=2)
        except Exception as error:  # noqa: BLE001 - reported to the test, which fails on it
            failures.append(error)
        finally:
            connections.close_all()

    tasks = [threading.Thread(target=one_task, args=(peak,)) for peak in (1, 7, 2, 4, 3)]
    for task in tasks:
        task.start()
    for task in tasks:
        task.join(10)

    assert failures == []
    assert (row(hub).requests, row(hub).peak_connections, row(hub).busy_requests) == (15, 7, 10)


def test_a_row_another_task_made_meanwhile_is_added_to(acme, monkeypatch):
    """Both found no row: the second one finds it when it goes to make it, and adds to it instead."""

    def another_task_made_it():
        HubActivityDaily.objects.create(hub=acme, day=DAY, requests=5, peak_connections=3, busy_requests=1)
        return True

    monkeypatch.setattr(
        services, "Hub", SimpleNamespace(objects=SimpleNamespace(filter=lambda **_: SimpleNamespace(exists=another_task_made_it)))
    )

    assert services.activity_recorded(ACME, DAY, requests=2, peak=7, busy=4) is True

    assert (row(acme).requests, row(acme).peak_connections, row(acme).busy_requests) == (7, 7, 5)


# ── The process's thread ──────────────────────────────────────────────────────────────────────────────────────────────


class Ticks:
    """A stop event that lets ``times`` passes through and then says stop."""

    def __init__(self, times: int) -> None:
        self.left = times
        self.waits = []

    def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        self.left -= 1
        return self.left < 0


def test_the_loop_writes_every_minute_closes_its_connections_and_survives_a_failure(monkeypatch, caplog):
    passes, closed = [], []

    def flush():
        passes.append(1)
        if len(passes) == 1:
            raise RuntimeError("away")

    monkeypatch.setattr(meter, "flush", flush)
    monkeypatch.setattr(meter, "close_old_connections", lambda: closed.append(1))
    ticks = Ticks(2)

    with caplog.at_level(logging.ERROR, logger="base.meter"):
        meter._loop(ticks)

    assert len(passes) == 2
    assert len(closed) == 2
    assert ticks.waits == [meter.INTERVAL_SECONDS] * 3
    assert meter.INTERVAL_SECONDS == 60
    assert "base.meter" in caplog.text


@pytest.fixture
def not_started(monkeypatch, settings):
    settings.METER_ENABLED = True
    monkeypatch.setattr(meter, "_recording", False)
    monkeypatch.setattr(meter, "_started", False)
    threads, exits = [], []

    class Thread:
        def __init__(self, *, target, name, daemon, args=()):
            self.target, self.name, self.daemon, self.args = target, name, daemon, args

        def start(self):
            threads.append(self)

    monkeypatch.setattr(meter.threading, "Thread", Thread)
    monkeypatch.setattr(meter.atexit, "register", exits.append)
    return threads, exits


def test_starting_runs_one_daemon_thread_and_writes_at_exit(not_started):
    threads, exits = not_started

    meter.start()
    meter.start()

    assert [(thread.target, thread.daemon) for thread in threads] == [(meter._loop, True)]
    assert exits == [meter.flush]
    assert meter._recording is True


def test_a_process_with_the_meter_off_starts_nothing_and_counts_nothing(not_started, settings):
    threads, exits = not_started
    settings.METER_ENABLED = False

    meter.start()

    assert (threads, exits, meter._recording) == ([], [], False)


def test_the_tests_settings_keep_it_off(settings):
    assert settings.METER_ENABLED is False


def test_counting_opens_no_connection(counting, at, db):
    """The request's way: no statement on any database, whatever it counts."""
    before = len(connection.queries_log)

    meter.count_request(ACME)
    meter.note_peak(ACME, 2)
    meter.count_busy(ACME)
    meter.note_seen("acme", ANA)

    assert len(connection.queries_log) == before


def test_the_clock_is_the_project_s(counting):
    """A figure counted now lands on the UTC day of now, with the real clock too."""
    meter.count_request(ACME)

    assert list(meter._activity) == [(ACME, timezone.now().astimezone(dt.UTC).date())]
