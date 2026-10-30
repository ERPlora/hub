"""System's queries (APP-BASE-7; the old hub's ``GET /api/system`` and ``/api/hub/events/dead``): the status of the hub
(``base.system.status``), its log of events between apps (``base.event.list``) and the events the relay gave up on
(``base.failed_event.list``). All three are for who runs the business (hub#2519: the errors may carry a customer's
tax id and name), and a hub never sees another's.
"""

import datetime as dt

import pytest
from django.urls import resolve
from django.utils import timezone
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from base.models import EventDelivery, Hub

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")
ADMIN = "base.administer_hub"


def run(name, *permissions, scope=A, language="en", **data):
    op = get(name)
    ctx = OperationContext(scope=scope, actor="ana", permissions=frozenset(permissions), language=language)
    return op(ctx, op.input.model_validate(data)).model_dump(mode="json")


def event(scope=A, name="sale.sale.completed", at=None, taken=True):
    at = at or timezone.now()
    return OutboxEvent.objects.create(
        scope_kind=scope.kind,
        scope_key=scope.key,
        name=name,
        payload={"id": "s1"},
        created_at=at,
        delivered_at=at if taken else None,
    )


def delivery(outbox_event, app="invoice", status=EventDelivery.Status.DEAD, attempts=8, error="Conflict: no issuer"):
    return EventDelivery.objects.create(
        event=outbox_event,
        app_label=app,
        status=status,
        attempts=attempts,
        last_error=error,
        next_attempt_at=timezone.now(),
    )


@pytest.mark.parametrize("name", ["base.system.status", "base.event.list", "base.failed_event.list"])
def test_each_query_is_for_who_runs_the_business_and_told_to_the_assistant(name):
    op = get(name)
    assert (op.kind, op.permission) == ("query", ADMIN)
    assert op.ai and op.ai["description"]
    with pytest.raises(PermissionDenied):
        run(name, "base.view_home")


# ── base.system.status (BASE-G45, G88, G89) ──────────────────────────────────────────────────────────────


def test_the_status_says_the_release_and_where_the_data_lives(settings):
    settings.APP_VERSION = "4da2a10c9e1f5b7d8a6c3e2f1b0a9d8c7e6f5a4b"
    settings.APP_RELEASED_AT = "2026-10-23T20:50:00+02:00"

    assert run("base.system.status", ADMIN) == {
        "version": "4da2a10",
        "released_at": "2026-10-23T18:50:00Z",
        # Phase 1: every business on the one shared database (``db_name`` empty).
        "shared_database": True,
    }


def test_a_hub_with_its_own_database_says_so(settings):
    settings.APP_VERSION, settings.APP_RELEASED_AT = "", ""
    Hub.objects.filter(slug="b").update(db_name="hub_0190f3a4b5c67d8e9fa0b1c2d3e4f5a6")

    assert run("base.system.status", ADMIN, scope=B)["shared_database"] is False
    assert run("base.system.status", ADMIN)["shared_database"] is True


def test_without_a_release_it_runs_the_development_build_and_never_makes_up_a_date(settings):
    settings.APP_VERSION, settings.APP_RELEASED_AT = "", "not a date"

    status = run("base.system.status", ADMIN)

    assert (status["version"], status["released_at"]) == ("dev", None)


def test_the_status_carries_no_error_text(settings):
    """hub#2566: the old history sent the verbatim error of a rollback to any session; nothing like it travels now."""
    assert set(run("base.system.status", ADMIN)) == {"version", "released_at", "shared_database"}


# ── base.event.list: the log of events between apps (BASE-G90) ──────────────────────────────────────────────


def test_the_log_is_this_hubs_newest_first_with_a_level_and_what_happened():
    now = timezone.now()
    delivered = event(at=now - dt.timedelta(minutes=5))
    delivery(delivered, status=EventDelivery.Status.DELIVERED, attempts=1, error="")
    retrying = event(at=now - dt.timedelta(minutes=4))
    delivery(retrying, status=EventDelivery.Status.PENDING, attempts=2)
    dead = event(at=now - dt.timedelta(minutes=3))
    delivery(dead)
    event(name="customer.customer.created", at=now - dt.timedelta(minutes=2))  # nobody listens
    event(at=now - dt.timedelta(minutes=1), taken=False)  # not handed over yet
    event(B, at=now)  # another hub's

    entries = run("base.event.list", ADMIN)["entries"]

    assert [(e["name"], e["app"], e["app_name"], e["level"], e["detail"]) for e in entries] == [
        ("sale.sale.completed", "sale", "Sales & POS", "info", "Waiting to be handed to the apps."),
        ("customer.customer.created", "customer", "Customers", "info", "No app listens to it."),
        ("sale.sale.completed", "sale", "Sales & POS", "error", "Invoicing could not take it: it is in Failed events."),
        ("sale.sale.completed", "sale", "Sales & POS", "warning", "Invoicing failed 2 times; it is retried by itself."),
        ("sale.sale.completed", "sale", "Sales & POS", "info", "Delivered to Invoicing."),
    ]
    assert entries[2]["id"] == str(dead.id)
    # The error itself stays in Failed events: the log only says where it went.
    assert all("no issuer" not in e["detail"] for e in entries)


def test_the_log_keeps_the_last_fifty():
    now = timezone.now()
    for minute in range(55):
        event(at=now - dt.timedelta(minutes=minute))

    entries = run("base.event.list", ADMIN)["entries"]

    assert len(entries) == 50
    assert entries[0]["at"] > entries[-1]["at"]


def test_an_event_given_to_several_apps_says_each_ones_and_takes_the_worst_level():
    outbox_event = event()
    delivery(outbox_event, app="inventory", status=EventDelivery.Status.DELIVERED, attempts=1, error="")
    delivery(outbox_event, app="invoice")
    delivery(outbox_event, app="kitchen", status=EventDelivery.Status.DISCARDED)

    [entry] = run("base.event.list", ADMIN)["entries"]

    assert entry["level"] == "error"
    assert entry["detail"] == (
        "Delivered to Inventory. Invoicing could not take it: it is in Failed events. Discarded for Kitchen."
    )


def test_the_log_speaks_the_persons_language():
    delivery(event(), status=EventDelivery.Status.DELIVERED, attempts=1, error="")

    [entry] = run("base.event.list", ADMIN, language="es")["entries"]

    assert (entry["app_name"], entry["detail"]) == ("Ventas / TPV", "Entregado a Facturación.")


def test_an_event_of_an_app_that_is_gone_keeps_its_label():
    """A label the deployment no longer has (an app retired) is shown as it is, never a crash."""
    delivery(event(name="oldapp.thing.done"), app="oldapp", status=EventDelivery.Status.DELIVERED, error="")

    [entry] = run("base.event.list", ADMIN)["entries"]

    assert (entry["app"], entry["app_name"], entry["detail"]) == ("oldapp", "oldapp", "Delivered to oldapp.")


# ── base.failed_event.list: what the relay gave up on (BASE-G91) ───────────────────────────────────────────


def test_the_failed_events_of_this_hub_newest_first_with_what_failed():
    now = timezone.now()
    older = delivery(event(at=now - dt.timedelta(hours=2)), error="Conflict: Set up the issuer first.")
    newer = delivery(event(name="kitchen.round.fired", at=now - dt.timedelta(hours=1)), app="printing", attempts=3)
    delivery(event(at=now), status=EventDelivery.Status.PENDING)  # still retrying: not failed yet
    delivery(event(at=now), status=EventDelivery.Status.DELIVERED)
    delivery(event(at=now), status=EventDelivery.Status.DISCARDED)
    delivery(event(B, at=now))  # another hub's

    page = run("base.failed_event.list", ADMIN)

    assert page["total"] == 2
    assert [item["id"] for item in page["items"]] == [str(newer.id), str(older.id)]
    first = page["items"][1]
    assert first == {
        "id": str(older.id),
        "event_id": str(older.event_id),
        "name": "sale.sale.completed",
        "source_app": "sale",
        "source_app_name": "Sales & POS",
        "target_app": "invoice",
        "target_app_name": "Invoicing",
        "attempts": 8,
        "occurred_at": first["occurred_at"],
        "last_error": "Conflict: Set up the issuer first.",
        "retryable": True,
    }


def test_one_failed_event_is_read_by_its_id_as_the_list_shows_it_and_only_this_hubs():
    """``base.failed_event.detail``, what names a failed event on the assistant's card: this hub's and still failed;
    another hub's (phase 1 shares the table) or one resent meanwhile is not there."""
    mine = delivery(event())
    assert run("base.failed_event.detail", ADMIN, id=str(mine.id)) == run("base.failed_event.list", ADMIN)["items"][0]
    for other in (delivery(event(B)), delivery(event(), status=EventDelivery.Status.PENDING)):
        with pytest.raises(NotFound):
            run("base.failed_event.detail", ADMIN, id=str(other.id))


def test_a_failed_event_for_an_app_that_is_not_on_cannot_be_retried(monkeypatch):
    """The old hub's «this one cannot be resent»: the app it was for is no longer on in this business."""
    monkeypatch.setattr("base.entitlement.blocked_apps", lambda scope: frozenset({"invoice"}))
    delivery(event())

    [item] = run("base.failed_event.list", ADMIN)["items"]

    assert item["retryable"] is False


def test_the_list_pages_and_cuts_a_long_error():
    now = timezone.now()
    for minute in range(3):
        delivery(event(at=now - dt.timedelta(minutes=minute)), error="x" * 2000)

    page = run("base.failed_event.list", ADMIN, limit=2)

    assert (page["total"], len(page["items"])) == (3, 2)
    assert len(page["items"][0]["last_error"]) == 300
    assert run("base.failed_event.list", ADMIN, limit=2, offset=2)["items"][0]["occurred_at"] < page["items"][1][
        "occurred_at"
    ]


@pytest.mark.parametrize("data", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_the_page_is_bounded(data):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        get("base.failed_event.list").input.model_validate(data)


# ── Over HTTP: every route bound to its operation, refused to whoever does not run the business ────────────


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/system/status", "base.system.status"),
        ("/system/events", "base.event.list"),
        ("/system/failed-events", "base.failed_event.list"),
    ],
)
def test_the_routes_are_bound_to_their_queries(path, operation):
    from base.api import router

    [route] = router.path_operations[path].operations
    assert (route.methods, route.operation_id) == (["GET"], operation)
    assert resolve(f"/api{path}").url_name


@pytest.mark.parametrize("path", ["/api/system/status", "/api/system/events", "/api/system/failed-events"])
def test_a_cashier_is_refused_and_an_owner_is_answered(client, make_user, path):
    """hub#2519: a cashier asked the old hub for System and read the errors of the events, with customers' data."""
    client.force_login(make_user("eva", host="a", role="hub_employee"))
    refused = client.get(path, HTTP_HOST="a.localhost:8000")
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")

    client.force_login(make_user("ana", host="a", role="hub_owner"))
    assert client.get(path, HTTP_HOST="a.localhost:8000").status_code == 200
