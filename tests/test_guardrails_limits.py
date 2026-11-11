"""Guardrail 12 of the tenancy (plan 2026-10-22-fase-2-tenencia §2; PLAN-DB §5 «Límite por plan»): every transaction
on a hub's alias holds a place of its hub's limiter in this process and carries its plan's ``statement_timeout``.

With two hubs with a database of their own (``hub_a``, ``hub_b``) and no plan in their photo (Free: one transaction at
once per process, 5 s): a second transaction at once in A waits the bounded time and answers 503 ``base.hub_busy``, or
runs as soon as the first one ends; a 6 s statement in A is cancelled by its ``statement_timeout``; A being busy never
slows B; the live executor (``/api/live``), a request to the API and the Hub admin of A's models obey the same place;
and every hub's alias runs on the limited engine (``base.tenancy.backend``), so no transaction can open without it.
"""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError, connections, transaction
from django.utils import timezone
from live.context import OperationContext, Scope
from live.executor import Executor, Stream, Subscription
from live.operations import get as get_operation

from base import access, registry, services
from base.models import Membership
from base.tenancy import connections as tenancy_connections
from base.tenancy import context, identity, limits, names
from base.tenancy.tests import hubs
from control.models import Hub

HUB_DB_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
SHORT_WAIT = 0.3


@pytest.fixture(autouse=True)
def as_in_production(monkeypatch, settings):
    """No fallback context (a thread without ``use_hub`` reaches no hub), every hub known by the live builder, and a
    fresh set of limiters in the process."""
    monkeypatch.setattr(context, "_test_fallback", None)
    monkeypatch.setattr(limits, "_limiters", {})
    settings.LIVE = {**settings.LIVE, "context_builder": "base.operations.HubContextBuilder"}


@pytest.fixture
def short_wait(monkeypatch) -> float:
    monkeypatch.setattr(limits, "SLOT_WAIT_SECONDS", SHORT_WAIT)
    return SHORT_WAIT


class Held:
    """Another thread's transaction in a hub's database, open (its first statement ran) until :meth:`end`, however long
    the test takes to get there: it waits for that fact, never for a clock a loaded machine outruns (hub#762)."""

    def __init__(self, hub) -> None:
        self.hub = hub
        self.opened = threading.Event()
        self.done = threading.Event()
        self.failure: list[Exception] = []
        self.thread = threading.Thread(target=self._hold)

    def _hold(self) -> None:
        try:
            with context.use_hub(self.hub):
                alias = context.current_alias()
                with transaction.atomic(using=alias), connections[alias].cursor() as cursor:
                    cursor.execute("SELECT 1")
                    self.opened.set()
                    self.done.wait()
        except Exception as exc:  # noqa: BLE001 - reported to the test, which fails on it
            self.failure.append(exc)
        finally:
            self.opened.set()
            connections.close_all()

    def end(self) -> None:
        self.done.set()


@contextmanager
def held_open(hub) -> Iterator[Held]:
    """``hub``'s place taken by :class:`Held` for the whole block. Both waits are for a fact the thread always reaches —
    its transaction open or failed, then ended — and the place is given back even when opening it failed."""
    held = Held(hub)
    held.thread.start()
    try:
        held.opened.wait()
        assert held.failure == []
        yield held
    finally:
        held.end()
        held.thread.join()
    assert held.failure == []


def as_hub(hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}))


def list_items(hub) -> list[str]:
    op = get_operation("demo.item.list")
    with context.use_hub(hub):
        return [row.name for row in op(as_hub(hub), op.input.model_validate({})).rows]


def a_statement_alone(hub) -> None:
    with context.use_hub(hub), connections[context.current_alias()].cursor() as cursor:
        cursor.execute("SELECT 1")


def a_transaction_by_hand(hub) -> None:
    with context.use_hub(hub):
        alias = context.current_alias()
        with transaction.atomic(using=alias), connections[alias].cursor() as cursor:
            cursor.execute("SELECT 1")


WAYS_IN = {"an operation": list_items, "a statement alone": a_statement_alone, "a transaction": a_transaction_by_hand}


# ── Two transactions at once in a Free hub ──────────────────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
@pytest.mark.parametrize("way", WAYS_IN.values(), ids=WAYS_IN.keys())
def test_a_second_transaction_at_once_in_a_free_hub_waits_the_bounded_time_and_answers_503(hub_a, short_wait, way):
    with held_open(hub_a):
        started = time.monotonic()
        with pytest.raises(limits.HubBusy) as busy:
            way(hub_a)
        waited = time.monotonic() - started

    assert busy.value.status == 503
    assert busy.value.code == "base.hub_busy"
    assert short_wait <= waited < short_wait + 1
    # Its place is free again: the same thing runs.
    way(hub_a)


@HUB_DB_COMMITTED
def test_a_second_transaction_runs_as_soon_as_the_first_one_ends(hub_a):
    with held_open(hub_a) as held:
        threading.Timer(0.2, held.end).start()
        started = time.monotonic()
        names_ = list_items(hub_a)
        waited = time.monotonic() - started

    assert names_ == []
    assert 0.2 <= waited < limits.SLOT_WAIT_SECONDS


# ── The plan's statement_timeout ─────────────────────────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
def test_a_six_second_statement_in_a_free_hub_is_cancelled_by_its_statement_timeout(hub_a):
    started = time.monotonic()
    with context.use_hub(hub_a), pytest.raises(OperationalError, match="statement timeout"):
        alias = context.current_alias()
        with transaction.atomic(using=alias), connections[alias].cursor() as cursor:
            cursor.execute("SELECT pg_sleep(6)")

    assert 4.5 <= time.monotonic() - started < 6
    assert limits.limiter_for(hubs.HUB_A_ALIAS).in_use == 0


# ── Another hub ──────────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
def test_a_busy_hub_never_slows_another(hub_a, hub_b, short_wait, monkeypatch):
    """B gets its rows without its limiter ever waiting for a place while A's place is taken from before B asks until
    after B has them; A, asked the same way, waits and does not get in. Facts, not B's time against a threshold a
    loaded machine outruns (hub#762): a B that waits on A, even one that gets in once the wait is over, fails at once."""

    def b_waits(timeout=None):
        raise AssertionError("B's limiter waited for a place while only A was busy")

    monkeypatch.setattr(limits.limiter_for(hubs.HUB_B_ALIAS)._condition, "wait", b_waits)
    with held_open(hub_a):
        a_places = limits.limiter_for(hubs.HUB_A_ALIAS)
        assert a_places.in_use == 1
        listed_in_b = list_items(hub_b)
        assert a_places.in_use == 1
        with pytest.raises(limits.HubBusy):
            list_items(hub_a)

    assert listed_in_b == []


# ── Every way in obeys it: the live executor, the API, the admin ────────────────────────────────────────────────────


def run_stream_once(stream: Stream) -> dict:
    executor = Executor(max_workers=1, debounce=0)

    async def once():
        try:
            await executor.run_all(stream)
        finally:
            executor.reset()
            executor.shutdown()

    asyncio.run(once())
    frame = stream.queue.get_nowait().decode()
    return json.loads(frame.split("data: ", 1)[1])


def a_stream_of_items(hub) -> Stream:
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub.slug, role=Membership.Role.ADMIN)
    op = get_operation("demo.item.list")
    stream = Stream(OperationContext(scope=Scope("host", hub.slug), actor=user))
    stream.subs["s1"] = Subscription(id="s1", op=op, params=op.input.model_validate({}))
    return stream


@HUB_DB_COMMITTED
def test_the_live_executor_waits_for_its_hubs_place_too(hub_a, short_wait, monkeypatch):
    monkeypatch.setattr(limits.HubBusy, "retry_after", 0.05)
    stream = a_stream_of_items(hub_a)

    with held_open(hub_a):
        busy = run_stream_once(stream)
    free = run_stream_once(stream)

    # Busy all along: its error once the executor's retries are spent.
    assert busy["error"]["code"] == "base.hub_busy"
    assert free["data"]["rows"] == []


@HUB_DB_COMMITTED
def test_a_live_stream_of_many_lists_on_a_busy_hub_waits_once_per_try_not_once_per_list(hub_a, short_wait, monkeypatch):
    """Five lists of a busy Free hub: the pass waits as long as one list would (the client's watchdog is 45 s; with the
    real waits, 4 × 2 s + 3 × 1 s ≈ 11 s, not 11 s per list), then every list gets the busy error."""
    monkeypatch.setattr(limits.HubBusy, "retry_after", 0.05)
    stream = a_stream_of_items(hub_a)
    op = get_operation("demo.item.list")
    for index in range(2, 6):
        stream.subs[f"s{index}"] = Subscription(id=f"s{index}", op=op, params=op.input.model_validate({}))

    with held_open(hub_a):
        started = time.monotonic()
        first = run_stream_once(stream)
        elapsed = time.monotonic() - started
    rest = []
    while not stream.queue.empty():
        rest.append(json.loads(stream.queue.get_nowait().decode().split("data: ", 1)[1]))

    assert elapsed < 4 * short_wait + 3 * 0.05 + 1
    assert [(frame["id"], frame["error"]["code"]) for frame in [first, *rest]] == [
        (f"s{index}", "base.hub_busy") for index in range(1, 6)
    ]


@HUB_DB_COMMITTED
def test_a_live_list_of_a_hub_busy_for_a_moment_gets_its_result_not_an_error(hub_a, short_wait):
    assert limits.HubBusy("Busy.").retry_after == limits.RETRY_AFTER_SECONDS
    stream = a_stream_of_items(hub_a)

    with held_open(hub_a) as held:
        threading.Timer(0.5, held.end).start()
        listed = run_stream_once(stream)

    assert listed["data"]["rows"] == []
    assert stream.queue.empty()


@HUB_DB_COMMITTED
def test_an_api_request_on_a_busy_hub_answers_503_with_the_envelope(client, hub_a, short_wait):
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub_a.slug, role=Membership.Role.ADMIN)
    client.force_login(user)
    host = f"{hub_a.slug}.localhost"

    with held_open(hub_a):
        busy = client.get("/api/demo/items", HTTP_HOST=host)
        # A's place is still taken once the answer is back: busy all along, however late the request came.
        assert limits.limiter_for(hubs.HUB_A_ALIAS).in_use == 1
    free = client.get("/api/demo/items", HTTP_HOST=host)

    assert busy.status_code == 503
    assert busy.json()["error"]["code"] == "base.hub_busy"
    assert free.status_code == 200


@HUB_DB_COMMITTED
def test_a_request_that_finds_its_hub_busy_while_checking_its_database_answers_503(
    client, hub_a, short_wait, monkeypatch
):
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub_a.slug, role=Membership.Role.ADMIN)
    client.force_login(user)

    with held_open(hub_a):
        # The process has not read this database's identity yet: the request's first statement in it is that read.
        monkeypatch.setattr(identity, "_verified", set())
        busy = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost")

    assert busy.status_code == 503
    assert busy.json()["error"]["code"] == "base.hub_busy"
    assert busy["Retry-After"] == str(limits.RETRY_AFTER_SECONDS)


@HUB_DB_COMMITTED
async def test_an_asgi_request_that_finds_its_hub_busy_while_checking_its_database_answers_503(
    async_client, hub_a, short_wait, monkeypatch
):
    """Daphne runs the middleware asynchronously (``HubDatabaseMiddleware.__acall__``): the same 503."""
    from asgiref.sync import sync_to_async
    from django.test.client import FakePayload

    user = await sync_to_async(get_user_model().objects.create_user)(username="ana", password="pw")
    await sync_to_async(Membership.objects.create)(user=user, host=hub_a.slug, role=Membership.Role.ADMIN)
    await async_client.aforce_login(user)

    with held_open(hub_a):
        monkeypatch.setattr(identity, "_verified", set())
        busy = await async_client.request(
            method="GET",
            path="/api/demo/items",
            query_string="",
            headers=[(b"host", f"{hub_a.slug}.localhost".encode())],
            _body_file=FakePayload(b""),
        )
    await sync_to_async(connections.close_all)()

    assert busy.status_code == 503
    assert json.loads(busy.content)["error"]["code"] == "base.hub_busy"


@HUB_DB_COMMITTED
def test_the_hub_admin_on_a_busy_hub_answers_a_legible_503(client, hub_a, short_wait):
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))
    client.get(f"/admin/hub/{hub_a.slug}/", HTTP_HOST="hubs.localhost")

    with held_open(hub_a):
        busy = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")
    free = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")

    assert busy.status_code == 503
    assert busy["Retry-After"] == str(limits.RETRY_AFTER_SECONDS)
    # A page, not the API's envelope.
    assert busy["Content-Type"].startswith("text/plain")
    assert busy.content.decode() == "Too many requests. Try again in a moment."
    assert free.status_code == 200


@HUB_DB_COMMITTED
@pytest.mark.parametrize(
    ("path", "device_cookie"), [("/", None), ("/settings", "a-tablets-token")], ids=["home", "spa-route-of-a-tablet"]
)
def test_a_visitor_without_a_session_on_a_busy_hub_gets_a_legible_503(client, hub_a, short_wait, path, device_cookie):
    """The login gate (``SaasLoginRequiredMiddleware``) reads the hub's database before any view: its website on ``/``,
    the trusted device of a browser with the device cookie (a till entering by PIN); a ``process_view`` never reaches
    ``process_exception``."""
    host = f"{hub_a.slug}.localhost"
    if device_cookie is not None:
        client.cookies[access.DEVICE_COOKIE] = device_cookie

    with held_open(hub_a):
        busy = client.get(path, HTTP_HOST=host, HTTP_ACCEPT="text/html")
    free = client.get(path, HTTP_HOST=host, HTTP_ACCEPT="text/html")

    assert busy.status_code == 503
    assert busy["Retry-After"] == str(limits.RETRY_AFTER_SECONDS)
    assert busy["Content-Type"].startswith("text/plain")
    assert busy.content.decode() == "Too many requests. Try again in a moment."
    assert free.status_code < 500


# ── No hub's alias opens a transaction without its limiter ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_every_hubs_alias_runs_on_the_limited_engine_and_the_migrators_does_not(hub_databases):
    import uuid

    hub_id = uuid.uuid7()
    hub = SimpleNamespace(id=hub_id, db_name=names.hub_db_name(tenancy_connections.control_name(), hub_id), cluster=None)
    before = connections.settings
    try:
        alias = tenancy_connections.register_hub_alias(hub)
        ddl = tenancy_connections.register_ddl_alias(hub.db_name)

        assert connections.settings[alias]["ENGINE"] == limits.ENGINE
        assert connections.settings[ddl]["ENGINE"] != limits.ENGINE
    finally:
        hubs.forget_aliases(before)
    for session_alias in (hubs.HUB_A_ALIAS, hubs.HUB_B_ALIAS):
        assert connections.settings[session_alias]["ENGINE"] == limits.ENGINE


# ── ERPlora's own hub: the row says it, with no photo, and a business without one stays on Free's ───────────────────


PLATFORM_AT_ONCE = 6
PLATFORM_TIMEOUT = "30s"


def as_platform(hub):
    """The row as ``create_platform_hub`` left it in prod and in pre: ``is_platform``, no photo, ``state_version`` 0. It is
    born so, so every process sees it from its first use: the fixture opened this one as a business, and that limiter goes."""
    Hub.objects.filter(pk=hub.pk).update(is_platform=True)
    hub.refresh_from_db()
    assert (hub.state, hub.state_version) == ({}, 0)
    limits._limiters.pop(tenancy_connections.hub_alias(hub), None)
    return hub


@contextmanager
def several_held_open(hub, how_many: int) -> Iterator[None]:
    if how_many == 0:
        yield
        return
    with held_open(hub), several_held_open(hub, how_many - 1):
        yield


def statement_timeout_in_a_transaction(hub) -> str:
    with context.use_hub(hub):
        alias = context.current_alias()
        with transaction.atomic(using=alias), connections[alias].cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            return cursor.fetchone()[0]


@HUB_DB_COMMITTED
@pytest.mark.parametrize("way", WAYS_IN.values(), ids=WAYS_IN.keys())
def test_the_platform_hub_lets_in_what_a_business_without_a_photo_cannot(hub_a, hub_b, settings, short_wait, way):
    """Two real hubs: the same second transaction gets in on the platform's, and answers 503 on the business's."""
    settings.PGBOUNCER_MAX_DB_CONNECTIONS = PLATFORM_AT_ONCE
    platform = as_platform(hub_a)

    with held_open(platform):
        way(platform)

    with held_open(hub_b), pytest.raises(limits.HubBusy):
        way(hub_b)


@HUB_DB_COMMITTED
def test_the_platform_hub_stops_at_what_pgbouncer_gives(hub_a, settings, short_wait):
    settings.PGBOUNCER_MAX_DB_CONNECTIONS = PLATFORM_AT_ONCE
    platform = as_platform(hub_a)

    with several_held_open(platform, PLATFORM_AT_ONCE - 1):
        a_transaction_by_hand(platform)
        with held_open(platform), pytest.raises(limits.HubBusy):
            a_transaction_by_hand(platform)


@HUB_DB_COMMITTED
def test_every_transaction_of_the_platform_hub_carries_its_own_timeout_and_a_business_keeps_free_s(hub_a, hub_b):
    platform = as_platform(hub_a)

    assert statement_timeout_in_a_transaction(platform) == PLATFORM_TIMEOUT
    assert statement_timeout_in_a_transaction(hub_b) == "5s"


@HUB_DB_COMMITTED
def test_a_statement_past_free_s_five_seconds_is_not_cancelled_on_the_platform_hub(hub_a):
    platform = as_platform(hub_a)

    with context.use_hub(platform):
        alias = context.current_alias()
        with transaction.atomic(using=alias), connections[alias].cursor() as cursor:
            cursor.execute("SELECT pg_sleep(5.2)")


@HUB_DB_COMMITTED
def test_only_the_business_without_a_photo_is_logged_as_free(hub_a, hub_b, caplog):
    caplog.set_level("WARNING", logger="base.tenancy.limits")
    platform = as_platform(hub_a)
    # A process that has opened neither yet: the fixtures already told hub_b's, once for its photo.
    limits._limiters.clear()

    a_statement_alone(platform)
    a_statement_alone(hub_b)

    told = [record.getMessage() for record in caplog.records if "base.hub_limits_free" in record.getMessage()]
    assert len(told) == 1
    assert hubs.HUB_B_ALIAS in told[0]


@HUB_DB_COMMITTED
def test_a_process_whose_limiter_was_already_made_is_corrected_by_the_first_use_hub(hub_a):
    """The first ``use_hub`` of the row that is already in prod, with no step by hand: ``state_version`` 0 is above the -1
    of a limiter nobody configured."""
    platform = as_platform(hub_a)
    early = limits.limiter_for(hubs.HUB_A_ALIAS)
    assert early.limits == limits.FREE

    assert statement_timeout_in_a_transaction(platform) == PLATFORM_TIMEOUT

    assert limits.limiter_for(hubs.HUB_A_ALIAS) is early
    assert early.limits.statement_timeout_seconds == 30
    assert early.hub_id == platform.pk


ROWS = {
    "the host gate": lambda hub: registry.hub_by_slug(hub.slug),
    "the worker": lambda hub: next(row for row in services.hubs_to_serve(timezone.now()) if row.pk == hub.pk),
    "the registry by id": lambda hub: services.registry_row(hub.pk),
    "the registry by slug": lambda hub: services.registry_row_by_slug(hub.slug),
    "a row without the field loaded": lambda hub: Hub.objects.defer("is_platform").get(pk=hub.pk),
}


@HUB_DB_COMMITTED
@pytest.mark.parametrize("read", ROWS.values(), ids=ROWS.keys())
def test_the_row_every_way_in_reads_says_it_is_the_platform_s(hub_a, read):
    """A row that came without the field must never get Free's in silence."""
    as_platform(hub_a)
    with context.use_control():
        row = read(hub_a)

    assert statement_timeout_in_a_transaction(row) == PLATFORM_TIMEOUT
