"""The plan's limits on a hub's database, per process (PLAN-DB §5 «Límite por plan»; plan 2026-10-22-fase-2-tenencia
§3 S4 and §2, guardrail 12).

Each hub with a database of its own gets, in each process, as many transactions at once as its plan says
(``max_db_connections`` of the SaaS's photo, ``Hub.state["plan"]``) and every one of them carries the plan's
``SET LOCAL statement_timeout`` (``statement_timeout_seconds``). A photo without a plan gets Free's (1 and 5 s), logged.
A newer photo (a greater ``state_version``) resizes the process's limiter without a restart; an older one changes
nothing. A transaction that finds no free place waits a bounded time and then answers 503 ``base.hub_busy``.

The end-to-end guardrail (two hubs, an operation, a request, the live executor, the admin) is
``tests/test_guardrails_limits.py``.
"""

import gc
import logging
import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from django.db import OperationalError, connections, transaction
from django.db.backends.postgresql.base import DatabaseWrapper as PostgresWrapper
from django.utils import translation

from base.tenancy import context, limits
from base.tenancy.tests import hubs

HUB_DB_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)

STARTER = {"slug": "starter", "max_db_connections": 3, "statement_timeout_seconds": 15}
STANDARD = {"slug": "standard", "max_db_connections": 6, "statement_timeout_seconds": 15}


@pytest.fixture(autouse=True)
def fresh_limiters(monkeypatch):
    """Each test starts with no hub's limiter in the process, and leaves none behind for the next one."""
    monkeypatch.setattr(limits, "_limiters", {})


def photo(plan=None, version: int = 1):
    return SimpleNamespace(state={} if plan is None else {"plan": plan}, state_version=version)


# ── The limits of a photo ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ceiling", "plan_gives", "effective"),
    [(6, 1, 1), (6, 3, 3), (6, 6, 6), (6, 12, 6), (6, 48, 6), (3, 6, 3), (3, 1, 1)],
)
def test_no_plan_gets_more_at_once_than_pgbouncer_gives(settings, ceiling, plan_gives, effective):
    """Past it, a transaction would wait 10 s in PgBouncer and fail with no ``base.hub_busy`` that counts it."""
    settings.PGBOUNCER_MAX_DB_CONNECTIONS = ceiling
    plan = {"slug": "x", "max_db_connections": plan_gives, "statement_timeout_seconds": 15}

    assert limits.plan_limits({"plan": plan}) == limits.PlanLimits(effective, 15)


def test_a_ceiling_that_makes_no_sense_leaves_the_plan_s(settings):
    settings.PGBOUNCER_MAX_DB_CONNECTIONS = 0
    plan = {"slug": "x", "max_db_connections": 3, "statement_timeout_seconds": 15}

    assert limits.plan_limits({"plan": plan}) == limits.PlanLimits(3, 15)


@pytest.mark.parametrize(
    ("ceiling", "plan_gives", "helps"),
    [(6, 1, True), (6, 3, True), (6, 5, True), (6, 6, False), (6, 12, False), (3, 3, False), (3, 1, True)],
)
def test_a_bigger_plan_helps_only_below_what_pgbouncer_gives(settings, ceiling, plan_gives, helps):
    settings.PGBOUNCER_MAX_DB_CONNECTIONS = ceiling
    plan = {"slug": "x", "max_db_connections": plan_gives, "statement_timeout_seconds": 15}

    assert limits.bigger_plan_gives_more({"plan": plan}) is helps


@pytest.mark.parametrize("state", [{}, None, {"plan": None}, {"plan": {"slug": "x"}}])
def test_a_photo_with_no_usable_plan_cannot_say_a_bigger_plan_helps(state):
    assert limits.bigger_plan_gives_more(state) is False


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        ({"slug": "free", "max_db_connections": 1, "statement_timeout_seconds": 5}, limits.PlanLimits(1, 5)),
        (STARTER, limits.PlanLimits(3, 15)),
        (STANDARD, limits.PlanLimits(6, 15)),
        # What PgBouncer gives each database is the ceiling, 6 by default: a Pro's 12 are 6 here (PLAN-HUB §66).
        ({"slug": "pro", "max_db_connections": 12, "statement_timeout_seconds": 15}, limits.PlanLimits(6, 15)),
    ],
    ids=["free", "starter", "standard", "pro"],
)
def test_the_photos_plan_sets_the_limits(plan, expected):
    assert limits.plan_limits({"plan": plan}) == expected


@pytest.mark.parametrize(
    "state",
    [
        None,
        {},
        {"plan": None},
        {"plan": "standard"},
        {"plan": {"slug": "x", "statement_timeout_seconds": 15}},
        {"plan": {"slug": "x", "max_db_connections": 0, "statement_timeout_seconds": 15}},
        {"plan": {"slug": "x", "max_db_connections": 3, "statement_timeout_seconds": -1}},
        {"plan": {"slug": "x", "max_db_connections": "3", "statement_timeout_seconds": 15}},
        {"plan": {"slug": "x", "max_db_connections": True, "statement_timeout_seconds": 15}},
    ],
    ids=["no-state", "no-photo", "no-plan", "plan-not-a-dict", "no-connections", "zero", "negative", "text", "bool"],
)
def test_a_photo_without_a_usable_plan_has_no_limits_of_its_own(state):
    assert limits.plan_limits(state) is None


def test_free_is_one_transaction_and_five_seconds_and_the_wait_is_bounded():
    assert limits.FREE == limits.PlanLimits(max_transactions=1, statement_timeout_seconds=5)
    assert limits.SLOT_WAIT_SECONDS == 2


def test_a_hub_without_a_plan_in_its_photo_gets_free_and_says_so_once_per_photo(caplog):
    caplog.set_level(logging.WARNING, logger="base.tenancy.limits")
    hub = photo(version=4)

    limiter = limits.configure("hub_" + "a" * 32, hub)
    limits.configure("hub_" + "a" * 32, hub)

    assert limiter.limits == limits.FREE
    warnings = [record for record in caplog.records if "base.hub_limits_free" in record.getMessage()]
    assert len(warnings) == 1
    assert "hub_" + "a" * 32 in warnings[0].getMessage()


def test_a_newer_photo_resizes_the_limiter_without_a_restart_and_an_older_one_changes_nothing():
    alias = "hub_" + "b" * 32
    limiter = limits.configure(alias, photo(STARTER, version=1))
    assert (limiter.limits, limiter.version) == (limits.PlanLimits(3, 15), 1)

    assert limits.configure(alias, photo(STANDARD, version=2)) is limiter
    assert (limiter.limits, limiter.version) == (limits.PlanLimits(6, 15), 2)

    limits.configure(alias, photo(STARTER, version=1))
    limits.configure(alias, photo(None, version=2))
    assert (limiter.limits, limiter.version) == (limits.PlanLimits(6, 15), 2)


def test_a_newer_photo_without_a_usable_plan_goes_back_to_free(caplog):
    caplog.set_level(logging.WARNING, logger="base.tenancy.limits")
    alias = "hub_" + "d" * 32
    limiter = limits.configure(alias, photo(STANDARD, version=2))

    limits.configure(alias, photo({"slug": "broken", "max_db_connections": 0}, version=3))

    assert (limiter.limits, limiter.version) == (limits.FREE, 3)
    assert any(
        "base.hub_limits_free" in record.getMessage() and "state_version=3" in record.getMessage()
        for record in caplog.records
    )


def test_an_alias_no_hub_configured_gets_free(caplog):
    caplog.set_level(logging.WARNING, logger="base.tenancy.limits")

    limiter = limits.limiter_for("hub_" + "c" * 32)

    assert limiter.limits == limits.FREE
    assert limits.limiter_for("hub_" + "c" * 32) is limiter
    assert any("base.hub_limits_free" in record.getMessage() for record in caplog.records)


# ── The limiter ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_full_limiter_waits_the_bounded_time_and_answers_hub_busy(caplog):
    caplog.set_level(logging.WARNING, logger="base.tenancy.limits")
    limiter = limits.Limiter(limits.FREE, version=0, alias="hub_x")
    held = limiter.take(wait=0)

    started = time.monotonic()
    with pytest.raises(limits.HubBusy) as busy:
        limiter.take(wait=0.2)

    assert time.monotonic() - started >= 0.2
    assert busy.value.status == 503
    assert busy.value.code == "base.hub_busy"
    assert busy.value.envelope() == {"error": {"code": "base.hub_busy", "message": busy.value.message}}
    assert limiter.in_use == 1
    assert any("base.hub_busy" in record.getMessage() and "hub_x" in record.getMessage() for record in caplog.records)
    held.release()


def test_hub_busy_speaks_the_active_language():
    limiter = limits.Limiter(limits.FREE, version=0, alias="hub_x")
    held = limiter.take(wait=0)
    with translation.override("es"), pytest.raises(limits.HubBusy) as busy:
        limiter.take(wait=0)
    held.release()

    assert busy.value.message == "Demasiadas peticiones. Inténtalo de nuevo en un momento."


def test_a_place_freed_while_waiting_lets_the_waiting_one_in():
    limiter = limits.Limiter(limits.FREE, version=0, alias="hub_x")
    held = limiter.take(wait=0)
    threading.Timer(0.1, held.release).start()

    started = time.monotonic()
    second = limiter.take(wait=2)

    # At once, not at the end of the wait.
    assert time.monotonic() - started < 1
    assert limiter.in_use == 1
    second.release()
    assert limiter.in_use == 0


def test_a_slot_released_twice_frees_one_place():
    limiter = limits.Limiter(limits.PlanLimits(2, 15), version=0, alias="hub_x")
    first = limiter.take(wait=0)
    limiter.take(wait=0)

    first.release()
    first.release()

    assert limiter.in_use == 1


def test_a_slot_keeps_the_limits_it_was_taken_with():
    limiter = limits.Limiter(limits.PlanLimits(3, 15), version=1, alias="hub_x")
    slot = limiter.take(wait=0)

    limiter.resize(limits.FREE, version=2)

    assert slot.limits == limits.PlanLimits(3, 15)
    slot.release()


def test_growing_lets_the_waiting_in_and_shrinking_waits_for_the_places_in_use():
    limiter = limits.Limiter(limits.FREE, version=1, alias="hub_x")
    first = limiter.take(wait=0)
    threading.Timer(0.1, lambda: limiter.resize(limits.PlanLimits(3, 15), version=2)).start()
    started = time.monotonic()
    second = limiter.take(wait=2)
    assert time.monotonic() - started < 1
    third = limiter.take(wait=0)

    assert not limiter.resize(limits.FREE, version=1)
    assert limiter.limits == limits.PlanLimits(3, 15)
    assert limiter.resize(limits.FREE, version=3)
    first.release()
    second.release()
    with pytest.raises(limits.HubBusy):
        limiter.take(wait=0.05)
    third.release()

    limiter.take(wait=0).release()
    assert limiter.in_use == 0


# ── What the meter hears (BASE-F40) ───────────────────────────────────────────────────────────────────────────────


ACME = uuid.UUID("0199c4b0-0000-7000-8000-00000000d001")


def photo_of(*, pk=ACME, is_demo=False, plan=STANDARD):
    return SimpleNamespace(pk=pk, is_demo=is_demo, state={"plan": plan}, state_version=1)


@pytest.fixture
def heard(monkeypatch):
    """What the limiters tell the meter: ``peaks`` and ``busy``."""
    told = SimpleNamespace(peaks=[], busy=[])
    monkeypatch.setattr(limits.meter, "note_peak", lambda hub_id, in_use: told.peaks.append((hub_id, in_use)))
    monkeypatch.setattr(limits.meter, "count_busy", told.busy.append)
    return told


def test_each_place_taken_says_how_many_are_in_use_now(heard):
    limiter = limits.configure("hub_x", photo_of())

    first = limiter.take(wait=0)
    second = limiter.take(wait=0)
    second.release()
    third = limiter.take(wait=0)

    assert heard.peaks == [(ACME, 1), (ACME, 2), (ACME, 2)]
    assert heard.busy == []
    first.release()
    third.release()


FREE_PLAN = {"slug": "free", "max_db_connections": 1, "statement_timeout_seconds": 5}


def test_finding_no_room_counts_nothing_yet_and_the_failure_knows_whose_it_is(heard):
    """Whoever catches it decides: the live executor tries again, and a try nobody saw must not tell an owner to upgrade."""
    limiter = limits.configure("hub_x", photo_of(plan=FREE_PLAN))
    held = limiter.take(wait=0)

    with pytest.raises(limits.HubBusy) as busy:
        limiter.take(wait=0)

    assert heard.busy == []
    assert busy.value.hub_id == ACME
    held.release()


def test_the_failure_counts_when_it_reaches_a_client(heard):
    limiter = limits.configure("hub_x", photo_of(plan=FREE_PLAN))
    held = limiter.take(wait=0)
    with pytest.raises(limits.HubBusy) as busy:
        limiter.take(wait=0)
    held.release()

    busy.value.reached_client()

    assert heard.busy == [ACME]


def test_the_same_failure_counts_once_however_many_doors_it_goes_through(heard):
    busy = limits.HubBusy("Too many requests.", hub_id=ACME)

    busy.reached_client()
    busy.reached_client()

    assert heard.busy == [ACME]


def test_the_meter_is_told_outside_the_limiter_s_lock(monkeypatch):
    """A slow pass of the meter never holds up who waits for a place of the hub."""
    limiter = limits.configure("hub_x", photo_of(plan=FREE_PLAN))
    held_while_told = []
    monkeypatch.setattr(limits.meter, "note_peak", lambda *_: held_while_told.append(limiter._condition._is_owned()))

    slot = limiter.take(wait=0)
    slot.release()

    assert held_while_told == [False]


def test_a_demo_is_never_measured(heard):
    limiter = limits.configure("hub_x", photo_of(is_demo=True, plan=FREE_PLAN))

    held = limiter.take(wait=0)
    with pytest.raises(limits.HubBusy) as busy:
        limiter.take(wait=0)
    held.release()
    busy.value.reached_client()

    assert (heard.peaks, heard.busy) == ([], [])


def test_an_alias_no_hub_configured_is_nobody_s_to_measure(heard):
    limiter = limits.limiter_for("hub_nobody")

    held = limiter.take(wait=0)
    with pytest.raises(limits.HubBusy) as busy:
        limiter.take(wait=0)
    held.release()
    busy.value.reached_client()

    assert (heard.peaks, heard.busy) == ([], [])


def test_the_statement_timeout_is_said_in_seconds():
    sql = limits.statement_timeout_sql(limits.PlanLimits(3, 15))

    assert sql.as_string(None) == "SET LOCAL statement_timeout = '15s'"


# ── The hubs' database backend: every transaction of a hub's alias holds a place and carries the timeout ─────────


def limiter_of_a(hub_a):
    """``hub_a``'s limiter in this process (configured by ``use_hub``)."""
    return limits.limiter_for(hubs.HUB_A_ALIAS)


def with_plan(hub, plan, version):
    hub.state = {"plan": plan}
    hub.state_version = version
    return hub


def show_statement_timeout(alias: str) -> str:
    with connections[alias].cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        return cursor.fetchone()[0]


def test_a_hubs_alias_runs_on_the_limited_backend_and_its_migrators_and_controls_do_not(hub_databases):
    from base.tenancy.backend.base import DatabaseWrapper

    assert connections.settings[hubs.HUB_A_ALIAS]["ENGINE"] == limits.ENGINE
    assert isinstance(connections[hubs.HUB_A_ALIAS], DatabaseWrapper)
    assert type(connections["default"]) is PostgresWrapper


@HUB_DB_COMMITTED
def test_a_transaction_holds_one_place_from_its_first_statement_to_its_commit(hub_a):
    seen = []
    with context.use_hub(hub_a):
        limiter = limiter_of_a(hub_a)
        with transaction.atomic(using=hubs.HUB_A_ALIAS):
            seen.append(limiter.in_use)
            show_statement_timeout(hubs.HUB_A_ALIAS)
            seen.append(limiter.in_use)
            with transaction.atomic(using=hubs.HUB_A_ALIAS):
                show_statement_timeout(hubs.HUB_A_ALIAS)
                seen.append(limiter.in_use)
            show_statement_timeout(hubs.HUB_A_ALIAS)
            seen.append(limiter.in_use)
        seen.append(limiter.in_use)

    assert seen == [0, 1, 1, 1, 0]


@HUB_DB_COMMITTED
def test_a_rolled_back_transaction_frees_its_place(hub_a):
    with context.use_hub(hub_a):
        limiter = limiter_of_a(hub_a)
        with pytest.raises(RuntimeError), transaction.atomic(using=hubs.HUB_A_ALIAS):
            show_statement_timeout(hubs.HUB_A_ALIAS)
            raise RuntimeError("rolled back")

        assert limiter.in_use == 0


@HUB_DB_COMMITTED
def test_a_transaction_whose_first_statement_fails_keeps_its_place_until_it_ends(hub_a):
    """An aborted transaction still holds its server connection (PgBouncer's, until its ROLLBACK): its place too. Here
    the connection died under it (its backend was ended), so the BEGIN with the plan's timeout fails."""
    seen = []
    with context.use_hub(hub_a):
        limiter = limiter_of_a(hub_a)
        connection = connections[hubs.HUB_A_ALIAS]
        connection.ensure_connection()
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(%s)", [connection.connection.info.backend_pid])

        with pytest.raises(OperationalError), transaction.atomic(using=hubs.HUB_A_ALIAS):
            try:
                show_statement_timeout(hubs.HUB_A_ALIAS)
            finally:
                seen.append(limiter.in_use)

        assert seen == [1]
        assert limiter.in_use == 0


@HUB_DB_COMMITTED
def test_a_connection_closed_in_the_middle_of_a_transaction_frees_its_place(hub_a):
    with context.use_hub(hub_a):
        limiter = limiter_of_a(hub_a)
        transaction.set_autocommit(False, using=hubs.HUB_A_ALIAS)
        show_statement_timeout(hubs.HUB_A_ALIAS)
        assert limiter.in_use == 1

        connections[hubs.HUB_A_ALIAS].close()

        assert limiter.in_use == 0


@HUB_DB_COMMITTED
def test_a_connection_dropped_in_the_middle_of_a_transaction_gives_its_place_back_when_collected(hub_a):
    from base.tenancy.backend.base import DatabaseWrapper

    with context.use_hub(hub_a):
        limiter = limiter_of_a(hub_a)
        dropped = DatabaseWrapper(dict(connections.settings[hubs.HUB_A_ALIAS]), hubs.HUB_A_ALIAS)
        dropped.set_autocommit(False)
        with dropped.cursor() as cursor:
            cursor.execute("SELECT 1")
        assert limiter.in_use == 1

        # Its thread is gone: nobody commits, rolls back or closes it through Django.
        dropped.connection.close()
        del dropped, cursor
        gc.collect()

        assert limiter.in_use == 0


@HUB_DB_COMMITTED
def test_a_statement_outside_any_transaction_holds_a_place_while_it_runs(hub_a):
    seen = []

    def spy(execute, sql, params, many, context_):
        seen.append(limiter.in_use)
        return execute(sql, params, many, context_)

    with context.use_hub(hub_a):
        limiter = limiter_of_a(hub_a)
        connection = connections[hubs.HUB_A_ALIAS]
        connection.ensure_connection()
        with connection.execute_wrapper(spy):
            timeout = show_statement_timeout(hubs.HUB_A_ALIAS)

        assert connection.get_autocommit()
        assert seen == [1]
        assert limiter.in_use == 0
        assert timeout == "5s"


@HUB_DB_COMMITTED
@pytest.mark.parametrize(
    ("plan", "expected"),
    [(None, "5s"), (STARTER, "15s"), ({"slug": "slow", "max_db_connections": 2, "statement_timeout_seconds": 7}, "7s")],
    ids=["free", "starter", "seven"],
)
def test_every_transaction_carries_the_plans_statement_timeout(hub_a, plan, expected):
    if plan is not None:
        with_plan(hub_a, plan, version=1)

    with context.use_hub(hub_a):
        with transaction.atomic(using=hubs.HUB_A_ALIAS):
            inside = show_statement_timeout(hubs.HUB_A_ALIAS)
        alone = show_statement_timeout(hubs.HUB_A_ALIAS)

    assert (inside, alone) == (expected, expected)


@HUB_DB_COMMITTED
def test_the_plans_timeout_never_outlives_its_transaction_on_the_server(hub_a):
    with context.use_hub(hub_a):
        connection = connections[hubs.HUB_A_ALIAS]
        connection.ensure_connection()
        show_statement_timeout(hubs.HUB_A_ALIAS)
        # The server session itself, read past the backend: SET LOCAL ended with its transaction.
        with connection.connection.cursor() as raw:
            raw.execute("SHOW statement_timeout")
            assert raw.fetchone()[0] != "5s"


@HUB_DB_COMMITTED
def test_a_newer_photo_resizes_the_limit_of_the_running_process(hub_a):
    with context.use_hub(hub_a):
        assert limiter_of_a(hub_a).limits == limits.FREE

    with context.use_hub(with_plan(hub_a, STANDARD, version=9)), transaction.atomic(using=hubs.HUB_A_ALIAS):
        inside = show_statement_timeout(hubs.HUB_A_ALIAS)

    assert limiter_of_a(hub_a).limits == limits.PlanLimits(6, 15)
    assert inside == "15s"


@pytest.mark.django_db
def test_the_control_database_is_never_limited():
    with context.use_control():
        timeout = show_statement_timeout("default")

    assert timeout != "5s"
    assert limits._limiters == {}
