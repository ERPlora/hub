"""An app's tables made when a hub with its own database turns it on (S3; PLAN-DB §7, spec 2026-10-11 «tablas al
activar», PLAN §33): ``base.app.enable`` answers 202 ``creating`` and rings the hub's ``hub_due``; the worker makes the
tables (``base.tenancy.migrator.ensure_schema(hub, add=[app, *requires])``) and turns it ``on`` (its event and live
notice), or ``failed`` with why, tried again at 1, 5 and 15 minutes and then every hour, or by hand
(``base.app.retry``). An app whose tables the hub has is on at once (200), and turning one off never drops them. A hub
that still shares phase 1's database keeps turning apps on at once (proposal (i) of round 2026-10-30, until S5).
"""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from base.activation import CREATING, FAILED, OFF, ON
from base.models import AppActivation


# ── The row: its states and what a failure leaves on it ─────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("state", [ON, OFF, CREATING, FAILED])
def test_a_row_is_on_off_creating_or_failed(state):
    row = AppActivation.objects.create(host="c", app="task", state=state, chosen=True)
    row.refresh_from_db()
    assert row.state == state
    assert (row.attempts, row.last_error, row.next_attempt_at) == (0, "", None)


@pytest.mark.django_db
def test_a_failed_row_keeps_its_attempts_its_error_and_its_next_try():
    at = timezone.now() + dt.timedelta(minutes=5)
    AppActivation.objects.create(
        host="c", app="task", state=FAILED, chosen=True, attempts=2, last_error="schema_failed: boom", next_attempt_at=at
    )
    row = AppActivation.objects.get(host="c", app="task")
    assert (row.attempts, row.last_error, row.next_attempt_at) == (2, "schema_failed: boom", at)


@pytest.mark.django_db
def test_any_other_state_is_refused_by_the_database():
    with pytest.raises(IntegrityError), transaction.atomic():
        AppActivation.objects.create(host="c", app="task", state="activating", chosen=False)


# ── Turning one on in a hub with its own database ───────────────────────────────────────────────────────────────

from live.context import OperationContext, Scope  # noqa: E402
from live.errors import Conflict  # noqa: E402
from live.models import OutboxEvent  # noqa: E402
from live.operations import get  # noqa: E402

from base import activation, events  # noqa: E402
from base.tenancy.context import use_hub  # noqa: E402
from base.tenancy.tests import hubs  # noqa: E402
from control.models import Hub, HubDue  # noqa: E402

own = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


def as_admin(hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=frozenset({"*"}), language="en")


def run(hub, name: str, app: str) -> dict:
    op = get(name)
    with use_hub(Hub.objects.get(pk=hub.pk)):
        return op(as_admin(hub), op.input.model_validate({"app": app})).model_dump(mode="json")


def rows_of(hub) -> dict[str, tuple[str, bool]]:
    with use_hub(Hub.objects.get(pk=hub.pk)):
        return {row.app: (row.state, row.chosen) for row in AppActivation.objects.filter(host=hub.slug)}


def given(hub, *, created=(), **states: str) -> None:
    """``hub``'s rows: every app off but those given (``on``, ``creating*``…; ``*`` chosen), and its database's apps
    as control knows them (``schema_apps``)."""
    Hub.objects.filter(pk=hub.pk).update(schema_apps={label: "0001_initial" for label in created})
    with use_hub(Hub.objects.get(pk=hub.pk)):
        AppActivation.objects.filter(host=hub.slug).delete()
        AppActivation.objects.bulk_create(
            AppActivation(host=hub.slug, app=label, state=states.get(label, OFF).rstrip("*"),
                          chosen=states.get(label, "").endswith("*"))
            for label in activation.module_graph()
        )


def outbox(hub) -> list[tuple[str, dict]]:
    with use_hub(Hub.objects.get(pk=hub.pk)):
        return [(event.name, event.payload) for event in OutboxEvent.objects.order_by("id")]


@own
def test_an_app_whose_tables_the_hub_lacks_is_creating_and_the_worker_is_rung_after_the_commit(
    hub_a, django_capture_on_commit_callbacks
):
    given(hub_a)

    with django_capture_on_commit_callbacks(using=hubs.HUB_A_ALIAS) as on_the_hub:
        answer = run(hub_a, "base.app.enable", "printing")
    assert not HubDue.objects.filter(hub_id=hub_a.pk).exists()  # nothing rung before the COMMIT
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        for callback in on_the_hub:
            callback()

    assert answer == {"app": "printing", "state": "creating", "chosen": True, "along": []}
    assert rows_of(hub_a)["printing"] == (CREATING, True)
    assert HubDue.objects.get(hub_id=hub_a.pk).due_at <= timezone.now()
    assert outbox(hub_a) == [(events.APP_ACTIVATION_REQUESTED, {"app": "printing", "along": []})]


@own
def test_what_it_needs_goes_in_the_same_plan_even_when_some_of_it_is_created(hub_a):
    given(hub_a, created=["tax", "customer"])

    answer = run(hub_a, "base.app.enable", "sale")

    assert answer["state"] == "creating"
    assert {item["id"] for item in answer["along"]} == {"tax", "customer"}
    assert {label: rows_of(hub_a)[label] for label in ("sale", "tax", "customer")} == {
        "sale": (CREATING, True),
        "tax": (CREATING, False),
        "customer": (CREATING, False),
    }


@own
def test_an_app_whose_tables_the_hub_has_is_on_at_once(hub_a):
    given(hub_a, created=["printing"])

    answer = run(hub_a, "base.app.enable", "printing")

    assert answer == {"app": "printing", "state": "on", "chosen": True, "along": []}
    assert rows_of(hub_a)["printing"] == (ON, True)
    assert not HubDue.objects.filter(hub_id=hub_a.pk).exists()
    assert [name for name, _ in outbox(hub_a)] == [events.APP_ENABLED]


@own
def test_turning_on_again_one_being_created_changes_nothing_and_rings_again(hub_a, django_capture_on_commit_callbacks):
    given(hub_a, printing="creating*")

    with django_capture_on_commit_callbacks(using=hubs.HUB_A_ALIAS, execute=True):
        answer = run(hub_a, "base.app.enable", "printing")

    assert answer == {"app": "printing", "state": "creating", "chosen": True, "along": []}
    assert rows_of(hub_a)["printing"] == (CREATING, True)
    assert HubDue.objects.filter(hub_id=hub_a.pk).exists()
    assert outbox(hub_a) == []


@own
def test_the_chosen_ones_being_created_count_against_the_plans_limit(hub_a):
    Hub.objects.filter(pk=hub_a.pk).update(state={"plan": {"max_apps": 1}}, state_version=1)
    given(hub_a, printing="creating*")

    with pytest.raises(Exception) as refused:
        run(hub_a, "base.app.enable", "website")

    assert getattr(refused.value, "code", None) == "base.app_limit_reached"
    assert rows_of(hub_a)["website"] == (OFF, False)


@own
def test_one_being_created_is_turned_off_at_once_and_stays_off_when_its_tables_are_made(hub_a):
    given(hub_a, sale="creating*", tax="creating", customer="creating")

    answer = run(hub_a, "base.app.disable", "sale")

    assert answer["state"] == "off"
    assert {label: rows_of(hub_a)[label] for label in ("sale", "tax", "customer")} == {
        "sale": (OFF, False),
        "tax": (OFF, False),
        "customer": (OFF, False),
    }


@own
def test_one_an_app_being_created_needs_cannot_go_off(hub_a):
    given(hub_a, sale="creating*", tax="on", customer="on", created=["tax", "customer"])

    with pytest.raises(Conflict) as refused:
        run(hub_a, "base.app.disable", "tax")

    assert refused.value.code == "base.app_required"
    assert rows_of(hub_a)["tax"] == (ON, False)


@own
def test_a_failed_app_is_tried_again_by_hand(hub_a, django_capture_on_commit_callbacks):
    given(hub_a, printing="failed*")
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        AppActivation.objects.filter(host=hub_a.slug, app="printing").update(
            attempts=3, last_error="schema_failed: boom", next_attempt_at=timezone.now() + dt.timedelta(hours=1)
        )

    with django_capture_on_commit_callbacks(using=hubs.HUB_A_ALIAS, execute=True):
        answer = run(hub_a, "base.app.retry", "printing")

    assert answer == {"app": "printing", "state": "creating", "chosen": True, "along": []}
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        row = AppActivation.objects.get(host=hub_a.slug, app="printing")
    assert (row.state, row.next_attempt_at, row.attempts) == (CREATING, None, 3)
    assert HubDue.objects.filter(hub_id=hub_a.pk).exists()
    assert [name for name, _ in outbox(hub_a)] == [events.APP_ACTIVATION_REQUESTED]


@own
@pytest.mark.parametrize("state", ["on", "off", "creating*"])
def test_only_a_failed_app_is_tried_again(hub_a, state):
    given(hub_a, printing=state, created=["printing"])

    with pytest.raises(Conflict) as refused:
        run(hub_a, "base.app.retry", "printing")

    assert refused.value.code == "base.app_not_failed"


@own
def test_turning_on_a_failed_app_tries_it_again_too(hub_a):
    given(hub_a, printing="failed*")

    answer = run(hub_a, "base.app.enable", "printing")

    assert answer["state"] == "creating"
    assert rows_of(hub_a)["printing"] == (CREATING, True)


@pytest.mark.django_db
def test_a_hub_that_shares_phase_1s_database_turns_an_app_on_at_once():
    """Proposal (i) of round 2026-10-30: until S5 a hub without its own database keeps the immediate turn on."""
    Hub.objects.update_or_create(slug="c", defaults={"status": "ready", "db_name": ""})
    op = get("base.app.enable")
    ctx = OperationContext(scope=Scope("host", "c"), actor="ana", permissions=frozenset({"*"}), language="en")

    answer = op(ctx, op.input.model_validate({"app": "printing"})).model_dump(mode="json")

    assert answer["state"] == "on"
    assert AppActivation.objects.get(host="c", app="printing").state == ON


# ── What the Apps screen reads ──────────────────────────────────────────────────────────────────────────────────


@own
def test_the_apps_screen_tells_creating_and_failed_and_counts_them_as_chosen(hub_a):
    given(hub_a, printing="creating*", website="failed*", sale="on*", tax="on", customer="on", created=["sale", "tax", "customer"])
    op = get("base.app.list")
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        listed = op(as_admin(hub_a), op.input()).model_dump(mode="json")

    by_id = {app["id"]: app for app in listed["apps"]}
    assert (by_id["printing"]["state"], by_id["printing"]["chosen"], by_id["printing"]["path"]) == ("creating", True, None)
    assert (by_id["website"]["state"], by_id["website"]["chosen"], by_id["website"]["path"]) == ("failed", True, None)
    assert by_id["sale"]["state"] == "on"
    assert listed["enabled"] == 3


@own
def test_the_session_tells_an_app_being_created_activating_and_keeps_it_out_of_the_menu(hub_a):
    given(hub_a, printing="creating*", website="failed*", flow="on*", created=["flow"])
    op = get("base.session.me")
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        me = op(as_admin(hub_a), op.input()).model_dump(mode="json")

    states = {app["label"]: app["state"] for app in me["apps"]}
    assert (states["printing"], states["website"], states["flow"]) == ("activating", "off", "on")
    assert {"printing", "website"}.isdisjoint(entry["id"] for entry in me["menu"])


# ── Over HTTP: 202 while its tables are made ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("state", "status"), [("creating", 202), ("on", 200)])
def test_the_route_answers_202_while_its_tables_are_made_and_200_once_on(client, state, status, monkeypatch):
    import json

    from django.contrib.auth import get_user_model

    from base import services
    from base.models import Membership
    from base.schemas import AppChangeIn, AppChangeOut

    class Answering:
        input = AppChangeIn

        def __call__(self, ctx, data):
            return AppChangeOut(app=data.app, state=state, chosen=True, along=[])

    monkeypatch.setattr(services, "app_enable", Answering())
    user = get_user_model().objects.create(username="ana")
    Membership.objects.create(user=user, host="a", role=Membership.Role.OWNER)
    client.force_login(user)

    answered = client.post(
        "/api/apps/enable", json.dumps({"app": "printing"}), content_type="application/json", HTTP_HOST="a.localhost:8000"
    )

    assert (answered.status_code, answered.json()) == (
        status,
        {"app": "printing", "state": state, "chosen": True, "along": []},
    )


def test_the_retry_route_is_bound_to_its_command(db):
    from django.urls import resolve

    from base.api import router

    [route] = router.path_operations["/apps/retry"].operations
    assert (route.methods, route.operation_id) == (["POST"], "base.app.retry")
    assert resolve("/api/apps/retry").url_name


@own
def test_an_app_being_created_or_failed_is_out_of_the_relay_and_the_tasks_until_it_is_on(hub_a):
    from base import relay

    given(hub_a, printing="creating*", website="failed*", flow="on*", created=["flow"])
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        active = relay.active_apps(Scope("host", hub_a.slug))

    assert "flow" in active
    assert not {"printing", "website"} & active
