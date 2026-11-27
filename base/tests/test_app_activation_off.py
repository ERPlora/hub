"""What an app that is off stops being (its operations, the relay, the home, the assistant, the menu and the API keys),
the Apps screen that lists every app with its state and follows each change live, and the SaaS's photo while an app
is off.
"""

import pytest
from django.apps import apps
from live.context import OperationContext
from live.errors import AppInactive, PermissionDenied
from live.live_registry import live_registry
from live.operations import get

from base import activation, apps_on, events
from base.entitlement import EntitlementBlocked
from base.models import Hub
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.business import HUB_DB, A, B, in_business_a
from base.tests.test_app_activation import app_list, by_id, ctx, disable, enable, keep, set_rows, with_limit

#: Business A entered for every test with the database.
__all__ = ["in_business_a"]


# ── What an app that is off stops being ────────────────────────────────────────────────────────────────────


@HUB_DB
def test_an_operation_of_an_app_off_answers_404_app_inactive(hub_b):
    set_rows(task="on*", staff="on")
    disable("task")

    task_list = get("task.task.list")
    with pytest.raises(AppInactive) as refused:
        task_list(ctx(), task_list.input())

    assert (refused.value.status, refused.value.code) == (404, "app_inactive")
    assert refused.value.message == "Tasks is turned off in this business."
    # The same operation runs in another business, and base's never stop.
    with use_hub(hub_b):
        assert task_list(ctx(scope=B), task_list.input()).model_dump()["rows"] == []
    assert get("base.app.list")(ctx(), get("base.app.list").input()).apps


@HUB_DB
def test_the_404_is_said_in_the_language_of_who_asks():
    set_rows(staff="on*")
    task_list = get("task.task.list")
    with pytest.raises(AppInactive) as refused:
        task_list(ctx(language="es"), task_list.input())
    assert refused.value.message == "Tareas está desactivada en este negocio."


@HUB_DB
def test_a_paid_app_without_its_right_is_402_before_it_is_off(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep(A.key, {"modules": []})
    set_rows(staff="on*")
    task_list = get("task.task.list")
    with pytest.raises(EntitlementBlocked):
        task_list(ctx(), task_list.input())


@HUB_DB
def test_the_relay_the_home_and_the_assistant_leave_out_an_app_off(django_capture_on_commit_callbacks, hub_b):
    from base import assistant

    set_rows(task="on*", staff="on")
    assert "task" in apps_on.active_apps(A)
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):  # its COMMIT forgets the cache
        disable("task")
    assert "task" not in apps_on.active_apps(A) and "staff" not in apps_on.active_apps(A)
    assert "base" in apps_on.active_apps(A)
    with use_hub(hub_b):
        assert "task" in apps_on.active_apps(B)
    assert "task" not in assistant.tools.active_apps(A)
    assert not any(op.app_label == "task" for op in assistant.tools.catalog(ctx()).values())


@HUB_DB
def test_the_menu_and_the_session_leave_out_an_app_off(django_capture_on_commit_callbacks, hub_b):
    set_rows(task="on*", staff="on", customer="on*")
    me = get("base.session.me")
    before = me(ctx(), me.input()).model_dump(mode="json")
    assert {"task", "staff", "customer"} <= {group["id"] for group in before["menu"]}

    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):  # its COMMIT forgets the cache
        disable("task")

    after = me(ctx(), me.input()).model_dump(mode="json")
    assert {group["id"] for group in after["menu"]} & {"task", "staff"} == set()
    assert "customer" in {group["id"] for group in after["menu"]}
    states = {app["label"]: app["state"] for app in after["apps"]}
    assert (states["task"], states["staff"], states["customer"]) == ("off", "off", "on")
    # Another business keeps its menu.
    with use_hub(hub_b):
        assert "task" in {group["id"] for group in me(ctx(scope=B), me.input()).model_dump()["menu"]}


@HUB_DB
def test_an_api_key_cannot_be_given_an_app_off(django_capture_on_commit_callbacks):
    from base import queries

    set_rows(task="on*", staff="on", customer="on*")
    assert "task" in {app["id"] for app in queries.api_keys.api_apps(ctx())}
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):  # its COMMIT forgets the cache
        disable("task")
    assert "task" not in {app["id"] for app in queries.api_keys.api_apps(ctx())}


# ── The Apps screen ─────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_the_list_says_each_apps_state_whether_chosen_and_which_apps_on_need_it():
    with_limit(A.key, 20)
    set_rows(invoice="on*", sale="on", tax="on", customer="on", task="off")

    document = app_list()
    apps_ = by_id(document)

    assert (apps_["invoice"]["state"], apps_["invoice"]["chosen"], apps_["invoice"]["required_by"]) == ("on", True, [])
    assert (apps_["sale"]["state"], apps_["sale"]["chosen"], apps_["sale"]["required_by"]) == ("on", False, ["invoice"])
    assert apps_["tax"]["required_by"] == ["invoice", "sale"]
    assert (apps_["task"]["state"], apps_["task"]["chosen"], apps_["task"]["path"]) == ("off", False, None)
    assert apps_["task"]["required_by"] == []  # nothing on needs it
    assert (document["max_apps"], document["enabled"]) == (20, 1)
    hub = Hub.objects.get(slug=A.key)
    assert document["plan_url"] == f"http://localhost:8001/dashboard/store/plans?business={hub.id}"


@HUB_DB
def test_an_app_off_is_still_listed_with_its_icon_and_name():
    set_rows()
    document = by_id(app_list())
    assert set(document) == set(activation.module_graph())
    assert all(app["state"] == "off" and app["icon"] and app["name"] for app in document.values())


@HUB_DB
@pytest.mark.parametrize("state", ["on*", "off"])
def test_a_paid_app_without_its_right_gives_no_reason_of_its_own_on_or_off(monkeypatch, state):
    """What it lacks is the right: «blocked» sends the person to erplora.com, and no reason of the app's competes."""
    config = apps.get_app_config("task")
    monkeypatch.setattr(config, "premium", True)
    monkeypatch.setattr(config, "can_enable", lambda ctx: "Only in Spain.", raising=False)
    monkeypatch.setattr(config, "can_disable", lambda ctx: "Tasks are open.", raising=False)
    set_rows(task=state, staff="on")

    row = by_id(app_list())["task"]
    assert (row["state"], row["refusal"]) == ("blocked", None)


@HUB_DB
def test_a_paid_app_without_its_right_is_blocked_on_or_off(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep(A.key, {"modules": []})
    set_rows(staff="on*")
    assert by_id(app_list())["task"]["state"] == "blocked"


@HUB_DB
def test_an_app_born_on_is_listed_on_and_takes_nothing_of_the_plans_limit():
    """hub#1286: Taxes, born on (hub#997), is on in «My apps» (the screen's counter counts it as turned on) but not
    chosen, so the plan's part of the counter, ``enabled``, leaves it out; the app the business chose counts."""
    with_limit(A.key, 20)
    born = activation.born(activation.born_on("ES"), activation.module_graph())
    set_rows(**{label: "on*" if row.chosen else "on" for label, row in born.items() if row.on}, task="on*")

    document = app_list()
    apps_ = by_id(document)

    assert (apps_["tax"]["state"], apps_["tax"]["chosen"]) == ("on", False)
    assert (apps_["task"]["state"], apps_["task"]["chosen"]) == ("on", True)
    assert (document["max_apps"], document["enabled"]) == (20, 1)


@HUB_DB
def test_the_counter_counts_only_the_apps_this_business_shows(settings):
    """An app out of the store (the reference app) is no app of a customer's hub: it never counts against its limit.
    This business has every app on: of its 17 roots, that one is not shown."""
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


@HUB_DB
def test_the_live_list_runs_with_its_permission_only():
    with pytest.raises(PermissionDenied):
        get("base.app.list")(OperationContext(scope=A, actor="eva", permissions=frozenset(), language="en"), get("base.app.list").input())


# ── The SaaS's photo while an app is off ────────────────────────────────────────────────────────────────


@pytest.fixture
def registered_a(hub_a, settings):
    """Business A, as the SaaS registered it."""
    settings.INTERNAL_SHARED_SECRET = "local-internal-shared-secret"
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    hub, _ = Hub.objects.update_or_create(slug=A.key, defaults={"status": "ready", "state": {}, "state_version": 0})
    return hub


def put_photo(client, hub, version, **blocks):
    from base.tests.test_internal import signed

    body = {"hub_id": str(hub.id), "slug": hub.slug, "version": version, **blocks}
    return signed(client, "put", f"/internal/hubs/{hub.id}/state", body)


@HUB_DB
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


@HUB_DB
def test_a_photo_applies_while_whatsapp_is_off_and_its_block_waits_until_it_is_on(client, registered_a):
    from apps.whatsapp_inbox.models.channel import Channel
    from base.tests.test_internal_whatsapp import channel_state

    set_rows(staff="on*")

    answer = put_photo(client, registered_a, 7, whatsapp=channel_state(1))

    assert (answer.status_code, answer.json()) == (200, {"applied": True, "version": 7})
    assert not Channel.objects.filter(version=7).exists()

    enable("whatsapp_inbox")

    assert Channel.objects.get().version == 7


@HUB_DB
def test_a_whatsapp_block_out_of_contract_while_it_is_off_never_stops_turning_it_on(client, registered_a, caplog):
    """Off, the photo's WhatsApp block is not read (as before the activation): the photo applies. Turned on, a block
    the sync refuses is logged and waits for the next photo; the app turns on all the same."""
    from apps.whatsapp_inbox.models.channel import Channel

    set_rows(staff="on*")

    answer = put_photo(client, registered_a, 8, whatsapp={"status": 42})

    assert (answer.status_code, answer.json()) == (200, {"applied": True, "version": 8})

    assert enable("whatsapp_inbox")["state"] == "on"
    assert not Channel.objects.filter(version=8).exists()
    assert "base.app.photo_block_refused" in caplog.text
