"""System's commands on the events the relay gave up on (APP-BASE-7; the old hub's ``/api/hub/events/:id/retry``,
``retry-all`` and ``:id/discard``, HUB-F55…F57): resend one, resend all, discard one. For who runs the business; one
hub never touches another's; each records its event in its transaction and the live queries follow after the COMMIT.
A delivery the relay gives up on is told to its hub's live queries too (the bell rises at once, BASE-F10).
"""

import datetime as dt
import json

import psycopg
import pytest
from django.db import connections
from django.utils import timezone
from live.context import OperationContext, Scope
from live.errors import Conflict, NotFound, PermissionDenied
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base import events, relay, services
from base.models import EventDelivery

A = Scope("host", "a")
B = Scope("host", "b")
ADMIN = "base.administer_hub"


def ctx(*permissions, scope=A, actor="ana"):
    return OperationContext(scope=scope, actor=actor, permissions=frozenset(permissions or (ADMIN,)), language="en")


def run(name, context=None, **data):
    op = get(name)
    return op(context or ctx(), op.input.model_validate(data)).model_dump(mode="json")


def dead(scope=A, app="invoice", name="sale.sale.completed", status=EventDelivery.Status.DEAD):
    outbox_event = OutboxEvent.objects.create(
        scope_kind=scope.kind, scope_key=scope.key, name=name, delivered_at=timezone.now()
    )
    return EventDelivery.objects.create(
        event=outbox_event,
        app_label=app,
        status=status,
        attempts=relay.MAX_ATTEMPTS,
        last_error="Conflict: Set up the issuer first.",
        next_attempt_at=timezone.now() - dt.timedelta(days=1),
    )


def recorded(name):
    return list(OutboxEvent.objects.filter(name=name).values_list("scope_key", "payload"))


@pytest.mark.parametrize(
    "name", ["base.failed_event.retry", "base.failed_event.retry_all", "base.failed_event.discard"]
)
def test_each_command_is_for_who_runs_the_business_and_told_to_the_assistant(name, db):
    op = get(name)
    assert (op.kind, op.permission) == ("command", ADMIN)
    assert op.ai and op.ai["description"]


# ── Resend one (BASE-G92) ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_resending_puts_it_back_in_the_queue_with_its_attempts_at_zero():
    delivery = dead()
    before = timezone.now()

    assert run("base.failed_event.retry", id=str(delivery.id)) == {"id": str(delivery.id)}

    delivery.refresh_from_db()
    assert (delivery.status, delivery.attempts, delivery.last_error) == ("pending", 0, "")
    assert delivery.next_attempt_at >= before
    assert recorded(events.FAILED_EVENT_RETRIED) == [("a", {"id": str(delivery.id), "count": 1})]


@pytest.mark.django_db
def test_resent_it_is_delivered_only_to_the_app_that_had_failed():
    delivery = dead()
    other = EventDelivery.objects.create(
        event=delivery.event, app_label="inventory", status="delivered", next_attempt_at=timezone.now()
    )
    run("base.failed_event.retry", id=str(delivery.id))
    got = []

    services.relay_deliver_next(
        timezone.now(),
        deliver=lambda app, event: got.append((app, event.name)),
        listeners=lambda _: [],
        max_depth=relay.MAX_EVENT_DEPTH,
        max_attempts=relay.MAX_ATTEMPTS,
        backoff=relay.backoff,
    )

    assert got == [("invoice", "sale.sale.completed")]
    delivery.refresh_from_db()
    other.refresh_from_db()
    assert (delivery.status, other.status) == ("delivered", "delivered")


@pytest.mark.django_db
@pytest.mark.parametrize("status", [EventDelivery.Status.PENDING, EventDelivery.Status.DELIVERED])
def test_only_a_failed_event_is_resent(status):
    delivery = dead(status=status)

    with pytest.raises(NotFound):
        run("base.failed_event.retry", id=str(delivery.id))


@pytest.mark.django_db
def test_another_hubs_failed_event_is_not_found_and_left_alone():
    delivery = dead(B)

    with pytest.raises(NotFound):
        run("base.failed_event.retry", id=str(delivery.id))
    with pytest.raises(NotFound):
        run("base.failed_event.discard", id=str(delivery.id))

    delivery.refresh_from_db()
    assert delivery.status == "dead"


@pytest.mark.django_db
def test_an_unknown_id_is_not_found():
    with pytest.raises(NotFound):
        run("base.failed_event.retry", id="0190f3a4-b5c6-7d8e-9fa0-b1c2d3e4f5a6")


@pytest.mark.django_db
def test_a_failed_event_for_an_app_that_is_not_on_is_refused_with_why(monkeypatch):
    monkeypatch.setattr("base.entitlement.blocked_apps", lambda scope: frozenset({"invoice"}))
    delivery = dead()

    with pytest.raises(Conflict) as refused:
        run("base.failed_event.retry", id=str(delivery.id))

    assert refused.value.code == "base.failed_event_app_off"
    delivery.refresh_from_db()
    assert delivery.status == "dead"


@pytest.mark.django_db
def test_a_cashier_cannot_resend_nor_discard():
    delivery = dead()
    cashier = ctx("base.view_home")

    for name in ("base.failed_event.retry", "base.failed_event.discard"):
        with pytest.raises(PermissionDenied):
            run(name, cashier, id=str(delivery.id))
    with pytest.raises(PermissionDenied):
        run("base.failed_event.retry_all", cashier)


# ── Resend all (BASE-G93) ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_resending_all_resends_every_failed_event_of_this_hub_that_can_be(monkeypatch):
    monkeypatch.setattr("base.entitlement.blocked_apps", lambda scope: frozenset({"kitchen"}))
    mine = [dead() for _ in range(120)]  # more than the list shows
    stuck = dead(app="kitchen")
    discarded = dead(status=EventDelivery.Status.DISCARDED)
    theirs = dead(B)

    assert run("base.failed_event.retry_all") == {"count": 120}

    assert set(EventDelivery.objects.filter(pk__in=[d.pk for d in mine]).values_list("status", flat=True)) == {
        "pending"
    }
    for delivery, status in ((stuck, "dead"), (discarded, "discarded"), (theirs, "dead")):
        delivery.refresh_from_db()
        assert delivery.status == status
    assert recorded(events.FAILED_EVENT_RETRIED) == [("a", {"count": 120})]


@pytest.mark.django_db
def test_resending_all_with_nothing_to_resend_records_nothing():
    assert run("base.failed_event.retry_all") == {"count": 0}
    assert recorded(events.FAILED_EVENT_RETRIED) == []


# ── Discard one (BASE-G94) ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_discarding_closes_it_for_good_with_who_when_and_why_and_keeps_the_row():
    delivery = dead()
    before = timezone.now()

    run("base.failed_event.discard", ctx(actor="ana@example.com"), id=str(delivery.id), reason="Invoiced by hand.")

    delivery.refresh_from_db()
    assert (delivery.status, delivery.closed_by, delivery.close_reason) == (
        "discarded",
        "ana@example.com",
        "Invoiced by hand.",
    )
    assert delivery.closed_at >= before
    assert delivery.last_error == "Conflict: Set up the issuer first."  # what went wrong stays, for the audit
    assert recorded(events.FAILED_EVENT_DISCARDED) == [("a", {"id": str(delivery.id)})]
    # The relay never takes it again.
    assert (
        services.relay_deliver_next(
            timezone.now() + dt.timedelta(days=2),
            deliver=lambda app, event: pytest.fail("a discarded event was delivered"),
            listeners=lambda _: [],
            max_depth=relay.MAX_EVENT_DEPTH,
            max_attempts=relay.MAX_ATTEMPTS,
            backoff=relay.backoff,
        )
        is None
    )


@pytest.mark.django_db
def test_a_reason_is_optional_and_bounded(monkeypatch):
    monkeypatch.setattr("base.entitlement.blocked_apps", lambda scope: frozenset({"invoice"}))
    delivery = dead()  # an event that cannot be resent can still be discarded

    run("base.failed_event.discard", id=str(delivery.id))

    delivery.refresh_from_db()
    assert (delivery.status, delivery.close_reason) == ("discarded", "")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        get("base.failed_event.discard").input.model_validate({"id": str(delivery.id), "reason": "x" * 501})


@pytest.mark.django_db
def test_a_discarded_event_cannot_be_discarded_again_nor_resent():
    delivery = dead(status=EventDelivery.Status.DISCARDED)

    for name in ("base.failed_event.discard", "base.failed_event.retry"):
        with pytest.raises(NotFound):
            run(name, id=str(delivery.id))


# ── Over HTTP ─────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/system/failed-events/retry", "base.failed_event.retry"),
        ("/system/failed-events/retry_all", "base.failed_event.retry_all"),
        ("/system/failed-events/discard", "base.failed_event.discard"),
    ],
)
def test_the_routes_are_bound_to_their_commands(path, operation, db):
    from django.urls import resolve

    from base.api import router

    [route] = router.path_operations[path].operations
    assert (route.methods, route.operation_id) == (["POST"], operation)
    assert resolve(f"/api{path}").url_name


@pytest.mark.django_db
def test_an_owner_resends_over_http_and_a_cashier_is_refused(client, make_user):
    delivery = dead()
    body = json.dumps({"id": str(delivery.id)})

    client.force_login(make_user("eva", host="a", role="hub_employee"))
    refused = client.post(
        "/api/system/failed-events/retry", body, content_type="application/json", HTTP_HOST="a.localhost:8000"
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")

    client.force_login(make_user("ana", host="a", role="hub_owner"))
    answered = client.post(
        "/api/system/failed-events/retry", body, content_type="application/json", HTTP_HOST="a.localhost:8000"
    )
    assert (answered.status_code, answered.json()) == (200, {"id": str(delivery.id)})


# ── Live: what changes the failed events re-runs their list and the bell ───────────────────────────────────


def test_the_failed_events_and_the_bell_follow_what_changes_them():
    for name in (events.FAILED_EVENT_CREATED, events.FAILED_EVENT_RETRIED, events.FAILED_EVENT_DISCARDED):
        assert {"base.failed_event.list", "base.bell.counters"} <= live_registry.affected([name])
    # The photo may turn the app a failed event was for on or off: whether it can be resent changes.
    assert "base.failed_event.list" in live_registry.affected([events.HUB_STATE_APPLIED])


@pytest.fixture
def listen():
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    sessions = []

    def open_session(scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout=0.5):
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_a_delivery_given_up_is_told_to_its_hub_only_after_the_commit(transactional_db, listen):
    """BASE-F10: the bell of who runs the hub rises at once, without waiting nor reloading; another hub hears nothing."""
    on_a, on_b = listen(A), listen(B)
    outbox_event = OutboxEvent.objects.create(scope_kind="host", scope_key="a", name="sale.sale.completed")
    now = timezone.now()
    services.relay_take_events(now, listeners=lambda _: ["invoice"], limit=10, max_depth=relay.MAX_EVENT_DEPTH)

    def fail(app, event):
        raise RuntimeError("the reaction crashed")

    def attempt(at, max_attempts):
        return services.relay_deliver_next(
            at,
            deliver=fail,
            listeners=lambda _: [],
            max_depth=relay.MAX_EVENT_DEPTH,
            max_attempts=max_attempts,
            backoff=relay.backoff,
        )

    attempt(now, max_attempts=2)  # a first failure: retried, not given up
    assert events.FAILED_EVENT_CREATED not in heard(on_a)
    attempt(now + dt.timedelta(hours=2), max_attempts=2)  # the last attempt: given up

    assert EventDelivery.objects.get(event=outbox_event).status == "dead"
    assert events.FAILED_EVENT_CREATED in heard(on_a)
    assert heard(on_b) == set()


def test_a_delivery_past_the_deepest_level_is_told_too(transactional_db, listen):
    on_a = listen(A)
    OutboxEvent.objects.create(scope_kind="host", scope_key="a", name="sale.sale.completed")

    services.relay_take_events(timezone.now(), listeners=lambda _: ["invoice"], limit=10, max_depth=-1)

    assert events.FAILED_EVENT_CREATED in heard(on_a)


@pytest.mark.django_db(transaction=True)
def test_resending_is_heard_in_its_hub_after_the_commit(listen):
    on_a, on_b = listen(A), listen(B)
    delivery = dead()

    run("base.failed_event.retry", id=str(delivery.id))

    assert events.FAILED_EVENT_RETRIED in heard(on_a)
    assert heard(on_b) == set()
