"""The Home's three live queries: ``base.setup.status``, ``base.widget.list`` and ``base.bell.counters``.

PLAN-HUB round 2026-10-21. Each module declares its steps, panels and counters in its ``LiveAppConfig`` and base runs
their queries by name, as the person of the request, with the old hub's rules (``setup_status.rs``): only modules on
in the scope, the hub's country, the person's permission (but a pending ⛔ stays, not actionable), a step whose query
fails is left out. The stand-in modules here name real operations registered for the test.
"""

import json
import logging
from types import SimpleNamespace

import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.meta import BellCounter, SetupCheck, SetupStep, Widget
from live.operations import Operation, get, registry
from live.outbox import channel_for
from live.models import OutboxEvent
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict

from base.models import EventDelivery, Hub, Membership
from base.schemas import BellCountersIn, BellCountersOut, SetupStatusIn, SetupStatusOut, WidgetListIn, WidgetListOut

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")
HOME = "base.view_home"
ADMIN = "base.administer_hub"


class AnyIn(BaseModel):
    """Whatever the step's params are (a ninja Schema would drop the fields it does not declare)."""

    model_config = ConfigDict(extra="allow")


class AnyOut(BaseModel):
    model_config = ConfigDict(extra="allow")


@pytest.fixture
def declare(monkeypatch):
    """Registers a query ``name`` answering ``answer(ctx, data)`` (a dict, or raising), for this test only."""

    def declare(name, answer, permission=None):
        op = Operation(
            name=name,
            kind="query",
            permission=permission,
            input=AnyIn,
            output=AnyOut,
            expose_api=False,
            ai=None,
            fn=lambda ctx, data: answer(ctx, data) if callable(answer) else answer,
        )
        monkeypatch.setitem(registry, name, op)
        return op

    return declare


@pytest.fixture
def modules(monkeypatch, settings):
    """The modules base sees (all of them on in every scope unless ``on`` says otherwise)."""
    settings.HOME_UNLISTED_HOOKS = True

    def use(*configs, on=None):
        labels = {config.label for config in configs} if on is None else set(on)
        monkeypatch.setattr("base.home.module_configs", lambda: list(configs))
        monkeypatch.setattr("base.queries.active_apps", lambda scope: frozenset(labels | {"base"}))

    use()
    return use


def module(label, *, setup=(), widgets=(), bell=(), listed=True, permissions=(), name=None):
    return SimpleNamespace(
        label=label,
        verbose_name=name or label.capitalize(),
        listed=listed,
        setup=list(setup),
        widgets=list(widgets),
        bell=list(bell),
        permissions=list(permissions),
    )


def ctx(*permissions, scope=A, actor="ana", language="en"):
    return OperationContext(scope=scope, actor=actor, permissions=frozenset({HOME, *permissions}), language=language)


def setup_status(context):
    return get("base.setup.status")(context, SetupStatusIn()).model_dump(mode="json")


def keys(document):
    return [item["key"] for item in document["items"]]


def by_key(document):
    return {item["key"]: item for item in document["items"]}


def step(key="catalog", operation="stock.catalog.status", **fields):
    return SetupStep(key=key, operation=operation, title=fields.pop("title", "Your catalog"), route="/stock", **fields)


# --- Declarations -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "input", "output"),
    [
        ("base.setup.status", SetupStatusIn, SetupStatusOut),
        ("base.widget.list", WidgetListIn, WidgetListOut),
        ("base.bell.counters", BellCountersIn, BellCountersOut),
    ],
)
def test_declarations(name, input, output):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == ("query", HOME, input, output)


def test_the_assistant_reads_the_setup_status():
    """BASE-G128: the assistant gets the same document as a tool; it never takes on a step «not available»."""
    ai = get("base.setup.status").ai
    assert "not available" in ai["description"]


# --- base.setup.status: the platform's steps (base.apps, base.team) ----------------------------------------


def test_the_platforms_steps_for_an_administrator(modules, make_user):
    modules(module("sale"))
    make_user("ana", host="a", role=Membership.Role.OWNER)

    document = setup_status(ctx(ADMIN))

    assert keys(document) == ["base.apps", "base.team"]
    apps, team = document["items"]
    assert {k: apps[k] for k in ("app", "state", "level", "required", "actionable", "route", "order")} == {
        "app": "base",
        "state": "done",
        "level": "functional",
        "required": True,
        "actionable": True,
        "route": "/apps",
        "order": 10,
    }
    assert {k: team[k] for k in ("state", "level", "required", "route", "order")} == {
        "state": "pending",
        "level": "recommended",
        "required": False,
        "route": "/employees",
        "order": 80,
    }
    assert (apps["title"], team["title"]) == ("Your apps", "Your team")


def test_the_platforms_steps_are_translated(modules):
    modules(module("sale"))

    apps, team = setup_status(ctx(ADMIN, language="es"))["items"]

    assert (apps["title"], team["title"]) == ("Tus apps", "Tu equipo")
    assert apps["description"].startswith("Activa al menos una app")


def test_your_apps_is_pending_without_an_app_on_and_unavailable_when_none_can_be(modules):
    modules(module("sale"), module("stock"), on=[])
    assert by_key(setup_status(ctx(ADMIN)))["base.apps"]["state"] == "pending"

    modules(module("demo", listed=False))  # the reference app is no business app
    document = setup_status(ctx(ADMIN))
    assert by_key(document)["base.apps"]["state"] == "unavailable"
    assert document["unavailable"] == 1


def test_your_team_is_done_with_two_active_people_in_this_hub(modules, make_user):
    modules(module("sale"))
    make_user("ana", host="a", role=Membership.Role.OWNER)
    make_user("bea", host="b")  # another hub's
    make_user("cris", host="a", is_active=False)
    assert by_key(setup_status(ctx(ADMIN)))["base.team"]["state"] == "pending"

    make_user("dani", host="a")
    assert by_key(setup_status(ctx(ADMIN)))["base.team"]["state"] == "done"


def test_whoever_cannot_administer_the_hub_gets_no_platform_step(modules):
    modules(module("sale"))
    assert setup_status(ctx()) == {"total": 0, "pending": 0, "unavailable": 0, "blocking_pending": 0, "items": []}


# --- base.setup.status: the modules' steps ---------------------------------------------------------------


def test_a_step_is_done_when_its_conditions_pass_on_the_first_row(modules, declare):
    declare("stock.catalog.status", {"rows": [{"products": 3, "state": "ready"}, {"products": 0}]})
    declare("stock.price.status", {"rows": [{"products": 0}]})
    modules(
        module(
            "stock",
            setup=[
                step(configured_when=[SetupCheck(field="products", truthy=True), SetupCheck(field="state", equals="ready")]),
                step("prices", "stock.price.status", configured_when=[SetupCheck(field="products", truthy=True)]),
            ],
        )
    )

    items = by_key(setup_status(ctx()))

    assert (items["stock.catalog"]["state"], items["stock.prices"]["state"]) == ("done", "pending")
    assert items["stock.catalog"] | {"title": None} == {
        "key": "stock.catalog",
        "app": "stock",
        "state": "done",
        "level": "functional",
        "required": True,
        "actionable": True,
        "title": None,
        "description": "",
        "icon": "ion:settings-outline",
        "route": "/stock",
        "order": 500,
    }


def test_without_a_row_a_step_is_pending_and_with_no_conditions_a_row_is_enough(modules, declare):
    declare("stock.empty.status", {"rows": []})
    declare("stock.any.status", {"rows": [{"x": 0}]})
    modules(module("stock", setup=[step("empty", "stock.empty.status"), step("any", "stock.any.status")]))

    items = by_key(setup_status(ctx()))

    assert (items["stock.empty"]["state"], items["stock.any"]["state"]) == ("pending", "done")


def test_the_query_runs_as_the_person_with_the_steps_params(modules, declare):
    seen = []
    declare("stock.catalog.status", lambda c, data: seen.append((c.actor, data.model_dump())) or {"n": 1})
    modules(module("stock", setup=[step(params={"kind": "service"})]))

    setup_status(ctx(actor="bea"))

    assert seen == [("bea", {"kind": "service"})]


def test_a_step_whose_query_fails_is_left_out_and_logged(modules, declare, caplog):
    def broken(c, data):
        raise NotFound("gone")

    declare("stock.catalog.status", broken)
    declare("stock.price.status", {"n": 1})
    modules(module("stock", setup=[step(), step("prices", "stock.price.status")]))

    with caplog.at_level(logging.WARNING, logger="base.home"):
        document = setup_status(ctx())

    assert keys(document) == ["stock.prices"]
    assert "stock.catalog" in caplog.text


def test_a_step_whose_query_the_person_may_not_run_is_left_out(modules, declare):
    declare("stock.catalog.status", {"n": 1}, permission="stock.view")
    modules(module("stock", setup=[step()], permissions=["stock.view"]))

    assert keys(setup_status(ctx())) == []
    assert keys(setup_status(ctx("stock.view"))) == ["stock.catalog"]


def test_a_step_needing_a_permission_the_person_lacks_is_not_on_their_list(modules, declare):
    declare("stock.catalog.status", {"n": 0})
    modules(module("stock", setup=[step(permission="stock.manage")], permissions=["stock.manage"]))

    assert keys(setup_status(ctx())) == []
    assert by_key(setup_status(ctx("stock.manage")))["stock.catalog"]["actionable"] is True


def test_a_pending_wall_stays_for_who_cannot_clear_it_but_not_actionable(modules, declare):
    """hub#435: the person at the till cannot set the business details up, yet they are what stops the invoice."""
    answer = {"configured": False}
    declare("invoice.identity.status", lambda c, data: answer, permission="invoice.view_invoice")
    wall = step("business_identity", "invoice.identity.status", permission="invoice.change_settings",
                configured_when=[SetupCheck(field="configured", truthy=True)])
    modules(module("invoice", setup=[wall], permissions=["invoice.view_invoice", "invoice.change_settings"]))

    document = setup_status(ctx())  # an employee: neither permission

    assert by_key(document)["invoice.business_identity"] | {"title": None, "description": None} == {
        "key": "invoice.business_identity",
        "app": "invoice",
        "state": "pending",
        "level": "legal",
        "required": True,
        "actionable": False,
        "title": None,
        "description": None,
        "icon": "ion:settings-outline",
        "route": "/stock",
        "order": 500,
    }
    assert document["blocking_pending"] == 1
    assert by_key(setup_status(ctx("invoice.change_settings", "invoice.view_invoice")))[
        "invoice.business_identity"
    ]["actionable"] is True

    answer["configured"] = True  # done: not their task, so off their list
    assert keys(setup_status(ctx())) == []
    assert setup_status(ctx())["blocking_pending"] == 0


def test_the_level_is_bases_never_the_modules(modules, declare):
    declare("stock.catalog.status", {"n": 1})
    modules(module("stock", setup=[step(required=True), step("photos", required=False)]))

    items = by_key(setup_status(ctx()))

    assert (items["stock.catalog"]["level"], items["stock.photos"]["level"]) == ("functional", "recommended")


def test_a_national_step_shows_only_in_a_hub_of_its_country(modules, declare):
    declare("stock.catalog.status", {"n": 1})
    modules(module("stock", setup=[step(countries=["ES"])]))
    assert keys(setup_status(ctx())) == []  # the hub has no country

    Hub.objects.filter(slug="a").update(country="ES")
    assert keys(setup_status(ctx())) == ["stock.catalog"]
    assert keys(setup_status(ctx(scope=B))) == []


def test_a_module_off_in_the_scope_brings_no_step(modules, declare):
    declare("stock.catalog.status", {"n": 1})
    modules(module("stock", setup=[step()]), on=[])

    assert keys(setup_status(ctx())) == []


def test_a_module_out_of_the_store_brings_no_step_to_a_customer(modules, declare, settings):
    declare("demo.item.stats", {"total": 0})
    modules(module("demo", setup=[step("first_item", "demo.item.stats")], listed=False))
    assert keys(setup_status(ctx())) == ["demo.first_item"]

    settings.HOME_UNLISTED_HOOKS = False
    assert keys(setup_status(ctx())) == []


def test_order_then_key_and_the_titles_in_the_persons_language(modules, declare, make_user):
    declare("stock.catalog.status", {"n": 1})
    modules(
        module(
            "stock",
            setup=[
                step("zeta", order=20, title=gettext_lazy("Your team")),
                step("alpha", order=20),
                step("late"),
            ],
        )
    )

    document = setup_status(ctx(ADMIN, language="es"))

    assert keys(document) == ["base.apps", "stock.alpha", "stock.zeta", "base.team", "stock.late"]
    assert by_key(document)["stock.zeta"]["title"] == "Tu equipo"


def test_the_demos_example_step_for_real_with_the_setting_on(settings):
    """The real demo app (no stand-in): its step is pending until the hub has an item, then done."""
    from apps.demo.models import Item

    settings.HOME_UNLISTED_HOOKS = True
    owner = ctx(ADMIN, "demo.view", "demo.manage")
    assert by_key(setup_status(owner))["demo.first_item"]["state"] == "pending"

    Item.objects.create(name="First")
    item = by_key(setup_status(owner))["demo.first_item"]
    assert (item["state"], item["level"], item["route"]) == ("done", "recommended", "/demo/items/new")

    settings.HOME_UNLISTED_HOOKS = False  # a customer's hub, in prod
    assert "demo.first_item" not in keys(setup_status(owner))


# --- base.widget.list -----------------------------------------------------------------------------------


def widget_list(context):
    return get("base.widget.list")(context, WidgetListIn()).model_dump(mode="json")["widgets"]


def test_the_panels_the_person_may_see(modules):
    modules(
        module(
            "stock",
            name="Stock",
            permissions=["stock.view"],
            widgets=[
                Widget(key="today", title="Today", kind="kpi", operation="stock.item.count", params={"a": 1},
                       map={"value": "n"}, options={"format": "number"}, default=True, size="sm",
                       refresh_on=["stock.item.created"]),
                Widget(key="private", title="Private", kind="kpi", operation="stock.item.count", permission="stock.view"),
                Widget(key="chart", title="Chart", component="StockChart", category="Charts"),
            ],
        )
    )

    widgets = widget_list(ctx())

    assert [w["key"] for w in widgets] == ["stock.today", "stock.chart"]
    assert widgets[0] == {
        "key": "stock.today",
        "app": "stock",
        "title": "Today",
        "icon": "",
        "category": "Stock",  # without a category of its own, the app's name
        "size": "sm",
        "default": True,
        "kind": "kpi",
        "operation": "stock.item.count",
        "params": {"a": 1},
        "map": {"value": "n"},
        "options": {"format": "number"},
        "component": None,
        "refresh_on": ["stock.item.created"],
    }
    assert widgets[1]["category"] == "Charts"
    assert [w["key"] for w in widget_list(ctx("stock.view"))] == ["stock.today", "stock.private", "stock.chart"]


def test_a_panel_of_some_verticals_shows_only_in_a_hub_of_one_of_them(modules):
    modules(module("stock", widgets=[Widget(key="tables", title="Tables", component="Tables", verticals=["restaurant"])]))
    assert widget_list(ctx()) == []

    Hub.objects.filter(slug="a").update(vertical="restaurant")
    assert [w["key"] for w in widget_list(ctx())] == ["stock.tables"]


def test_panels_of_a_module_off_or_out_of_the_store(modules, settings):
    panel = Widget(key="w", title="W", component="W")
    modules(module("stock", widgets=[panel]), module("demo", widgets=[panel], listed=False), on=["demo"])
    assert [w["key"] for w in widget_list(ctx())] == ["demo.w"]

    settings.HOME_UNLISTED_HOOKS = False
    assert widget_list(ctx()) == []


# --- base.bell.counters ---------------------------------------------------------------------------------


def bell(context):
    return get("base.bell.counters")(context, BellCountersIn()).model_dump(mode="json")["counters"]


def counter(key="to_confirm", operation="stock.item.count", **fields):
    return BellCounter(key=key, operation=operation, route="/stock", label=fields.pop("label", "To confirm"), **fields)


def test_the_counters_above_zero(modules, declare):
    declare("stock.item.count", {"count": 2})
    declare("stock.low.count", {"rows": [{"count": 0}]})
    modules(module("stock", bell=[counter(icon="ion:alert"), counter("low", "stock.low.count")]))

    assert bell(ctx()) == [
        {"key": "stock.to_confirm", "app": "stock", "count": 2, "route": "/stock", "label": "To confirm", "icon": "ion:alert"}
    ]


def test_a_counter_the_person_may_not_see_or_whose_query_fails(modules, declare, caplog):
    def broken(c, data):
        raise RuntimeError("boom")

    declare("stock.item.count", {"count": 2})
    declare("stock.broken.count", broken)
    declare("stock.text.count", {"count": "many"})
    modules(
        module(
            "stock",
            permissions=["stock.view"],
            bell=[
                counter(permission="stock.view"),
                counter("broken", "stock.broken.count"),
                counter("text", "stock.text.count"),
            ],
        )
    )

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert bell(ctx()) == []
    assert "stock.broken" in caplog.text
    assert "stock.text" in caplog.text
    assert [c["key"] for c in bell(ctx("stock.view"))] == ["stock.to_confirm"]


def test_the_counters_of_a_module_out_of_the_store_only_where_the_setting_says(modules, declare, settings):
    declare("demo.item.open_count", {"count": 1})
    modules(module("demo", bell=[counter("open", "demo.item.open_count")], listed=False))
    assert [c["key"] for c in bell(ctx())] == ["demo.open"]

    settings.HOME_UNLISTED_HOOKS = False
    assert bell(ctx()) == []


def dead_event(scope, status=EventDelivery.Status.DEAD):
    event = OutboxEvent.objects.create(scope_kind=scope.kind, scope_key=scope.key, name="sale.sale.completed")
    return EventDelivery.objects.create(event=event, app_label="invoice", status=status, next_attempt_at=timezone.now())


def test_the_failed_events_of_this_hub_for_an_administrator(modules):
    """BASE-G137: the bell says how many events between apps the relay gave up on, in this hub only."""
    modules(module("sale"))
    dead_event(A)
    dead_event(A)
    dead_event(A, EventDelivery.Status.PENDING)
    dead_event(B)

    assert bell(ctx(ADMIN)) == [
        {"key": "base.failed_events", "app": "base", "count": 2, "route": "/system#events", "label": "Failed events",
         "icon": "ion:warning-outline"}
    ]
    assert bell(ctx(ADMIN, language="es"))[0]["label"] == "Eventos caídos"
    assert bell(ctx()) == []  # not an administrator
    assert [c["count"] for c in bell(ctx(ADMIN, scope=B))] == [1]


# --- Live: a write in hub B reaches B's channel only, and re-runs base's queries there ----------------------


@pytest.fixture
def listen(django_db_setup):
    from django.db import connections

    params = connections["default"].settings_dict
    dsn = make_conninfo(dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"],
                        host=params["HOST"], port=params["PORT"])
    sessions = []

    def open_session(scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=1.0, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_a_demo_item_written_in_b_notifies_b_only_and_re_runs_the_home_there(listen):
    from live.live_registry import live_registry

    from apps.demo.schemas import ItemIn

    on_a, on_b = listen(A), listen(B)
    get_user_model()  # the demo command runs as the person; no user is needed for the system context
    from live.context import system_context

    get("demo.item.create")(system_context(B), ItemIn(name="In B"))

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["demo.item.created"]})]
    assert received(on_a, timeout=0.3) == []
    assert {"base.setup.status", "base.bell.counters"} <= live_registry.affected(["demo.item.created"])
