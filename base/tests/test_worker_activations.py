"""The worker makes the tables of the apps a hub with its own database turned on (S3; PLAN-DB §7 and §8, spec
2026-10-11 «tablas al activar» §4–§8 and §14).

``base.app.enable`` leaves the app ``creating`` and rings the hub's ``hub_due``; each tick the worker takes the hubs
rung (and, every ``ACTIVATION_SWEEP_SECONDS``, every ready hub with its own database, so a ring lost is found again),
reads in each one what is due (``creating``, or ``failed`` past its next try) and makes those apps' tables with
``migrator.ensure_schema(hub, add=…)``, under the hub's schema lock; then ``base.app.activation_settle`` turns them on
(``base.app.enabled``, its live notice) or ``failed`` with why, tried again at 1, 5 and 15 minutes and then every hour.
A schema held by another run puts it off 30 s; a request of a newer code than the worker's waits for a worker of that
code (+60 s). Turned off meanwhile, it stays off with its tables. Another hub's database is never opened.

Real databases, committed (no test case: the migrator registers its own aliases): a template of this module with only
the platform (``base``, ``live``) and two businesses cloned from it, A and B.
"""

import datetime as dt
import threading
import uuid

import pytest
from django.db import connections
from django.utils import timezone
from live.context import OperationContext, Scope
from live.models import OutboxEvent
from live.operations import get
from psycopg import sql

from base import activation, events, worker
from base.activation import CREATING, FAILED, OFF, ON
from base.models import AppActivation
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, migrator, names
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import opened_at  # noqa: F401 (a fixture)
from control.models import Hub, HubDue

pytestmark = pytest.mark.usefixtures("no_test_fallback")

#: An app without ``requires``, with migrations of its own.
APP = "printing"
#: This module's template: the platform's apps and no other.
VERTICAL = "w6activation"


@pytest.fixture
def no_test_fallback(monkeypatch):
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())
    monkeypatch.setattr(worker, "_swept", {})
    monkeypatch.setattr(worker, "_synced", set())
    monkeypatch.setattr(worker, "_next_hub", None)


@pytest.fixture(scope="module")
def platform_template(django_db_setup, django_db_blocker):
    """A template with the platform's tables alone: what a hub's template is for an app ported after it was made. The
    real ones carry every portable app (``migrator.templates``, PLAN-DB round 2026-11-01), so turning on an app they have
    is on at once; this one makes every app one whose tables its hubs lack."""
    with django_db_blocker.unblock():
        name = names.template_db_name(tenancy_connections.control_name(), VERTICAL)
        hubs.drop_database(name)
        hubs.create_database(name)
        migrator.ensure_template(migrator.Template(db_name=name, apps=migrator.platform_apps()))
    yield name
    with django_db_blocker.unblock():
        hubs.drop_database(name)


@pytest.fixture
def business(platform_template, django_db_blocker):
    """``business(name, **hub fields)``: a ready business with its own database cloned from the platform's template,
    its identity written and every app off; its database and its rows dropped after the test."""
    made: list[Hub] = []
    control = tenancy_connections.control_name()

    def make(name: str, **fields) -> Hub:
        hub_id = uuid.uuid7()
        db_name = names.hub_db_name(control, hub_id)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(db_name, control=control), names.identifier(platform_template, control=control)
                )
            )
        alias = tenancy_connections.register_ddl_alias(db_name)
        try:
            identity.write(alias, hub_id)
        finally:
            connections[alias].close()
        values = {"id": hub_id, "slug": f"{name}-{hub_id.hex[-8:]}", "status": Hub.Status.READY, "db_name": db_name}
        made.append(hub := Hub.objects.create(**(values | fields)))
        with use_hub(hub):
            AppActivation.objects.bulk_create(
                AppActivation(host=hub.slug, app=label, state=OFF, chosen=False) for label in activation.module_graph()
            )
        return hub

    with django_db_blocker.unblock():
        yield make
        with hubs._maintenance() as conn:
            for hub in made:
                hubs._drop(conn, hub.db_name, control)
        Hub.objects.filter(pk__in=[hub.pk for hub in made]).delete()


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster").get(pk=hub.pk)


def as_admin(hub: Hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=frozenset({"*"}), language="en")


def turn_on(hub: Hub, app: str = APP) -> dict:
    op = get("base.app.enable")
    with use_hub(fresh(hub)):
        return op(as_admin(hub), op.input.model_validate({"app": app})).model_dump(mode="json")


def turn_off(hub: Hub, app: str = APP) -> dict:
    op = get("base.app.disable")
    with use_hub(fresh(hub)):
        return op(as_admin(hub), op.input.model_validate({"app": app})).model_dump(mode="json")


def row(hub: Hub, app: str = APP) -> AppActivation:
    with use_hub(fresh(hub)):
        return AppActivation.objects.get(host=hub.slug, app=app)


def outbox(hub: Hub) -> list[tuple[str, dict]]:
    with use_hub(fresh(hub)):
        return [(event.name, event.payload) for event in OutboxEvent.objects.order_by("id")]


def tables(hub: Hub) -> set[str]:
    return hubs.table_names(hub.db_name)


def recorded(hub: Hub) -> set[str]:
    with hubs._maintenance(hub.db_name) as conn:
        return {name for (name,) in conn.execute("SELECT DISTINCT app FROM django_migrations")}


def sessions_on(hub: Hub) -> list:
    with hubs._maintenance() as conn:
        return conn.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", [hub.db_name]
        ).fetchall()


def run_pass(now: dt.datetime | None = None) -> None:
    worker._activations(now or timezone.now())


# ── What is due in a hub ────────────────────────────────────────────────────────────────────────────────────────
# (A ``django_db`` test: pytest-django sets the test databases up for the session before any of this module's.)


@pytest.mark.django_db
def test_what_is_due_is_creating_unless_put_off_and_failed_once_its_next_try_came():
    from base.tenancy.context import use_shared_database

    with use_shared_database():
        _what_is_due()


def _what_is_due():
    from base.queries import activations_due

    now = timezone.now()
    later, before = now + dt.timedelta(seconds=30), now - dt.timedelta(seconds=1)
    for app, state, next_attempt_at, target in [
        ("printing", CREATING, None, "0001_a"),
        ("website", CREATING, later, ""),
        ("flow", FAILED, before, "0002_b"),
        ("payment", FAILED, later, ""),
        ("schedule", ON, None, ""),
        ("gone_app", CREATING, None, ""),
    ]:
        AppActivation.objects.create(
            host="c", app=app, state=state, chosen=True, next_attempt_at=next_attempt_at, target=target
        )

    assert activations_due("c", now) == {"printing": "0001_a", "flow": "0002_b"}
    assert activations_due("d", now) == {}


# ── Spec §14, 1: turned on in A, its tables are made in A and nowhere else ──────────────────────────────────────


def test_turned_on_in_a_its_tables_are_made_there_only_and_bs_database_is_never_opened(business):
    a, b = business("a"), business("b")
    assert turn_on(a)["state"] == "creating"
    assert HubDue.objects.filter(hub_id=a.pk).exists()
    assert not hubs.hub_tables([APP]) & tables(a)

    with hubs.watched() as sent:
        run_pass()

    assert row(a).state == ON and row(a).chosen
    assert hubs.hub_tables([APP]) <= tables(a) and APP in recorded(a)
    assert not hubs.hub_tables([APP]) & tables(b) and APP not in recorded(b)
    assert not [alias for alias in sent if b.db_name in alias or b.id.hex in alias]
    assert APP in fresh(a).schema_apps
    assert [name for name, _ in outbox(a)] == [events.APP_ACTIVATION_REQUESTED, events.APP_ENABLED]
    assert outbox(a)[-1][1] == {"app": APP, "along": []}
    told = [statement for statement in sent.get("default", []) if "pg_notify" in statement]
    assert told, "the live notice of the app on goes out after the COMMIT"


def test_what_it_needs_is_made_in_the_same_plan_and_goes_on_with_it(business):
    a = business("a")
    turn_on(a, "sale")

    run_pass()

    assert {label: (row(a, label).state, row(a, label).chosen) for label in ("sale", "tax", "customer")} == {
        "sale": (ON, True),
        "tax": (ON, False),
        "customer": (ON, False),
    }
    assert hubs.hub_tables(["sale", "tax", "customer"]) <= tables(a)
    assert outbox(a)[-1] == (events.APP_ENABLED, {"app": "sale", "along": ["customer", "tax"]})


def test_the_pass_leaves_no_connection_to_the_hubs_database_open(business):
    a = business("a")
    turn_on(a)

    run_pass()

    assert sessions_on(a) == []


# ── Spec §14, 4: a failure leaves it failed with why, never on; the next try finishes it ────────────────────────


def test_making_its_tables_failing_leaves_it_failed_with_why_and_a_try_a_minute_later_finishes_it(business, monkeypatch):
    a = business("a")
    turn_on(a)
    real = migrator.ensure_schema
    monkeypatch.setattr(migrator, "ensure_schema", lambda hub, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    now = timezone.now()

    run_pass(now)

    failed = row(a)
    assert (failed.state, failed.attempts) == (FAILED, 1)
    assert "boom" in failed.last_error
    assert dt.timedelta(seconds=55) <= failed.next_attempt_at - now <= dt.timedelta(seconds=65)
    assert outbox(a)[-1] == (events.APP_ACTIVATION_FAILED, {"apps": [APP], "error": "schema_failed"})
    assert not hubs.hub_tables([APP]) & tables(a)

    monkeypatch.setattr(migrator, "ensure_schema", real)
    run_pass(now + dt.timedelta(seconds=30))  # not due yet
    assert row(a).state == FAILED

    run_pass(now + dt.timedelta(seconds=61))
    done = row(a)
    assert (done.state, done.attempts, done.last_error, done.next_attempt_at) == (ON, 0, "", None)
    assert hubs.hub_tables([APP]) <= tables(a)


@pytest.mark.parametrize(("attempts", "wait"), [(1, 300), (2, 900), (3, 3600), (9, 3600)])
def test_each_failure_waits_longer_up_to_an_hour(business, monkeypatch, attempts, wait):
    a = business("a")
    turn_on(a)
    with use_hub(fresh(a)):
        AppActivation.objects.filter(host=a.slug, app=APP).update(attempts=attempts)
    monkeypatch.setattr(migrator, "ensure_schema", lambda hub, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    now = timezone.now()

    run_pass(now)

    failed = row(a)
    assert failed.attempts == attempts + 1
    assert abs((failed.next_attempt_at - now).total_seconds() - wait) < 5


# ── Spec §14, 3: two at once in one hub, one waits or is put off; no 42P07 ──────────────────────────────────────


def test_a_schema_held_by_another_run_puts_it_off_30_seconds(business):
    a = business("a")
    turn_on(a)
    now = timezone.now()
    with hubs._maintenance(a.db_name) as holder:
        holder.execute("SELECT pg_advisory_lock(hashtext('erplora.schema'))")
        run_pass(now)
        waiting = row(a)
        assert waiting.state == CREATING and waiting.attempts == 0
        assert dt.timedelta(seconds=25) <= waiting.next_attempt_at - now <= dt.timedelta(seconds=35)
        assert not hubs.hub_tables([APP]) & tables(a)
        run_pass(now + dt.timedelta(seconds=10))  # not due yet
        assert row(a).state == CREATING

    run_pass(now + dt.timedelta(seconds=40))  # its wait counts from when the lock was found held (1 s of waiting)
    assert row(a).state == ON


def test_two_workers_at_once_on_one_hub_never_collide_and_it_goes_on_once(business, monkeypatch):
    a = business("a")
    turn_on(a)
    real = migrator.ensure_schema
    both_in = threading.Barrier(2)

    def together(hub, **kwargs):
        both_in.wait(timeout=10)
        return real(hub, **kwargs)

    monkeypatch.setattr(migrator, "ensure_schema", together)
    monkeypatch.setattr(worker, "ACTIVATION_LOCK_WAIT", 30.0)
    failures: list[BaseException] = []

    def one_worker():
        try:
            worker._activate(fresh(a), timezone.now())
        except BaseException as error:  # noqa: BLE001 - what a thread raised is asserted below
            failures.append(error)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=one_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert failures == []
    assert row(a).state == ON and row(a).attempts == 0
    assert [name for name, _ in outbox(a)].count(events.APP_ENABLED) == 1


# ── Turned off meanwhile: it stays off, its tables made ─────────────────────────────────────────────────────────


def test_turned_off_while_its_tables_are_made_it_stays_off_with_them(business, monkeypatch):
    a = business("a")
    turn_on(a)
    real = migrator.ensure_schema

    def turned_off_meanwhile(hub, **kwargs):
        turn_off(a)
        return real(hub, **kwargs)

    monkeypatch.setattr(migrator, "ensure_schema", turned_off_meanwhile)

    run_pass()

    assert row(a).state == OFF
    assert hubs.hub_tables([APP]) <= tables(a) and APP in fresh(a).schema_apps
    assert events.APP_ENABLED not in [name for name, _ in outbox(a)]


# ── A worker of an older code than the request's leaves it to one of that code ─────────────────────────────────


def test_a_request_of_a_newer_code_waits_for_a_worker_of_that_code(business, caplog):
    a = business("a")
    turn_on(a)
    with use_hub(fresh(a)):
        AppActivation.objects.filter(host=a.slug, app=APP).update(target="9999_of_a_newer_code")
    now = timezone.now()

    run_pass(now)

    waiting = row(a)
    assert waiting.state == CREATING
    assert dt.timedelta(seconds=55) <= waiting.next_attempt_at - now <= dt.timedelta(seconds=65)
    assert not hubs.hub_tables([APP]) & tables(a)
    assert "base.app.activation_newer_code" in caplog.text


def test_the_request_names_the_codes_leaf_of_what_it_asks_for(business):
    a = business("a")
    turn_on(a, "sale")

    leaves = migrator.code_migrations().leaves
    assert {label: row(a, label).target for label in ("sale", "tax", "customer")} == {
        label: leaves[label] for label in ("sale", "tax", "customer")
    }


# ── Which hubs it looks at ──────────────────────────────────────────────────────────────────────────────────────


def test_the_pass_takes_only_the_hubs_rung(business):
    a = business("a")
    turn_on(a)
    HubDue.objects.filter(hub_id=a.pk).delete()  # a ring lost

    with hubs.watched() as sent:
        run_pass()

    assert row(a).state == CREATING
    assert not [alias for alias in sent if a.id.hex in alias]


# ── Its retries go by hub_due, which the pass over the hubs due leaves to it (PLAN-DB §8) ─────────────────────────


def due_at(hub: Hub):
    return HubDue.objects.filter(hub_id=hub.pk).values_list("due_at", flat=True).first()


def test_a_schema_held_puts_it_off_30_seconds_in_hub_due_and_the_pass_over_the_hubs_due_leaves_that_ring(business):
    from base.tenancy import provision

    a = business("a")
    turn_on(a)
    now = timezone.now()
    with hubs._maintenance(a.db_name) as holder:
        holder.execute("SELECT pg_advisory_lock(hashtext('erplora.schema'))")
        run_pass(now)
    assert dt.timedelta(seconds=25) <= due_at(a) - now <= dt.timedelta(seconds=35)

    provision.run_due(now + dt.timedelta(seconds=40))  # the worker's own pass over hub_due, after the ring came

    assert due_at(a) is not None
    run_pass(now + dt.timedelta(seconds=40))
    assert row(a).state == ON


def test_a_failure_rings_its_hub_at_its_next_try_and_nothing_pending_ends_the_ring(business, monkeypatch):
    a = business("a")
    turn_on(a)
    real = migrator.ensure_schema
    monkeypatch.setattr(migrator, "ensure_schema", lambda hub, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    now = timezone.now()

    run_pass(now)

    assert due_at(a) == row(a).next_attempt_at
    monkeypatch.setattr(migrator, "ensure_schema", real)
    run_pass(row(a).next_attempt_at)
    assert row(a).state == ON
    assert due_at(a) is None


def test_a_ring_with_other_work_of_the_hub_is_left_to_it(business):
    a = business("a")
    turn_on(a)
    Hub.objects.filter(pk=a.pk).update(reset_requested_at=timezone.now(), reset_sections={"apps": ["sale"]})

    run_pass()

    assert row(a).state == ON
    assert due_at(a) is not None  # the reset still to do keeps it due


# ── A ring lost is found by the sweep of the hubs served: every 10 min the active ones, daily all (PLAN-DB §8) ─────


def activation_reads(sent: dict[str, list[str]], hub: Hub) -> int:
    return sum(
        1
        for alias, statements in sent.items()
        if hub.id.hex in alias
        for statement in statements
        if '"base_appactivation"' in statement
    )


def visited(hub: Hub, day) -> None:
    from control.models import HubVisit

    HubVisit.objects.create(host=hub.slug, day=day, saas_user_id="saas:1")


def test_the_sweep_of_the_hubs_served_rings_a_hub_whose_ring_was_lost(business):
    from base.tenancy.context import use_control

    a = business("a")
    turn_on(a)
    HubDue.objects.filter(hub_id=a.pk).delete()
    now = timezone.now()

    with use_control():
        worker._hubs(now)
    assert due_at(a) is not None and due_at(a) <= timezone.now()

    run_pass(timezone.now())
    assert row(a).state == ON


@pytest.mark.parametrize(("active", "again"), [(True, dt.timedelta(minutes=10)), (False, dt.timedelta(days=1))])
def test_the_sweep_looks_into_a_hub_only_at_its_pace(business, active, again):
    from base.tenancy.context import use_control

    a = business("a")
    now = timezone.now()
    if active:
        visited(a, now.date() - dt.timedelta(days=6))
    with use_control():
        worker._hubs(now)  # looked into once: the first pass of the process

        with hubs.watched() as sent:
            worker._hubs(now + dt.timedelta(minutes=1))
            worker._hubs(now + again - dt.timedelta(seconds=1))
        assert activation_reads(sent, a) == 0

        with hubs.watched() as sent:
            worker._hubs(now + again)
        assert activation_reads(sent, a) > 0


# ── PLAN-DB §7, rollback: a database ahead of this code holds back only what it is about ────────────────────────


def test_the_platform_ahead_of_this_code_does_not_hold_back_another_apps_tables(business):
    a = business("a")
    Hub.objects.filter(pk=a.pk).update(schema_apps={"base": "0099_of_a_later_code", "live": "0001_initial"})
    turn_on(a)

    run_pass()

    assert row(a).state == ON


@pytest.mark.parametrize("ahead", ["target", "schema_apps"])
def test_an_app_asked_by_a_code_that_is_gone_fails_as_code_behind_after_ten_minutes_and_is_tried_again(
    business, ahead
):
    a = business("a")
    turn_on(a)
    if ahead == "target":
        with use_hub(fresh(a)):
            AppActivation.objects.filter(host=a.slug, app=APP).update(target="9999_of_a_code_rolled_back")
    else:
        Hub.objects.filter(pk=a.pk).update(schema_apps={**fresh(a).schema_apps, APP: "9999_of_a_code_rolled_back"})
    now = timezone.now()

    run_pass(now)
    assert row(a).state == CREATING  # a newer worker may still be coming: put off

    with use_hub(fresh(a)):
        AppActivation.objects.filter(host=a.slug, app=APP).update(changed_at=now - dt.timedelta(minutes=10))
    run_pass(now + dt.timedelta(minutes=2))  # past its wait of a minute

    failed = row(a)
    assert (failed.state, failed.attempts) == (FAILED, 1)
    assert failed.last_error.startswith("code_behind: ")
    assert failed.next_attempt_at is not None and due_at(a) == failed.next_attempt_at
    assert outbox(a)[-1] == (events.APP_ACTIVATION_FAILED, {"apps": [APP], "error": "code_behind"})


@pytest.mark.parametrize("status", [Hub.Status.REQUESTED, Hub.Status.MIGRATING, Hub.Status.CANCELLED, Hub.Status.PURGED])
def test_a_hub_not_ready_is_never_entered(business, status):
    a = business("a")
    turn_on(a)
    Hub.objects.filter(pk=a.pk).update(status=status)

    with hubs.watched() as sent:
        run_pass()

    assert not [alias for alias in sent if a.id.hex in alias]


def test_a_demo_whose_time_is_up_is_never_entered(business):
    a = business("a", is_demo=True, expires_at=timezone.now() + dt.timedelta(hours=1))
    turn_on(a)
    Hub.objects.filter(pk=a.pk).update(expires_at=timezone.now() - dt.timedelta(seconds=1))

    with hubs.watched() as sent:
        run_pass()

    assert not [alias for alias in sent if a.id.hex in alias]


def test_a_hub_that_fails_is_logged_and_the_others_are_served(business, monkeypatch, caplog):
    a, b = business("a"), business("b")
    turn_on(a)
    turn_on(b)
    real = worker._activate_in

    def broken(hub, now):
        if hub.pk == a.pk:
            raise RuntimeError("the hub's database went away")
        return real(hub, now)

    monkeypatch.setattr(worker, "_activate_in", broken)

    run_pass()

    assert row(b).state == ON and row(a).state == CREATING
    assert "went away" in caplog.text


# ── Spec §14, 2: migrate_hubs with a new migration of X touches A, never B (B's database is not even opened) ────


def test_migrate_hubs_brings_xs_new_migration_to_a_and_never_opens_b(business, opened_at):
    a, b = business("a"), business("b")
    turn_on(a)
    run_pass()
    old = "0002_print_device"  # as A was left by the code before printing's last migration
    alias = tenancy_connections.register_ddl_alias(a.db_name)
    try:
        from django.db.migrations.executor import MigrationExecutor

        MigrationExecutor(connections[alias]).migrate([(APP, old)])
    finally:
        connections[alias].close()
    Hub.objects.filter(pk=a.pk).update(schema_apps={**fresh(a).schema_apps, APP: old})
    # B never turned X on: it lacks it and is at the leaf of what it has, never behind.
    Hub.objects.filter(pk=b.pk).update(
        schema_apps={label: name for label, name in fresh(a).schema_apps.items() if label != APP}
    )
    opened_at.clear()

    result = migrator.migrate_hubs_behind(workers=1)

    assert a.slug in result.migrated and b.slug not in result.migrated
    assert fresh(a).schema_apps[APP] == migrator.code_migrations().leaves[APP]
    assert not [name for _host, name in opened_at if name == b.db_name]
    assert APP not in recorded(b)


# ── Spec §14, 5 and 6: an app not on is never reached in a hub, whatever a process kept ─────────────────────────


def read_printing(hub: Hub):
    op = get("printing.settings.get")
    with use_hub(fresh(hub)):
        return op(as_admin(hub), op.input())


def test_while_its_tables_are_made_its_operations_say_app_inactive_never_a_database_error(business):
    from live.errors import AppInactive

    a = business("a")
    turn_on(a)

    with pytest.raises(AppInactive):
        read_printing(a)


def test_a_process_whose_cache_lags_says_app_inactive_until_it_forgets_never_reaches_tables_before_on(business):
    from django.core.cache import cache
    from live.errors import AppInactive

    a = business("a")
    turn_on(a)
    keys = (activation.OFF_APPS_CACHE + a.slug, activation.CREATING_APPS_CACHE + a.slug)
    with use_hub(fresh(a)):
        kept = {keys[0]: sorted(activation.off_apps(Scope("host", a.slug))), keys[1]: [APP]}
    assert APP in kept[keys[0]]

    run_pass()
    cache.set_many(kept, 60)  # another process read the rows before the worker's COMMIT, and kept them

    with pytest.raises(AppInactive):
        read_printing(a)
    activation.forget(a.slug)
    assert read_printing(a) is not None


def test_an_app_b_never_turned_on_says_app_inactive_in_b_never_a_database_error(business):
    from live.errors import AppInactive

    a, b = business("a"), business("b")
    turn_on(a)
    run_pass()
    assert hubs.hub_tables([APP]) <= tables(a) and not hubs.hub_tables([APP]) & tables(b)

    with pytest.raises(AppInactive):
        read_printing(b)


# ── Spec §14, 8: turning X on changes nothing of the process ────────────────────────────────────────────────────


def test_turning_an_app_on_changes_neither_the_installed_apps_nor_the_urls_nor_the_api_routes(business):
    from django.apps import apps as django_apps
    from django.conf import settings
    from django.urls import get_resolver

    from config.api import api

    def snapshot():
        return (
            list(settings.INSTALLED_APPS),
            [config.label for config in django_apps.get_app_configs()],
            sorted(str(pattern.pattern) for pattern in get_resolver().url_patterns),
            sorted(api.get_openapi_schema()["paths"]),
        )

    before = snapshot()
    a = business("a")
    turn_on(a)
    run_pass()

    assert row(a).state == ON
    assert snapshot() == before


# ── Spec §14, 11: each app is made alone from nothing on the platform's template ────────────────────────────────


@pytest.mark.parametrize("label", sorted(activation.module_graph()))
def test_each_app_is_made_alone_with_what_it_requires_on_the_platforms_template(business, label):
    a = business("a")
    turn_on(a, label)

    run_pass()

    expected = {label} | activation.needs([label], activation.module_graph())
    assert {name for name in expected if row(a, name).state != ON} == set()
    assert hubs.hub_tables(expected) <= tables(a)
    others = set(activation.module_graph()) - expected
    assert not hubs.hub_tables(others) & tables(a)
