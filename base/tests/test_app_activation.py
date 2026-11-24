"""Turning a business's apps on and off, with the plan's limit (BASE-F18, F19, F23–F25): ``base.app.enable``,
``base.app.disable`` and ``base.app.get``, their rows (``base.AppActivation``), how a hub is born, what the business
must keep on in its country, and their routes.

What an app refuses beforehand is ``test_app_activation_refusals.py``; what an app that is off stops being, the Apps
screen and the SaaS's photo, ``test_app_activation_off.py``; what a change does at its COMMIT,
``test_app_activation_commit.py``. The rules themselves, without the database, are ``base/tests/test_activation.py``.
"""

import json
import re

import pytest
from django.apps import apps
from django.db import IntegrityError
from live.assistant import description, risk
from live.context import OperationContext, Scope
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.models import OutboxEvent
from live.operations import atomic, get

from base import activation, apps_on, events
from base.activation import OFF, ON, Activation
from base.entitlement import EntitlementBlocked
from base.models.activation import AppActivation
from base.models import Hub
from base.schemas.apps import AppChangeIn, AppChangeOut
from base.tenancy import inventory
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, HUB_DB, A, B, in_business_a
from base.tests.routes import assert_bound

#: Business A entered for every test with the database.
__all__ = ["in_business_a"]

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


def rows(host=A.key):
    return {
        row.app: Activation(row.state, row.chosen) for row in AppActivation.objects.filter(host=host).order_by("app")
    }


def set_rows(host=A.key, **given):
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


def born_off(host=A.key):
    """The business as it is born, every app off: no row of its own (one of before has every app on)."""
    AppActivation.objects.filter(host=host).delete()


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


@HUB_DB
def test_a_hub_has_one_row_per_app():
    AppActivation.objects.create(host="c", app="task", state=ON, chosen=True)
    AppActivation.objects.create(host="d", app="task", state=OFF, chosen=False)
    with pytest.raises(IntegrityError), atomic():
        AppActivation.objects.create(host="c", app="task", state=OFF, chosen=False)


@HUB_DB
def test_a_state_is_on_or_off():
    with pytest.raises(IntegrityError), atomic():  # a host without rows: only the state's check can refuse it
        AppActivation.objects.create(host="c", app="task", state="activating", chosen=False)


@HUB_DB
def test_a_business_that_never_changed_anything_has_every_app_off_and_writes_nothing():
    born_off()
    document = app_list()
    assert {app["id"]: (app["state"], app["chosen"]) for app in document["apps"]} == {
        label: ("off", False) for label in activation.module_graph()
    }
    assert (document["max_apps"], document["enabled"]) == (None, 0)
    assert apps_on.active_apps(A).isdisjoint(activation.module_graph())
    assert rows() == {}


@HUB_DB
def test_a_hub_of_before_keeps_every_app_on_and_its_roots_chosen():
    """What the migration base.0017 wrote for hubs created before new hubs started with every app off (as the suite's
    A): every app on, the roots chosen."""
    document = app_list()
    graph = activation.module_graph()
    roots = activation.roots(graph, graph)
    assert {app["id"]: (app["state"], app["chosen"]) for app in document["apps"]} == {
        label: ("on", label in roots) for label in graph
    }
    assert (document["max_apps"], document["enabled"]) == (None, 17)


@HUB_DB
def test_erploras_own_hub_has_every_app_on_and_the_worker_scope_is_not_the_platform(settings):
    """ERPlora's own hub issues its invoices with Invoicing and VeriFactu; the worker's legacy scope is not it."""
    settings.PLATFORM_HUB_SLUG, settings.WORKER_SCOPE_SLUG = "erplora", "worker-scope"
    graph = activation.module_graph()
    scope = Scope("host", "erplora")
    assert activation.off_apps(scope) == frozenset()
    assert activation.states_of(scope) == activation.every_on(graph)
    assert {"invoice", "verifactu", "whatsapp_inbox"} <= apps_on.active_apps(scope)
    assert activation.off_apps(Scope("host", "worker-scope")) == frozenset(graph)
    assert activation.off_apps(Scope("host", "c")) == frozenset(graph)


# ── How a hub is born ─────────────────────────────────────────────────────────────────────────────────────────


def modules_on(scope):
    return set(apps_on.active_apps(scope)) & set(activation.module_graph())


@HUB_DB
def test_a_business_the_saas_registers_is_born_with_every_app_off():
    from live.context import system_context

    from base import registry
    from base.schemas.hub_registry import HubRegistryIn

    get("base.hub.register")(
        system_context(registry.REGISTRY_SCOPE),
        HubRegistryIn(id="0199c4b0-0000-7000-8000-0000000000c1", slug="nuevo", name="Nuevo", country="ES",
                      timezone="Europe/Madrid", language="es", vertical="restaurant"),
    )

    # Requested, with its own database still to make: its template carries no app turned on
    # (base/tenancy/tests/test_provision.py), and nothing turns one on before it is ready.
    assert Hub.objects.get(slug="nuevo").status == "requested"
    assert modules_on(Scope("host", "nuevo")) == set()
    assert rows("nuevo") == {}


@HUB_DB
def test_a_demo_is_born_with_every_app_off():
    import hashlib

    from live.context import system_context

    from base import registry
    from base.schemas.demos import DemoCreateIn

    demo = get("base.demo.create")(
        system_context(registry.REGISTRY_SCOPE),
        DemoCreateIn(session_key=hashlib.sha256(b"a browser").hexdigest(), vertical="restaurant", language="es"),
    )

    assert modules_on(Scope("host", demo.slug)) == set()
    assert rows(demo.slug) == {}



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
        assert [str(label) for _, label in AppActivation.State.choices] == ["Activada", "Desactivada", "Activándose", "No se ha podido activar"]


# ── Turning one on ──────────────────────────────────────────────────────────────────────────────────────────


def test_the_assistants_card_names_the_apps_screen():
    from base import assistant

    for name in ("base.app.enable", "base.app.disable"):
        assert assistant.cards.card(get(name), {"app": "task"}, "es")["app_name"] == "Apps"
        assert assistant.cards.card(get(name), {"app": "task"}, "en")["app_name"] == "Apps"


def test_the_commands_are_for_who_runs_the_business_and_told_to_the_assistant():
    for name in ("base.app.enable", "base.app.disable"):
        op = get(name)
        assert (op.kind, op.permission, op.input, op.output) == ("command", ADMIN, AppChangeIn, AppChangeOut)
        assert description(op)
    assert risk(get("base.app.enable")) == "normal"
    assert risk(get("base.app.disable")) == "high"


@HUB_DB
def test_turning_one_on_turns_on_what_it_needs_and_records_its_event():
    set_rows(task="on*", staff="on")

    answer = enable("invoice")

    assert answer == {
        "app": "invoice",
        "state": "on",
        "chosen": True,
        "along": [{"id": "customer", "name": "Customers"}, {"id": "sale", "name": "Sales & POS"}, {"id": "tax", "name": "Taxes"}],
        "already": False,
    }
    now = rows()
    assert now["invoice"] == Activation(ON, True)
    assert {label: now[label] for label in ("sale", "tax", "customer")} == dict.fromkeys(
        ("sale", "tax", "customer"), Activation(ON, False)
    )
    assert now["task"] == Activation(ON, True) and now["staff"] == Activation(ON, False)
    assert recorded(events.APP_ENABLED) == [(A.key, {"app": "invoice", "along": ["customer", "sale", "tax"]})]


@HUB_DB
def test_what_it_needs_and_was_chosen_stays_chosen():
    set_rows(customer="on*")
    enable("sale")
    assert rows()["customer"] == Activation(ON, True)
    assert rows()["tax"] == Activation(ON, False)


@HUB_DB
def test_one_already_on_and_chosen_changes_nothing_and_records_nothing():
    set_rows(task="on*", staff="on")
    assert enable("task") == {"app": "task", "state": "on", "chosen": True, "along": [], "already": True}
    assert recorded(events.APP_ENABLED) == []


@HUB_DB
def test_the_first_change_writes_down_every_app_of_the_business(hub_b):
    """A business on the baseline (born, every app off) gets its rows the first time it changes something: every app
    as it was, off, and the change; so a second change at the same time has rows to lock (the plan's limit). Another
    business keeps its own baseline."""
    born_off()
    with use_hub(hub_b):
        born_off(B.key)

    enable("task")

    expected = {label: Activation(OFF, False) for label in activation.module_graph()}
    expected["task"] = Activation(ON, True)
    expected["staff"] = Activation(ON, False)  # what Tasks needs comes along, not chosen
    assert rows() == expected
    with use_hub(hub_b):
        assert (rows(B.key), by_id(app_list(B))["task"]["state"]) == ({}, "off")


@HUB_DB
def test_an_unknown_app_or_the_platform_is_not_found():
    before = rows()
    for label in ("nope", "base", "live", "peluquería"):
        with pytest.raises(NotFound):
            enable(label)
        with pytest.raises(NotFound):
            disable(label)
    assert rows() == before


# ── By its name, as the person says it (BASE-F23, F24; hub#539) ────────────────────────────────────────────


def app_get(app, *, language="en", permissions=(HOME,)):
    op = get("base.app.get")
    context = OperationContext(scope=A, actor="ana", permissions=frozenset(permissions), language=language)
    return op(context, op.input.model_validate({"app": app})).model_dump(mode="json")


@HUB_DB
def test_the_app_the_person_names_goes_on_never_another_whose_name_starts_the_same():
    """«Activa la app de reservas» with Reservas off and Reservas online on turned on Reservas online (hub#539)."""
    set_rows(online_booking="on*", appointment="on", customer="on", service="on", staff="on")

    answer = enable("reservas", context=ctx(language="es"))

    assert (answer["app"], answer["state"], answer["already"]) == ("reservation", "on", False)
    assert rows()["reservation"] == Activation(ON, True)
    assert rows()["online_booking"] == Activation(ON, True)
    assert [payload["app"] for _, payload in recorded(events.APP_ENABLED)] == ["reservation"]


@HUB_DB
@pytest.mark.parametrize(
    ("said", "language", "app"),
    [
        ("reservation", "es", "reservation"),  # its id, whatever the language
        ("Reservas online", "es", "online_booking"),  # its whole name
        ("RESERVAS", "es", "reservation"),  # case aside
        ("facturacion", "es", "invoice"),  # accents aside
        ("Reservations", "es", "reservation"),  # its English name, whatever the person's language
        ("Online booking", "en", "online_booking"),
        ("booking", "en", "online_booking"),  # the only one with a word of its name that starts so
        ("tpv", "es", "sale"),  # «Ventas / TPV»
    ],
)
def test_an_app_is_named_by_its_id_or_by_its_name_as_the_person_says_it(said, language, app):
    set_rows()
    assert app_get(said, language=language)["id"] == app
    assert enable(said, context=ctx(language=language))["app"] == app
    assert disable(said, context=ctx(language=language))["app"] == app


@HUB_DB
def test_a_name_that_fits_several_apps_is_refused_naming_them_and_changes_nothing():
    """«reserva» is Reservas and Reservas online: the assistant asks which one, never picks one (hub#539)."""
    set_rows(online_booking="on*", appointment="on", customer="on", service="on", staff="on")
    before = rows()
    for turn in (enable, disable, app_get):
        with pytest.raises(Conflict) as refused:
            turn("reserva", **({"language": "es"} if turn is app_get else {"context": ctx(language="es")}))
        assert (refused.value.status, refused.value.code) == (409, "base.app_ambiguous")
        assert {"Reservas", "Reservas online"} <= set(re.findall(r"Reservas(?: online)?", str(refused.value)))
    assert rows() == before
    assert recorded(events.APP_ENABLED) == recorded(events.APP_DISABLED) == []


@HUB_DB
def test_one_already_on_says_so_also_when_it_had_come_along_with_another():
    """«Activa la app de clientes» with Clientes on (it came with Sales): it was on already, and the answer says so."""
    set_rows(sale="on*", tax="on", customer="on")
    answer = enable("clientes", context=ctx(language="es"))
    assert (answer["app"], answer["state"], answer["already"]) == ("customer", "on", True)


@HUB_DB
def test_the_read_says_which_app_a_name_names_and_whether_it_is_on(monkeypatch):
    set_rows(online_booking="on*", appointment="on", customer="on", service="on", staff="on")
    said = {app: row["summary"] for app, row in by_id(app_list(language="es")).items()}
    assert app_get("reservas", language="es") == {
        "id": "reservation", "name": "Reservas", "summary": said["reservation"], "state": "off", "mandatory": False
    }
    assert app_get("Reservas online", language="es") == {
        "id": "online_booking", "name": "Reservas online", "summary": said["online_booking"], "state": "on",
        "mandatory": False,
    }
    assert app_get("online_booking")["name"] == "Online booking"
    with pytest.raises(NotFound):
        app_get("nope")
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep(A.key, {"modules": []})
    assert app_get("task")["state"] == "blocked"


def test_the_read_is_for_who_sees_the_home_and_told_to_the_assistant():
    op = get("base.app.get")
    assert (op.kind, op.permission) == ("query", HOME)
    assert description(op)


@HUB_DB
def test_the_assistants_card_names_the_app_by_its_name_never_by_its_id():
    """hub#539: the card said «online_booking», and the person confirmed Reservas online asking for Reservas."""
    from base import assistant

    set_rows()

    def card(name, app, language):
        shown = assistant.cards.card(get(name), {"app": app}, language, ctx(language=language))
        return [(field["name"], field["value"]) for field in shown["fields"]]

    assert card("base.app.enable", "online_booking", "es") == [
        ("app", "Reservas online"),
        ("along", "Reservas online necesita Citas, Clientes, Horarios, Impuestos, Personal y Servicios: se activan con ella."),
    ]
    assert card("base.app.disable", "online_booking", "es") == [("app", "Reservas online")]
    assert card("base.app.enable", "reservas", "en") == [
        ("app", "Reservations"),
        ("along", "Reservations needs Customers, Sales & POS, Schedules, Tables, and Taxes: they turn on with it."),
    ]
    assert card("base.app.disable", "reservas", "en") == [("app", "Reservations")]


@HUB_DB
def test_the_apps_to_turn_off_first_are_named_as_the_screen_joins_them():
    Hub.objects.filter(slug=A.key).update(country="PL")
    set_rows(customer="on", tax="on*", sale="on*", table="on*", invoice="on*")

    with pytest.raises(Conflict) as refused:
        disable("customer")

    assert refused.value.message == "Turn off Invoicing, Sales & POS, and Tables first."


@HUB_DB
def test_a_paid_app_without_its_right_cannot_be_turned_on(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "premium", True)
    keep(A.key, {"modules": []})
    set_rows(staff="on*")

    with pytest.raises(EntitlementBlocked) as refused:
        enable("task")

    assert (refused.value.status, refused.value.code) == (402, "app_entitlement_blocked")
    assert rows()["task"] == Activation(OFF, False)


@HUB_DB
def test_only_who_runs_the_business_turns_apps_on_or_off():
    for name in ("base.app.enable", "base.app.disable"):
        with pytest.raises(PermissionDenied):
            run(name, "task", context=ctx(HOME))


# ── The plan's limit ────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_at_the_limit_one_more_is_refused_with_402_and_what_counts():
    with_limit(A.key, 2)
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


@HUB_DB
def test_the_limit_is_said_in_the_language_of_who_asks():
    with_limit(A.key, 2)
    set_rows(task="on*", website="on*")
    with pytest.raises(OperationError) as refused:
        enable("flow", context=ctx(language="es"))
    assert refused.value.message == "Has llegado al límite de 2 apps de tu plan. Mejora el plan o desactiva una."


@HUB_DB
def test_what_comes_along_does_not_count():
    with_limit(A.key, 2)
    set_rows(invoice="on*", sale="on", tax="on", customer="on")

    enable("task")  # 1 chosen (invoice) + task = 2: staff comes along, uncounted

    assert app_list()["enabled"] == 2
    assert rows()["staff"] == Activation(ON, False)


@HUB_DB
def test_choosing_one_that_came_along_counts():
    with_limit(A.key, 1)
    set_rows(invoice="on*", sale="on", tax="on", customer="on")
    with pytest.raises(OperationError) as refused:
        enable("sale")
    assert refused.value.code == "base.app_limit_reached"
    assert rows()["sale"] == Activation(ON, False)


@HUB_DB
@pytest.mark.parametrize(
    "photo",
    [
        {"plan": {"slug": "pro", "max_users": 0, "max_devices": 0, "max_apps": 0}},  # 0 = no limit
        {"plan": {"slug": "free", "max_users": 0, "max_devices": 0}},  # a photo without the field
        {},
    ],
)
def test_no_limit_without_a_positive_max_apps(photo):
    keep(A.key, photo)
    set_rows(task="on*", staff="on", website="on*", flow="on*")
    enable("cart_checkout")
    assert app_list()["max_apps"] is None and app_list()["enabled"] == 4


@HUB_DB
def test_a_lower_plan_turns_nothing_off_and_only_refuses_one_more():
    with_limit(A.key, 20)
    graph = activation.module_graph()
    before = by_id(app_list())

    with_limit(A.key, 5)  # bought down: 17 chosen, 5 allowed

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


@HUB_DB
def test_the_limit_is_this_business_own(hub_b):
    with_limit(A.key, 1)
    keep(B.key, {})
    set_rows(A.key, task="on*", staff="on")
    with use_hub(hub_b):
        set_rows(B.key, task="on*", staff="on")
        enable("website", context=ctx(scope=B))
    with pytest.raises(OperationError):
        enable("website")


# ── Turning one off ─────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_turning_one_off_turns_off_what_came_with_it_and_records_its_event():
    set_rows(invoice="on*", sale="on", tax="on*", customer="on", task="on*", staff="on")

    answer = disable("invoice")

    assert answer == {
        "app": "invoice",
        "state": "off",
        "chosen": False,
        "along": [{"id": "customer", "name": "Customers"}, {"id": "sale", "name": "Sales & POS"}],
        "already": False,
    }
    now = rows()
    assert [label for label, row in now.items() if row.on] == ["staff", "task", "tax"]
    assert recorded(events.APP_DISABLED) == [(A.key, {"app": "invoice", "along": ["customer", "sale"]})]


@HUB_DB
def test_one_another_app_on_needs_is_refused_with_409_naming_them():
    # Outside Spain, where VeriFactu can go off: turning it off first is something the person can do (hub#619).
    Hub.objects.filter(slug=A.key).update(country="PL")
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


@HUB_DB
def test_the_409_is_said_in_the_language_of_who_asks():
    set_rows(task="on*", staff="on")
    with pytest.raises(Conflict) as refused:
        disable("staff", context=ctx(language="es"))
    assert refused.value.message == "Desactiva antes Tareas."


@HUB_DB
def test_one_already_off_changes_nothing_and_records_nothing():
    set_rows(task="on*", staff="on")
    assert disable("flow") == {"app": "flow", "state": "off", "chosen": False, "along": [], "already": True}
    assert recorded(events.APP_DISABLED) == []


@HUB_DB
def test_an_app_may_veto_going_off_with_its_reason(monkeypatch):
    """The hook an app declares on its config, told which business asks."""
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
    assert refused.value.message == "Close the open tasks of tenant-a first."
    assert seen == [A]
    assert rows()["task"] == Activation(ON, True)


@HUB_DB
def test_a_veto_is_said_in_the_language_of_who_asks(monkeypatch):
    """BASE-F25: an app's reason comes in the asker's language, whatever the
    language the process runs in (the assistant, an API key), even from a hook that only calls gettext."""
    from django.utils.translation import gettext

    monkeypatch.setattr(
        apps.get_app_config("task"),
        "can_disable",
        lambda ctx: gettext("Turn off %(apps)s first.") % {"apps": "Tareas abiertas"},
        raising=False,
    )
    set_rows(task="on*", staff="on")

    with pytest.raises(Conflict) as refused:
        disable("task", context=ctx(language="es"))

    assert refused.value.envelope()["error"]["code"] == "base.app_vetoed"
    assert refused.value.message == "Desactiva antes Tareas abiertas."


@HUB_DB
def test_what_would_go_off_along_may_veto_too(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("staff"), "can_disable", lambda ctx: "Staff is busy.", raising=False)
    set_rows(task="on*", staff="on")
    with pytest.raises(Conflict) as refused:
        disable("task")
    assert refused.value.envelope()["error"]["app"] == "staff"
    assert rows()["task"] == Activation(ON, True)


@HUB_DB
def test_one_needed_by_an_app_that_refuses_says_why_instead_of_asking_the_impossible(monkeypatch):
    """hub#619: «Turn off Tasks first» is an instruction nobody can follow while Tasks refuses to go off."""
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: "Tasks are open.", raising=False)
    set_rows(task="on*", staff="on")

    with pytest.raises(Conflict) as refused:
        disable("staff")

    error = refused.value.envelope()["error"]
    assert (refused.value.status, error["code"], error["app"]) == (409, "base.app_vetoed", "task")
    assert refused.value.message == "Staff can't be turned off: Tasks needs it. Tasks are open."
    assert "required_by" not in error
    assert rows()["staff"] == Activation(ON, False)
    assert recorded(events.APP_DISABLED) == []


@HUB_DB
def test_that_sentence_is_said_in_the_language_of_who_asks(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: "Hay tareas abiertas.", raising=False)
    set_rows(task="on*", staff="on")

    with pytest.raises(Conflict) as refused:
        disable("staff", context=ctx(language="es"))

    assert refused.value.message == "Personal no se puede desactivar: hace falta para Tareas. Hay tareas abiertas."


@HUB_DB
def test_one_that_refuses_itself_says_its_own_reason_even_while_another_app_needs_it(monkeypatch):
    """«Turn off Tasks first» would be a dead end: Tasks goes off, and then Staff still refuses."""
    monkeypatch.setattr(apps.get_app_config("staff"), "can_disable", lambda ctx: "Staff is busy.", raising=False)
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: None, raising=False)
    set_rows(task="on*", staff="on")

    assert by_id(app_list())["staff"]["refusal"] == "Staff is busy."
    with pytest.raises(Conflict) as refused:
        disable("staff")

    error = refused.value.envelope()["error"]
    assert (error["code"], error["app"]) == ("base.app_vetoed", "staff")
    assert refused.value.message == "Staff is busy."
    assert rows()["staff"] == Activation(ON, False)


@HUB_DB
def test_while_none_of_those_that_need_it_refuses_it_still_says_which_to_turn_off_first(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: None, raising=False)
    set_rows(task="on*", staff="on")

    with pytest.raises(Conflict) as refused:
        disable("staff")

    assert refused.value.envelope()["error"]["code"] == "base.app_required"
    assert refused.value.message == "Turn off Tasks first."


@HUB_DB
def test_an_app_without_a_reason_lets_it_go(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: None, raising=False)
    set_rows(task="on*", staff="on")
    disable("task")
    assert rows()["task"] == Activation(OFF, False)


@HUB_DB
def test_one_that_refuses_itself_says_its_own_reason_before_that_of_an_app_that_needs_it(monkeypatch):
    """Its own reason is the one that holds: turning the other off would still leave it refusing (hub#997: Taxes, which
    VeriFactu needs in Spain, says that it is mandatory, not that VeriFactu needs it)."""
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: "Tasks are open.", raising=False)
    monkeypatch.setattr(apps.get_app_config("staff"), "can_disable", lambda ctx: "Staff is busy.", raising=False)
    set_rows(task="on*", staff="on")

    assert by_id(app_list())["staff"]["refusal"] == "Staff is busy."
    with pytest.raises(Conflict) as refused:
        disable("staff")
    assert (refused.value.envelope()["error"]["app"], refused.value.message) == ("staff", "Staff is busy.")


# ── An app the business must have on in its country (hub#997, BASE-F25) ─────────────────────────────────────────
# Taxes says it is mandatory everywhere (apps/tax/apps.py) and has no reason of its own to refuse: base's. The local
# hub ``a`` has no country: it is in Spain.

MANDATORY_HERE = "Taxes is mandatory for businesses in Spain: it can't be turned off."


@HUB_DB
def test_one_the_business_must_have_on_is_refused_with_409_and_stays_on():
    set_rows(tax="on*")

    with pytest.raises(Conflict) as refused:
        disable("tax")

    error = refused.value.envelope()["error"]
    assert (refused.value.status, error["code"], error["app"]) == (409, "base.app_vetoed", "tax")
    assert refused.value.message == MANDATORY_HERE
    assert rows()["tax"] == Activation(ON, True)
    assert recorded(events.APP_DISABLED) == []


@HUB_DB
def test_its_refusal_names_the_business_country_in_the_language_of_who_asks():
    Hub.objects.filter(slug=A.key).update(country="PL")
    set_rows(tax="on*")

    with pytest.raises(Conflict) as refused:
        disable("tax", context=ctx(language="es"))

    assert refused.value.message == "Impuestos es obligatoria para los negocios de Polonia: no se puede desactivar."
    assert by_id(app_list(language="es"))["tax"]["refusal"] == refused.value.message


@HUB_DB
def test_while_an_app_on_needs_it_it_says_it_is_mandatory_not_which_to_turn_off_first():
    """«Turn off Sales first» would be a dead end: Sales goes off, and Taxes still stays on."""
    set_rows(sale="on*", tax="on", customer="on")

    with pytest.raises(Conflict) as refused:
        disable("tax")

    error = refused.value.envelope()["error"]
    assert (error["code"], error["app"], refused.value.message) == ("base.app_vetoed", "tax", MANDATORY_HERE)
    assert "required_by" not in error
    assert rows()["tax"] == Activation(ON, False)


@HUB_DB
def test_turning_off_the_app_it_came_with_leaves_it_on():
    """The cascade of BASE-F23 skips it: Customers goes off with Sales, Taxes stays on (not chosen: it never counts
    against the plan's limit)."""
    set_rows(sale="on*", tax="on", customer="on")

    assert by_id(app_list())["sale"]["refusal"] is None
    answer = disable("sale")

    assert answer["along"] == [{"id": "customer", "name": "Customers"}]
    assert rows()["tax"] == Activation(ON, False)
    assert {label: rows()[label].state for label in ("sale", "customer")} == {"sale": OFF, "customer": OFF}
    assert recorded(events.APP_DISABLED) == [(A.key, {"app": "sale", "along": ["customer"]})]


@HUB_DB
def test_turning_off_the_app_it_came_with_never_asks_it(monkeypatch):
    """Only what would go off is asked whether it refuses: Taxes stays on, so its hook is not run."""
    asked = []
    monkeypatch.setattr(apps.get_app_config("tax"), "can_disable", lambda ctx: asked.append(ctx.scope), raising=False)
    set_rows(sale="on*", tax="on", customer="on")

    disable("sale")

    assert asked == []
    assert rows()["tax"] == Activation(ON, False)


@HUB_DB
def test_one_mandatory_only_in_another_country_goes_off_here(monkeypatch):
    monkeypatch.setattr(
        apps.get_app_config("task"), "mandatory", {"countries": ["PL"], "platform_turns_on": False}, raising=False
    )
    set_rows(task="on*", staff="on")

    assert by_id(app_list())["task"]["refusal"] is None
    disable("task")

    assert rows()["task"] == Activation(OFF, False)


@HUB_DB
def test_each_hub_keeps_on_what_its_own_business_country_requires(hub_a, hub_b, monkeypatch):
    """Two businesses with their own databases: Tasks, mandatory in Poland only, stays on in A's (Poland) and goes off
    in B's (Spain); neither reads the other's country."""
    monkeypatch.setattr(
        apps.get_app_config("task"), "mandatory", {"countries": ["PL"], "platform_turns_on": False}, raising=False
    )
    Hub.objects.filter(slug=hub_a.slug).update(country="PL")
    Hub.objects.filter(slug=hub_b.slug).update(country="ES")
    of_a, of_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)

    with use_hub(hub_a), pytest.raises(Conflict) as refused:
        disable("task", context=ctx(scope=of_a))
    assert refused.value.message == "Tasks is mandatory for businesses in Poland: it can't be turned off."
    with use_hub(hub_b):
        assert disable("task", context=ctx(scope=of_b))["state"] == "off"
    with use_hub(hub_a):
        assert activation.states_of(of_a)["task"].on


# ── Over HTTP ───────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("path", "operation"), [("/apps/enable", "base.app.enable"), ("/apps/disable", "base.app.disable")])
def test_the_routes_are_bound_to_their_commands(path, operation):
    assert_bound("POST", path, operation)


@HUB_DB
def test_which_app_a_name_names_is_read_over_http(client, make_user):
    client.force_login(make_user("ana", host=A.key, role="hub_owner"))
    answered = client.get("/api/apps/detail", {"app": "Reservas online"}, HTTP_HOST=HOST)
    assert (answered.status_code, answered.json()["id"]) == (200, "online_booking")
    refused = client.get("/api/apps/detail", {"app": "reserva"}, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "base.app_ambiguous")


@HUB_DB
def test_an_owner_turns_one_off_over_http_and_a_cashier_is_refused(client, make_user):
    body = json.dumps({"app": "task"})
    client.force_login(make_user("eva", host=A.key, role="hub_employee"))
    refused = client.post("/api/apps/disable", body, content_type="application/json", HTTP_HOST=HOST)
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")

    client.force_login(make_user("ana", host=A.key, role="hub_owner"))
    answered = client.post("/api/apps/disable", body, content_type="application/json", HTTP_HOST=HOST)
    assert (answered.status_code, answered.json()["state"]) == (200, "off")
    gone = client.get("/api/task/tasks", HTTP_HOST=HOST)
    assert (gone.status_code, gone.json()["error"]["code"]) == (404, "app_inactive")

    with_limit(A.key, 1)
    over = client.post("/api/apps/enable", body, content_type="application/json", HTTP_HOST=HOST)
    assert over.status_code == 402
    assert {key: over.json()["error"][key] for key in ("code", "max_apps", "enabled")} == {
        "code": "base.app_limit_reached",
        "max_apps": 1,
        "enabled": 16,
    }
