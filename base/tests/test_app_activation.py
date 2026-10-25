"""Turning a business's apps on and off, with the plan's limit (PLAN-HUB §9; BASE-F18, F19, F23–F25; FIX-BASE-APP-TURN-
OFF-VETO): ``base.app.enable`` and ``base.app.disable``, their rows (``base.AppActivation``), what an app that is off
stops being (its operations, the menu, the relay) and how the Apps screen follows them live.

The rules themselves, without the database, are ``base/tests/test_activation.py``.
"""

import json
import threading

import psycopg
import pytest
from django.apps import apps
from django.db import IntegrityError, connections, transaction
from live.context import OperationContext, Scope
from live.errors import AppInactive, Conflict, NotFound, OperationError, PermissionDenied
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base import activation, events, relay
from base.activation import OFF, ON, Activation
from base.entitlement import EntitlementBlocked
from base.models import AppActivation, Hub
from base.schemas import AppChangeIn, AppChangeOut
from base.tenancy import inventory

A = Scope("host", "a")
B = Scope("host", "b")
ADMIN = "base.administer_hub"
HOME = "base.view_home"


def ctx(*permissions, scope=A, language="en"):
    return OperationContext(
        scope=scope, actor="ana", permissions=frozenset(permissions or ("*",)), language=language
    )


def run(name, app, *, context=None):
    op = get(name)
    return op(context or ctx(), op.input.model_validate({"app": app})).model_dump(mode="json")


def enable(app, **kwargs):
    return run("base.app.enable", app, **kwargs)


def disable(app, **kwargs):
    return run("base.app.disable", app, **kwargs)


def keep(slug, state):
    """The SaaS's last photo of ``slug``."""
    Hub.objects.update_or_create(slug=slug, defaults={"status": "ready", "state": state, "state_version": 1})


def with_limit(slug, max_apps):
    keep(slug, {"plan": {"slug": "free", "max_users": 0, "max_devices": 0, "max_apps": max_apps}})


def rows(host="a"):
    return {
        row.app: Activation(row.state, row.chosen) for row in AppActivation.objects.filter(host=host).order_by("app")
    }


def set_rows(host="a", **given):
    """Write ``host``'s rows: every module off, those given ``on``/``on*`` (chosen)/``off``."""
    AppActivation.objects.filter(host=host).delete()
    graph = activation.module_graph()
    AppActivation.objects.bulk_create(
        AppActivation(
            host=host,
            app=label,
            state=ON if given.get(label, "off").startswith("on") else OFF,
            chosen=given.get(label, "").endswith("*"),
        )
        for label in graph
    )


def recorded(name):
    return list(OutboxEvent.objects.filter(name=name).values_list("scope_key", "payload"))


def app_list(scope=A, language="en", *permissions):
    context = OperationContext(
        scope=scope, actor="ana", permissions=frozenset({HOME, *permissions}), language=language
    )
    return get("base.app.list")(context, get("base.app.list").input()).model_dump(mode="json")


def by_id(document):
    return {app["id"]: app for app in document["apps"]}


# ── The rows ────────────────────────────────────────────────────────────────────────────────────────────────


def test_an_activation_lives_in_the_hubs_database():
    assert inventory.classify(AppActivation) == inventory.HUB


@pytest.mark.django_db
def test_a_hub_has_one_row_per_app():
    AppActivation.objects.create(host="a", app="task", state=ON, chosen=True)
    AppActivation.objects.create(host="b", app="task", state=OFF, chosen=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        AppActivation.objects.create(host="a", app="task", state=OFF, chosen=False)


@pytest.mark.django_db
def test_a_state_is_on_or_off():
    with pytest.raises(IntegrityError), transaction.atomic():
        AppActivation.objects.create(host="a", app="task", state="activating", chosen=False)


@pytest.mark.django_db
def test_a_business_that_never_changed_anything_has_every_app_on_and_writes_nothing():
    """The existing hubs (and every new one in phase 1): every app on, the roots chosen (PLAN §32, point 2)."""
    document = app_list()
    graph = activation.module_graph()
    roots = activation.roots(graph, graph)
    assert {app["id"]: (app["state"], app["chosen"]) for app in document["apps"]} == {
        label: ("on", label in roots) for label in graph
    }
    assert (document["max_apps"], document["enabled"]) == (None, 17)
    assert not AppActivation.objects.exists()


def test_the_hubs_admin_shows_the_rows_and_changes_none(rf):
    """The Hub's admin (hubs.erplora.com/admin) shows each business's apps as they are; turning one on or off is
    base.app.enable/disable's (their requires, the plan's limit, the event), never a row edited by hand."""
    from django.contrib import admin

    from base.admin import AppActivationAdmin

    model_admin = admin.site._registry[AppActivation]
    assert isinstance(model_admin, AppActivationAdmin)
    request = rf.get("/admin/")
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
    assert model_admin.list_display == ("host", "app", "state", "chosen", "changed_at")


def test_the_states_are_named_in_spanish_as_the_screen_names_them():
    from django.utils import translation

    with translation.override("es"):
        assert [str(label) for _, label in AppActivation.State.choices] == ["Activada", "Desactivada"]


# ── Turning one on ──────────────────────────────────────────────────────────────────────────────────────────


def test_the_commands_are_for_who_runs_the_business_and_told_to_the_assistant():
    for name in ("base.app.enable", "base.app.disable"):
        op = get(name)
        assert (op.kind, op.permission, op.input, op.output) == ("command", ADMIN, AppChangeIn, AppChangeOut)
        assert op.ai["description"].strip()
    assert get("base.app.enable").ai["risk"] == "normal"
    assert get("base.app.disable").ai["risk"] == "high"


@pytest.mark.django_db
def test_turning_one_on_turns_on_what_it_needs_and_records_its_event():
    set_rows(task="on*", staff="on")

    answer = enable("invoice")

    assert answer == {
        "app": "invoice",
        "state": "on",
        "chosen": True,
        "along": [{"id": "customer", "name": "Customers"}, {"id": "sale", "name": "Sales & POS"}, {"id": "tax", "name": "Taxes"}],
    }
    now = rows()
    assert now["invoice"] == Activation(ON, True)
    assert {label: now[label] for label in ("sale", "tax", "customer")} == dict.fromkeys(
        ("sale", "tax", "customer"), Activation(ON, False)
    )
    assert now["task"] == Activation(ON, True) and now["staff"] == Activation(ON, False)
    assert recorded(events.APP_ENABLED) == [("a", {"app": "invoice", "along": ["customer", "sale", "tax"]})]


@pytest.mark.django_db
def test_what_it_needs_and_was_chosen_stays_chosen():
    set_rows(customer="on*")
    enable("sale")
    assert rows()["customer"] == Activation(ON, True)
    assert rows()["tax"] == Activation(ON, False)


@pytest.mark.django_db
def test_one_already_on_and_chosen_changes_nothing_and_records_nothing():
    set_rows(task="on*", staff="on")
    assert enable("task") == {"app": "task", "state": "on", "chosen": True, "along": []}
    assert recorded(events.APP_ENABLED) == []


@pytest.mark.django_db
def test_the_first_change_writes_down_every_app_of_the_business():
    """A business on the baseline gets its rows the first time it changes something: every app as it was, and the
    change. Another business keeps its own baseline."""
    disable("task")

    graph = activation.module_graph()
    roots = activation.roots(graph, graph)
    expected = {label: Activation(ON, label in roots) for label in graph}
    expected["task"] = Activation(OFF, False)
    assert rows("a") == expected
    assert rows("b") == {}
    assert by_id(app_list(B))["task"]["state"] == "on"


@pytest.mark.django_db
def test_an_unknown_app_or_the_platform_is_not_found():
    for label in ("nope", "base", "live"):
        with pytest.raises(NotFound):
            enable(label)
        with pytest.raises(NotFound):
            disable(label)
    assert not AppActivation.objects.exists()


@pytest.mark.django_db
def test_a_paid_app_without_its_right_cannot_be_turned_on(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep("a", {"modules": []})
    set_rows(staff="on*")

    with pytest.raises(EntitlementBlocked) as refused:
        enable("task")

    assert (refused.value.status, refused.value.code) == (402, "app_entitlement_blocked")
    assert rows()["task"] == Activation(OFF, False)


@pytest.mark.django_db
def test_only_who_runs_the_business_turns_apps_on_or_off():
    for name in ("base.app.enable", "base.app.disable"):
        with pytest.raises(PermissionDenied):
            run(name, "task", context=ctx(HOME))


# ── The plan's limit (PLAN §32, points 2 and 3) ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_at_the_limit_one_more_is_refused_with_402_and_what_counts():
    with_limit("a", 2)
    set_rows(task="on*", staff="on", website="on*")

    with pytest.raises(OperationError) as refused:
        enable("flow")

    assert (refused.value.status, refused.value.code) == (402, "base.app_limit_reached")
    assert refused.value.envelope()["error"] | {"message": ""} == {
        "code": "base.app_limit_reached",
        "message": "",
        "max_apps": 2,
        "enabled": 2,
    }
    assert refused.value.message == (
        "You have reached the 2-app limit of your plan. Upgrade your plan or turn one off."
    )
    assert rows()["flow"] == Activation(OFF, False)
    assert recorded(events.APP_ENABLED) == []


@pytest.mark.django_db
def test_the_limit_is_said_in_the_language_of_who_asks():
    with_limit("a", 2)
    set_rows(task="on*", website="on*")
    with pytest.raises(OperationError) as refused:
        enable("flow", context=ctx(language="es"))
    assert refused.value.message == "Has llegado al límite de 2 apps de tu plan. Mejora el plan o apaga una."


@pytest.mark.django_db
def test_what_comes_along_does_not_count():
    with_limit("a", 2)
    set_rows(invoice="on*", sale="on", tax="on", customer="on")

    enable("task")  # 1 chosen (invoice) + task = 2: staff comes along, uncounted

    assert app_list()["enabled"] == 2
    assert rows()["staff"] == Activation(ON, False)


@pytest.mark.django_db
def test_choosing_one_that_came_along_counts():
    with_limit("a", 1)
    set_rows(invoice="on*", sale="on", tax="on", customer="on")
    with pytest.raises(OperationError) as refused:
        enable("sale")
    assert refused.value.code == "base.app_limit_reached"
    assert rows()["sale"] == Activation(ON, False)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "photo",
    [
        {"plan": {"slug": "pro", "max_users": 0, "max_devices": 0, "max_apps": 0}},  # 0 = no limit
        {"plan": {"slug": "free", "max_users": 0, "max_devices": 0}},  # a photo without the field
        {},
    ],
)
def test_no_limit_without_a_positive_max_apps(photo):
    keep("a", photo)
    set_rows(task="on*", staff="on", website="on*", flow="on*")
    enable("cart_checkout")
    assert app_list()["max_apps"] is None and app_list()["enabled"] == 4


@pytest.mark.django_db
def test_a_lower_plan_turns_nothing_off_and_only_refuses_one_more():
    with_limit("a", 20)
    graph = activation.module_graph()
    before = by_id(app_list())

    with_limit("a", 5)  # bought down: 17 chosen, 5 allowed

    after = by_id(app_list())
    assert {label: (app["state"], app["chosen"]) for label, app in after.items()} == {
        label: (app["state"], app["chosen"]) for label, app in before.items()
    }
    assert app_list()["enabled"] == 17 and app_list()["max_apps"] == 5
    disable("task")
    with pytest.raises(OperationError) as refused:
        enable("task")
    assert refused.value.code == "base.app_limit_reached"
    assert refused.value.envelope()["error"]["enabled"] == 16
    assert len(graph) == len(after)


@pytest.mark.django_db
def test_the_limit_is_this_business_own():
    with_limit("a", 1)
    keep("b", {})
    set_rows("a", task="on*", staff="on")
    set_rows("b", task="on*", staff="on")
    enable("website", context=ctx(scope=B))
    with pytest.raises(OperationError):
        enable("website")


# ── Turning one off ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_turning_one_off_turns_off_what_came_with_it_and_records_its_event():
    set_rows(invoice="on*", sale="on", tax="on*", customer="on", task="on*", staff="on")

    answer = disable("invoice")

    assert answer == {
        "app": "invoice",
        "state": "off",
        "chosen": False,
        "along": [{"id": "customer", "name": "Customers"}, {"id": "sale", "name": "Sales & POS"}],
    }
    now = rows()
    assert [label for label, row in now.items() if row.on] == ["staff", "task", "tax"]
    assert recorded(events.APP_DISABLED) == [("a", {"app": "invoice", "along": ["customer", "sale"]})]


@pytest.mark.django_db
def test_one_another_app_on_needs_is_refused_with_409_naming_them():
    set_rows(verifactu="on*", invoice="on", sale="on", tax="on", customer="on", cash_register="on*")

    with pytest.raises(Conflict) as refused:
        disable("sale")

    error = refused.value.envelope()["error"]
    assert (refused.value.status, error["code"]) == (409, "base.app_required")
    assert error["required_by"] == ["cash_register", "invoice", "verifactu"]
    # The ones to turn off: the chosen ones (invoice goes off with VeriFactu).
    assert refused.value.message == "Turn off Cash register and VeriFactu first."
    assert rows()["sale"] == Activation(ON, False)
    assert recorded(events.APP_DISABLED) == []


@pytest.mark.django_db
def test_the_409_is_said_in_the_language_of_who_asks():
    set_rows(task="on*", staff="on")
    with pytest.raises(Conflict) as refused:
        disable("staff", context=ctx(language="es"))
    assert refused.value.message == "Apaga antes Tareas."


@pytest.mark.django_db
def test_one_already_off_changes_nothing_and_records_nothing():
    set_rows(task="on*", staff="on")
    assert disable("flow") == {"app": "flow", "state": "off", "chosen": False, "along": []}
    assert recorded(events.APP_DISABLED) == []


@pytest.mark.django_db
def test_an_app_may_veto_going_off_with_its_reason(monkeypatch):
    """FIX-BASE-APP-TURN-OFF-VETO: the hook an app declares on its config (VeriFactu will, in its own lane)."""
    seen = []

    def veto(ctx):
        seen.append(ctx.scope)
        return f"Close the open tasks of {ctx.scope.key} first."

    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", veto, raising=False)
    set_rows(task="on*", staff="on")

    with pytest.raises(Conflict) as refused:
        disable("task")

    error = refused.value.envelope()["error"]
    assert (refused.value.status, error["code"], error["app"]) == (409, "base.app_vetoed", "task")
    assert refused.value.message == "Close the open tasks of a first."
    assert seen == [A]
    assert rows()["task"] == Activation(ON, True)


@pytest.mark.django_db
def test_what_would_go_off_along_may_veto_too(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("staff"), "can_disable", lambda ctx: "Staff is busy.", raising=False)
    set_rows(task="on*", staff="on")
    with pytest.raises(Conflict) as refused:
        disable("task")
    assert refused.value.envelope()["error"]["app"] == "staff"
    assert rows()["task"] == Activation(ON, True)


@pytest.mark.django_db
def test_an_app_without_a_reason_lets_it_go(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: None, raising=False)
    set_rows(task="on*", staff="on")
    disable("task")
    assert rows()["task"] == Activation(OFF, False)


@pytest.mark.django_db
def test_turning_one_off_and_on_again_keeps_its_data():
    from apps.task.models import Project

    project = Project.objects.create(name="Spring menu")
    set_rows(task="on*", staff="on")
    disable("task")
    assert Project.objects.filter(pk=project.pk).exists()
    enable("task")
    assert Project.objects.get(pk=project.pk).name == "Spring menu"


# ── What an app that is off stops being ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_an_operation_of_an_app_off_answers_404_app_inactive():
    set_rows(task="on*", staff="on")
    disable("task")

    task_list = get("task.task.list")
    with pytest.raises(AppInactive) as refused:
        task_list(ctx(), task_list.input())

    assert (refused.value.status, refused.value.code) == (404, "app_inactive")
    assert refused.value.message == "Tasks is turned off in this business."
    # The same operation runs in another business, and base's never stop.
    assert task_list(ctx(scope=B), task_list.input()).model_dump()["rows"] == []
    assert get("base.app.list")(ctx(), get("base.app.list").input()).apps


@pytest.mark.django_db
def test_the_404_is_said_in_the_language_of_who_asks():
    set_rows(staff="on*")
    task_list = get("task.task.list")
    with pytest.raises(AppInactive) as refused:
        task_list(ctx(language="es"), task_list.input())
    assert refused.value.message == "Tareas está desactivada en este negocio."


@pytest.mark.django_db
def test_a_paid_app_without_its_right_is_402_before_it_is_off(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep("a", {"modules": []})
    set_rows(staff="on*")
    task_list = get("task.task.list")
    with pytest.raises(EntitlementBlocked):
        task_list(ctx(), task_list.input())


@pytest.mark.django_db
def test_the_relay_the_home_and_the_assistant_leave_out_an_app_off():
    from base import assistant

    set_rows(task="on*", staff="on")
    assert "task" in relay.active_apps(A)
    disable("task")
    assert "task" not in relay.active_apps(A) and "staff" not in relay.active_apps(A)
    assert "base" in relay.active_apps(A)
    assert "task" in relay.active_apps(B)
    assert "task" not in assistant.active_apps(A)
    assert not any(op.app_label == "task" for op in assistant.catalog(ctx()).values())


@pytest.mark.django_db
def test_the_menu_and_the_session_leave_out_an_app_off():
    set_rows(task="on*", staff="on", customer="on*")
    me = get("base.session.me")
    before = me(ctx(), me.input()).model_dump(mode="json")
    assert {"task", "staff", "customer"} <= {group["id"] for group in before["menu"]}

    disable("task")

    after = me(ctx(), me.input()).model_dump(mode="json")
    assert {group["id"] for group in after["menu"]} & {"task", "staff"} == set()
    assert "customer" in {group["id"] for group in after["menu"]}
    states = {app["label"]: app["state"] for app in after["apps"]}
    assert (states["task"], states["staff"], states["customer"]) == ("off", "off", "on")
    # Another business keeps its menu.
    assert "task" in {group["id"] for group in me(ctx(scope=B), me.input()).model_dump()["menu"]}


@pytest.mark.django_db
def test_an_api_key_cannot_be_given_an_app_off():
    from base import queries

    set_rows(task="on*", staff="on", customer="on*")
    assert "task" in {app["id"] for app in queries.api_apps(ctx())}
    disable("task")
    assert "task" not in {app["id"] for app in queries.api_apps(ctx())}


# ── The Apps screen ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_list_says_each_apps_state_whether_chosen_and_which_apps_on_need_it():
    with_limit("a", 20)
    set_rows(invoice="on*", sale="on", tax="on", customer="on", task="off")

    document = app_list()
    apps_ = by_id(document)

    assert (apps_["invoice"]["state"], apps_["invoice"]["chosen"], apps_["invoice"]["required_by"]) == ("on", True, [])
    assert (apps_["sale"]["state"], apps_["sale"]["chosen"], apps_["sale"]["required_by"]) == ("on", False, ["invoice"])
    assert apps_["tax"]["required_by"] == ["invoice", "sale"]
    assert (apps_["task"]["state"], apps_["task"]["chosen"], apps_["task"]["path"]) == ("off", False, None)
    assert apps_["task"]["required_by"] == []  # nothing on needs it
    assert (document["max_apps"], document["enabled"]) == (20, 1)
    hub = Hub.objects.get(slug="a")
    assert document["plan_url"] == f"http://localhost:8001/store/plans?business={hub.id}"


@pytest.mark.django_db
def test_an_app_off_is_still_listed_with_its_icon_and_name():
    set_rows()
    document = by_id(app_list())
    assert set(document) == set(activation.module_graph())
    assert all(app["state"] == "off" and app["icon"] and app["name"] for app in document.values())


@pytest.mark.django_db
def test_a_paid_app_without_its_right_is_blocked_on_or_off(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep("a", {"modules": []})
    set_rows(staff="on*")
    assert by_id(app_list())["task"]["state"] == "blocked"


@pytest.mark.django_db
def test_the_counter_counts_only_the_apps_this_business_shows(settings):
    """The reference app is no app of a customer's hub: it never counts against its limit."""
    settings.SHOW_UNLISTED_MODULES = False
    assert app_list()["enabled"] == 16


def test_the_list_the_menu_and_the_home_follow_every_change():
    affected = live_registry.affected([events.APP_ENABLED])
    assert affected == live_registry.affected([events.APP_DISABLED])
    assert {
        "base.app.list",
        "base.setup.status",
        "base.widget.list",
        "base.bell.counters",
        "base.notice.list",
        "base.failed_event.list",
        "base.api_key.list",
    } <= affected
    # The SaaS's photo changes the limit and the rights.
    assert "base.app.list" in live_registry.affected([events.HUB_STATE_APPLIED])
    # The menu is the session's (no live query: it needs no permission); the shell reads it again when the live Apps
    # list it follows changes (base/frontend/components/AppsFollower.vue).
    assert "base.session.me" not in affected


@pytest.mark.django_db
def test_the_live_list_runs_with_its_permission_only():
    with pytest.raises(PermissionDenied):
        get("base.app.list")(OperationContext(scope=A, actor="eva", permissions=frozenset(), language="en"), get("base.app.list").input())


# ── The SaaS's photo while an app is off ────────────────────────────────────────────────────────────────


@pytest.fixture
def registered_a(db, settings):
    """The suite's local hub ``a``, as the SaaS registered it."""
    settings.INTERNAL_SHARED_SECRET = "local-internal-shared-secret"
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    hub, _ = Hub.objects.update_or_create(slug="a", defaults={"status": "ready", "state": {}, "state_version": 0})
    return hub


def put_photo(client, hub, version, **blocks):
    from base.tests.test_internal import signed

    body = {"hub_id": str(hub.id), "slug": "a", "version": version, **blocks}
    return signed(client, "put", f"/internal/hubs/{hub.id}/state", body)


def test_a_photo_applies_while_verifactu_is_off_and_its_block_waits_until_it_is_on(client, registered_a):
    from apps.verifactu.models import Config

    approved = {"status": "approved", "updated_at": "2026-10-15T10:00:00Z", "reason": ""}
    set_rows(staff="on*")

    answer = put_photo(client, registered_a, 3, status="active", verifactu={"representation": approved})

    assert (answer.status_code, answer.json()) == (200, {"applied": True, "version": 3})
    assert not Config.objects.filter(synced_version=3).exists()

    enable("verifactu")

    config = Config.objects.get()
    assert (config.hub_status, config.representation_status, config.synced_version) == ("active", "approved", 3)


def test_a_photo_applies_while_whatsapp_is_off_and_its_block_waits_until_it_is_on(client, registered_a):
    from apps.whatsapp_inbox.models import Channel
    from base.tests.test_internal_whatsapp import channel_state

    set_rows(staff="on*")

    answer = put_photo(client, registered_a, 7, whatsapp=channel_state(1))

    assert (answer.status_code, answer.json()) == (200, {"applied": True, "version": 7})
    assert not Channel.objects.filter(version=7).exists()

    enable("whatsapp_inbox")

    assert Channel.objects.get().version == 7


def test_a_whatsapp_block_out_of_contract_while_it_is_off_never_stops_turning_it_on(client, registered_a, caplog):
    """Off, the photo's WhatsApp block is not read (as before the activation): the photo applies. Turned on, a block
    the sync refuses is logged and waits for the next photo; the app turns on all the same."""
    from apps.whatsapp_inbox.models import Channel

    set_rows(staff="on*")

    answer = put_photo(client, registered_a, 8, whatsapp={"status": 42})

    assert (answer.status_code, answer.json()) == (200, {"applied": True, "version": 8})

    assert enable("whatsapp_inbox")["state"] == "on"
    assert not Channel.objects.filter(version=8).exists()
    assert "base.app.photo_block_refused" in caplog.text


# ── Over HTTP ───────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("path", "operation"), [("/apps/enable", "base.app.enable"), ("/apps/disable", "base.app.disable")])
def test_the_routes_are_bound_to_their_commands(path, operation, db):
    from django.urls import resolve

    from base.api import router

    [route] = router.path_operations[path].operations
    assert (route.methods, route.operation_id) == (["POST"], operation)
    assert resolve(f"/api{path}").url_name


@pytest.mark.django_db
def test_an_owner_turns_one_off_over_http_and_a_cashier_is_refused(client, make_user):
    body = json.dumps({"app": "task"})
    client.force_login(make_user("eva", host="a", role="hub_employee"))
    refused = client.post("/api/apps/disable", body, content_type="application/json", HTTP_HOST="a.localhost:8000")
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")

    client.force_login(make_user("ana", host="a", role="hub_owner"))
    answered = client.post("/api/apps/disable", body, content_type="application/json", HTTP_HOST="a.localhost:8000")
    assert (answered.status_code, answered.json()["state"]) == (200, "off")
    gone = client.get("/api/task/tasks", HTTP_HOST="a.localhost:8000")
    assert (gone.status_code, gone.json()["error"]["code"]) == (404, "app_inactive")

    with_limit("a", 1)
    over = client.post("/api/apps/enable", body, content_type="application/json", HTTP_HOST="a.localhost:8000")
    assert over.status_code == 402
    assert {key: over.json()["error"][key] for key in ("code", "max_apps", "enabled")} == {
        "code": "base.app_limit_reached",
        "max_apps": 1,
        "enabled": 16,
    }


# ── After the COMMIT, to its own business only ──────────────────────────────────────────────────────────────


def dsn() -> str:
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )


@pytest.fixture
def listen():
    sessions = []

    def open_session(scope):
        session = psycopg.connect(dsn(), autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout=0.5):
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_turning_one_off_in_b_is_told_to_b_and_never_to_a(transactional_db, listen):
    on_a, on_b = listen(A), listen(B)

    disable("task", context=ctx(scope=B))
    enable("task", context=ctx(scope=B))

    assert heard(on_b) == {events.APP_DISABLED, events.APP_ENABLED}
    assert heard(on_a, timeout=0.2) == set()


def test_two_at_the_limit_at_once_turn_on_only_one(transactional_db):
    """The rows of the business are locked while one turns an app on: two people at once cannot both pass the
    limit."""
    with_limit("a", 2)
    set_rows(task="on*", staff="on")
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def turn_on(label):
        try:
            barrier.wait()
            enable(label)
            outcomes.append("on")
        except OperationError as error:
            outcomes.append(error.code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=turn_on, args=(label,)) for label in ("website", "flow")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["base.app_limit_reached", "on"]
    assert app_list()["enabled"] == 2


def test_a_change_waits_while_another_holds_the_business_rows(transactional_db):
    """What makes the limit hold with two people at once: a change locks every row of its business, the ones it does
    not touch too (a row held elsewhere, Tasks, holds a change of Website)."""
    with_limit("a", 20)
    set_rows(task="on*", staff="on")
    holder = psycopg.connect(dsn())
    holder.execute("SELECT id FROM base_appactivation WHERE host = 'a' AND app = 'task' FOR UPDATE")
    done = threading.Event()
    failures: list[BaseException] = []

    def turn_on():
        try:
            enable("website")
        except BaseException as error:  # noqa: BLE001 - the test reports any of them
            failures.append(error)
        finally:
            connections.close_all()
            done.set()

    thread = threading.Thread(target=turn_on)
    thread.start()
    try:
        assert not done.wait(0.7), "the change did not wait for the business's rows"
    finally:
        holder.rollback()
        holder.close()
    assert done.wait(10) and failures == []
    thread.join()
    assert rows()["website"] == Activation(ON, True)


def test_two_first_changes_at_once_write_the_business_down_once(transactional_db):
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def turn_off(label):
        try:
            barrier.wait()
            disable(label)
        except BaseException as error:  # noqa: BLE001 - the test reports any of them
            failures.append(error)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=turn_off, args=(label,)) for label in ("website", "flow")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    now = rows()
    assert len(now) == len(activation.module_graph())
    assert now["website"] == Activation(OFF, False) and now["flow"] == Activation(OFF, False)
