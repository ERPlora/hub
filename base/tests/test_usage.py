"""The nightly use of each business (BASE-F40, HUBS-F21/F22, FIX-HUB-INTERNAL-USAGE-MISSING; round 2026-10-30 of
PLAN-DB, decision 3 and proposal (j)).

Every night, once the UTC day ended (00:15, before the SaaS asks at 01:15), the worker measures each hub with its own
database (``base.usage.measure``): its database's size from the server's catalog (``pg_database_size``, never opening
the hub's database), its files in the store (``s3_bytes``) and the people who came in that day and in the 30 days that
end it (``control.HubVisit``, one per person, hub and day, noted at every login). A hub that still shares control's
database is skipped (logged ``base.usage_shared_database``) and never gets control's size; a demo is no business of
the SaaS's. The night is kept as a ``UsageRun``: one worker measures it, a run left unfinished is taken over.

``GET /internal/usage?day=YYYY-MM-DD[&cursor=]`` (saas ``hubs/README.md``, «Contrato para el Hub») serves the rows of
that day, by pages, signed as every ``/internal`` call: 409 ``usage_not_ready`` before the night measured it, 422 for
a day missing or badly written. On the Hub, ``base.plan.usage`` says the size of the business's own database.
"""

import datetime as dt
import logging
import threading
import uuid

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import Client
from django.utils import timezone
from live.context import OperationContext, Scope
from live.operations import get

from base import services, usage, worker
from base.models import Membership
from base.storage import hub_prefix
from base.tenancy.ops import connect_ops
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import make_cluster, make_hub  # noqa: F401 (fixtures)
from base.tests.test_internal import signed
from base.tests.test_session_revoke import ANA, OLGA, login
from control.models import Hub, HubUsageDaily, HubVisit, UsageRun

#: A night long past, never the real yesterday of a run: no row a real clock writes can be this day's.
DAY = dt.date(2026, 3, 10)
NIGHT = dt.datetime(2026, 3, 11, 0, 15, tzinfo=dt.UTC)


def size_in_the_catalog(name: str) -> int:
    with connect_ops() as conn:
        return conn.execute("SELECT pg_database_size(%s)", [name]).fetchone()[0]


def visit(host: str, person: str, day: dt.date) -> None:
    HubVisit.objects.create(host=host, saas_user_id=person, day=day)


# ── The measurement ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_hub_with_its_own_database_is_measured_and_the_shared_one_is_skipped(hub_a, hub_b, caplog, settings, tmp_path):
    # The hub file store on this test's own folder: nothing lands in the checkout's media/.
    settings.STORAGES = {
        **settings.STORAGES,
        "hub_files": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(tmp_path)}},
    }
    storages["hub_files"].save(f"{hub_prefix(hub_a.id)}/files/menu.pdf", ContentFile(b"x" * 1234))
    visit(hub_a.slug, ANA, DAY)
    visit(hub_a.slug, OLGA, DAY - dt.timedelta(days=29))
    visit(hub_a.slug, "someone-long-ago", DAY - dt.timedelta(days=30))
    visit(hub_a.slug, "someone-the-day-after", DAY + dt.timedelta(days=1))
    visit("a", ANA, DAY)  # the shared hub's person

    with caplog.at_level(logging.INFO, logger="base.usage"):
        measured = usage.measure(DAY, now=NIGHT)

    assert measured == 2
    rows = {row.hub_id: row for row in HubUsageDaily.objects.filter(day=DAY)}
    assert set(rows) == {hub_a.id, hub_b.id}
    a = rows[hub_a.id]
    assert a.db_bytes == size_in_the_catalog(hub_a.db_name) > 0
    assert (a.s3_bytes, a.active_users_1d, a.active_users_30d, a.measured_at) == (1234, 1, 2, NIGHT)
    assert (rows[hub_b.id].s3_bytes, rows[hub_b.id].active_users_1d) == (0, 0)
    assert "base.usage_shared_database" in caplog.text
    run = UsageRun.objects.get(day=DAY)
    assert (run.finished_at, run.hubs) == (NIGHT, 2)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_night_is_measured_once(hub_a):
    assert usage.measure(DAY, now=NIGHT) == 1

    assert usage.measure(DAY, now=NIGHT + dt.timedelta(minutes=5)) is None
    assert HubUsageDaily.objects.filter(day=DAY).count() == 1


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_night_another_worker_is_measuring_is_left_to_it_until_it_is_stale(hub_a):
    UsageRun.objects.create(day=DAY, started_at=NIGHT)

    assert usage.measure(DAY, now=NIGHT + dt.timedelta(minutes=30)) is None
    assert usage.measure(DAY, now=NIGHT + usage.RUN_TAKEOVER + dt.timedelta(seconds=1)) == 1


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_demo_a_hub_being_made_and_one_whose_database_is_gone_are_not_measured(hub_a, hub_b, make_hub, caplog):
    from base.tenancy import connections, names

    Hub.objects.filter(pk=hub_b.pk).update(is_demo=True, expires_at=NIGHT + dt.timedelta(hours=1))
    make_hub(names.hub_db_name(connections.control_name(), uuid.uuid7()), status=Hub.Status.CREATING)
    gone = make_hub(names.hub_db_name(connections.control_name(), uuid.uuid7()))

    with caplog.at_level(logging.WARNING, logger="base.usage"):
        assert usage.measure(DAY, now=NIGHT) == 1

    assert set(HubUsageDaily.objects.values_list("hub_id", flat=True)) == {hub_a.id}
    assert f"base.usage.not_measured hub={gone.slug}" in caplog.text


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_measuring_again_a_day_replaces_its_figures(hub_a):
    HubUsageDaily.objects.create(hub=hub_a, day=DAY, db_bytes=1, measured_at=NIGHT - dt.timedelta(days=1))

    usage.measure(DAY, now=NIGHT)

    assert HubUsageDaily.objects.get(hub=hub_a, day=DAY).db_bytes == size_in_the_catalog(hub_a.db_name)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_visits_older_than_the_window_are_forgotten(hub_a):
    visit(hub_a.slug, ANA, DAY - dt.timedelta(days=31))
    visit(hub_a.slug, OLGA, DAY - dt.timedelta(days=29))

    usage.measure(DAY, now=NIGHT)

    assert list(HubVisit.objects.values_list("saas_user_id", flat=True)) == [OLGA]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_night_forgets_the_copies_the_bucket_no_longer_keeps(hub_a):
    from control.models import HubDump

    def made(days: int) -> HubDump:
        at = NIGHT - dt.timedelta(days=days)
        return HubDump.objects.create(hub=hub_a, kind="reset", key=f"{hub_a.id.hex}/{at:%Y%m%dT%H%M%SZ}-reset.dump", bytes=1, created_at=at)

    kept, _gone = made(89), made(91)

    usage.measure(DAY, now=NIGHT)

    assert list(HubDump.objects.values_list("pk", flat=True)) == [kept.pk]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_business_measured_hears_it_live(hub_a, monkeypatch):
    told = []
    monkeypatch.setattr(services, "notify", lambda scope, names: told.append((scope.channel, list(names))))

    usage.measure(DAY, now=NIGHT)

    assert told == [(Scope("host", hub_a.slug).channel, ["base.hub.usage_measured"])]


@pytest.mark.parametrize(
    ("now", "day"),
    [
        (dt.datetime(2026, 10, 31, 0, 14, 59, tzinfo=dt.UTC), dt.date(2026, 10, 29)),
        (dt.datetime(2026, 10, 31, 0, 15, tzinfo=dt.UTC), dt.date(2026, 10, 30)),
        (dt.datetime(2026, 10, 31, 23, 59, tzinfo=dt.UTC), dt.date(2026, 10, 30)),
        (dt.datetime(2026, 10, 31, 1, 30, tzinfo=dt.timezone(dt.timedelta(hours=2))), dt.date(2026, 10, 29)),
    ],
)
def test_the_day_to_measure_is_the_last_utc_day_that_ended_a_quarter_of_an_hour_ago(now, day):
    assert usage.day_due(now) == day


# ── The worker's pass ────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES)
def test_the_worker_measures_the_day_that_ended_once(hub_a, monkeypatch):
    monkeypatch.setattr(worker, "_measured", None)

    worker._usage(NIGHT - dt.timedelta(minutes=1))  # 00:14: the day before DAY, which nobody measured in this test
    worker._usage(NIGHT)
    worker._usage(NIGHT + dt.timedelta(minutes=1))

    assert set(UsageRun.objects.values_list("day", flat=True)) == {DAY - dt.timedelta(days=1), DAY}
    assert HubUsageDaily.objects.filter(day=DAY).count() == 1


@pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES)
def test_a_measurement_that_fails_is_logged_and_the_next_tick_tries_again(hub_a, monkeypatch, caplog):
    monkeypatch.setattr(worker, "_measured", None)
    real = usage.measure
    failures = [RuntimeError("the catalog went away")]

    def measure(day, *, now=None):
        if failures:
            raise failures.pop()
        return real(day, now=now)

    monkeypatch.setattr(usage, "measure", measure)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        worker._usage(NIGHT)
    worker._usage(NIGHT)

    assert "the nightly measurement failed" in caplog.text
    assert HubUsageDaily.objects.filter(day=DAY).count() == 1


# ── The worker's real loop in the other tests (W8, 2026-10-31) ───────────────────────────────────────────────────


def run_the_loop_once(monkeypatch) -> None:
    from base import catalog
    from base.catalog import RegisterResult

    monkeypatch.setattr(catalog, "register_apps", lambda: RegisterResult(written=0, retired=0, docs_changed=0, skipped=True))
    monkeypatch.setattr(worker, "_measured", None)
    stop = threading.Event()
    assert worker.run(stop, tick_seconds=0, wait=lambda seconds: stop.set()) == 0


@pytest.mark.django_db(transaction=True)
def test_a_test_that_runs_the_worker_s_loop_measures_nothing_unless_it_asks(monkeypatch):
    """The slow passes (a copy, the nightly measurement) run in threads of their own, on their own connections: in a
    test they committed outside its transaction, and the ``UsageRun`` of the real yesterday that the relay's tests left
    broke the next tests (W8, 2026-10-31). The suite keeps them off (``conftest.py``, ``worker_slow_passes``)."""
    run_the_loop_once(monkeypatch)

    assert not UsageRun.objects.exists()


@pytest.mark.worker_slow_passes
@pytest.mark.django_db(transaction=True)
def test_a_test_marked_for_them_gets_the_slow_passes(monkeypatch):
    run_the_loop_once(monkeypatch)

    assert list(UsageRun.objects.values_list("day", flat=True)) == [usage.day_due(timezone.now())]


# ── Who came in ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_every_login_on_a_hub_notes_its_person_once_a_day_and_the_platforms_none():
    acme = Hub.objects.create(slug="acme", status="ready")

    login(ANA, acme)
    login(ANA, acme)
    login(OLGA, acme)
    login(ANA)  # the platform's admin

    today = timezone.now().date()
    assert set(HubVisit.objects.values_list("host", "saas_user_id", "day")) == {
        ("acme", ANA, today),
        ("acme", OLGA, today),
    }


# ── GET /internal/usage ──────────────────────────────────────────────────────────────────────────────────────────


def usage_of(client, query: str):
    return signed(client, "get", f"/internal/usage{query}", b"", with_v2=True)


@pytest.fixture
def measured_night(db):
    """Three businesses measured on DAY (their rows only: the measurement is above), the night finished."""
    made = []
    for index in range(3):
        hub = Hub.objects.create(
            id=uuid.UUID(f"0199c4b0-0000-7000-8000-00000000c00{index}"), slug=f"shop-{index}", status="ready", db_name=""
        )
        HubUsageDaily.objects.create(
            hub=hub,
            day=DAY,
            db_bytes=1000 + index,
            s3_bytes=10 * index,
            active_users_1d=index,
            active_users_30d=index + 1,
            measured_at=NIGHT,
        )
        made.append(hub)
    UsageRun.objects.create(day=DAY, started_at=NIGHT, finished_at=NIGHT, hubs=3)
    return made


def test_the_day_measured_is_served_as_the_saas_reads_it(measured_night, settings):
    answer = usage_of(Client(), "?day=2026-03-10")

    assert answer.status_code == 200
    assert answer.json() == {
        "day": "2026-03-10",
        "hubs": [
            {
                "id": str(hub.id),
                "s3_bytes": 10 * index,
                "db_bytes": 1000 + index,
                "active_users_1d": index,
                "active_users_30d": index + 1,
            }
            for index, hub in enumerate(measured_night)
        ],
        "next_cursor": None,
    }


def test_the_rows_come_by_pages_each_once(measured_night, monkeypatch):
    monkeypatch.setattr(usage, "PAGE_SIZE", 2)
    client = Client()

    first = usage_of(client, "?day=2026-03-10").json()
    second = usage_of(client, f"?day=2026-03-10&cursor={first['next_cursor']}").json()

    assert [row["id"] for row in first["hubs"] + second["hubs"]] == [str(hub.id) for hub in measured_night]
    assert 1 <= len(first["next_cursor"]) <= 512
    assert second["next_cursor"] is None


def test_a_night_with_no_business_of_its_own_is_an_empty_page(db):
    UsageRun.objects.create(day=DAY, started_at=NIGHT, finished_at=NIGHT, hubs=0)

    assert usage_of(Client(), "?day=2026-03-10").json() == {"day": "2026-03-10", "hubs": [], "next_cursor": None}


@pytest.mark.parametrize("run", [None, {"finished_at": None}])
def test_a_day_not_measured_yet_is_not_ready(db, run):
    if run is not None:
        UsageRun.objects.create(day=DAY, started_at=NIGHT, **run)

    answer = usage_of(Client(), "?day=2026-03-10")

    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "usage_not_ready"


@pytest.mark.parametrize("query", ["", "?day=", "?day=10-03-2026", "?day=2026-13-01", "?day=2026-03-10&cursor=nope"])
def test_a_day_missing_or_badly_written_or_a_cursor_not_ours_is_refused(measured_night, query):
    answer = usage_of(Client(), query)

    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "internal.payload_invalid"


def test_an_unsigned_call_is_refused(db):
    assert Client().get("/internal/usage?day=2026-03-10", HTTP_HOST="hubs.localhost").status_code == 401


# ── On the Hub: the size of its own database (BASE-F40) ──────────────────────────────────────────────────────────


def admin_of(slug: str) -> OperationContext:
    from django.contrib.auth import get_user_model

    from base.permissions import permissions_for

    user = get_user_model().objects.create_user(username=f"olga-{slug}", password="pw")
    Membership.objects.create(user=user, host=slug, role=Membership.Role.OWNER)
    return OperationContext(scope=Scope("host", slug), actor=user, permissions=permissions_for(user, Scope("host", slug)), language="en")


def plan_usage(ctx):
    op = get("base.plan.usage")
    return op(ctx, op.input())


def with_its_own_database(slug: str = "a") -> Hub:
    """The registry's row of ``slug`` as a hub with its own database (the operation reads only the row here)."""
    from base.tenancy import connections, names

    hub = Hub.objects.get(slug=slug)
    Hub.objects.filter(pk=hub.pk).update(db_name=names.hub_db_name(connections.control_name(), hub.id))
    return hub


@pytest.mark.django_db
def test_the_hub_says_the_size_of_its_database_last_measured():
    hub = with_its_own_database()
    HubUsageDaily.objects.create(hub=hub, day=DAY - dt.timedelta(days=1), db_bytes=10, measured_at=NIGHT)
    HubUsageDaily.objects.create(hub=hub, day=DAY, db_bytes=2048, measured_at=NIGHT)

    database = plan_usage(admin_of("a")).database

    assert (database.available, database.bytes, database.day) == (True, 2048, DAY)


@pytest.mark.django_db
def test_a_hub_with_its_own_database_not_measured_yet_says_so():
    with_its_own_database()

    database = plan_usage(admin_of("a")).database

    assert (database.available, database.bytes, database.day) == (True, None, None)


@pytest.mark.django_db
def test_a_hub_that_shares_its_database_has_no_size_of_its_own():
    HubUsageDaily.objects.create(hub=Hub.objects.get(slug="a"), day=DAY, db_bytes=99, measured_at=NIGHT)

    database = plan_usage(admin_of("a")).database

    assert (database.available, database.bytes, database.day) == (False, None, None)
