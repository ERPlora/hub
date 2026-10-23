"""The Home's three live queries: ``base.setup.status``, ``base.widget.list`` and ``base.bell.counters``; and the
device's notices, ``base.notice.list`` (PLAN-HUB round 2026-10-23).

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
from live.meta import BellCounter, DeviceNotice, SetupCheck, SetupStep, Widget
from live.operations import Operation, get, registry
from live.outbox import channel_for
from live.models import OutboxEvent
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict

from base.models import EventDelivery, Hub, Membership
from base.schemas import (
    BellCountersIn,
    BellCountersOut,
    NoticeListIn,
    NoticeListOut,
    SetupStatusIn,
    SetupStatusOut,
    WidgetListIn,
    WidgetListOut,
)

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
    settings.SHOW_UNLISTED_MODULES = True

    def use(*configs, on=None):
        labels = {config.label for config in configs} if on is None else set(on)
        monkeypatch.setattr("base.home.module_configs", lambda: list(configs))
        monkeypatch.setattr("base.queries.active_apps", lambda scope: frozenset(labels | {"base"}))

    use()
    return use


def module(label, *, setup=(), widgets=(), bell=(), notices=(), listed=True, permissions=(), name=None):
    return SimpleNamespace(
        label=label,
        verbose_name=name or label.capitalize(),
        listed=listed,
        setup=list(setup),
        widgets=list(widgets),
        bell=list(bell),
        notices=list(notices),
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
        ("base.notice.list", NoticeListIn, NoticeListOut),
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
    declare("stock.catalog.status", {"n": 0}, permission="stock.view")
    pending = [SetupCheck(field="n", truthy=True)]
    modules(module("stock", setup=[step(permission="stock.manage", configured_when=pending)],
                   permissions=["stock.view", "stock.manage"]))

    assert keys(setup_status(ctx())) == []
    # Reading its query is not enough: the step is the work of whoever has its own permission.
    assert keys(setup_status(ctx("stock.view"))) == []
    assert by_key(setup_status(ctx("stock.view", "stock.manage")))["stock.catalog"]["actionable"] is True


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

    settings.SHOW_UNLISTED_MODULES = False
    assert keys(setup_status(ctx())) == []

    # A demo's hub shows the reference's example: there it is what the visitor came to see.
    Hub.objects.filter(slug="a").update(is_demo=True)
    assert keys(setup_status(ctx())) == ["demo.first_item"]


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

    settings.SHOW_UNLISTED_MODULES = True
    owner = ctx(ADMIN, "demo.view", "demo.manage")
    assert by_key(setup_status(owner))["demo.first_item"]["state"] == "pending"

    Item.objects.create(name="First")
    item = by_key(setup_status(owner))["demo.first_item"]
    assert (item["state"], item["level"], item["route"]) == ("done", "recommended", "/demo/items/new")

    settings.SHOW_UNLISTED_MODULES = False  # a customer's hub, in prod
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
        "live": False,  # stock.item.count is no live query: the Home asks for it once
    }
    assert widgets[1]["category"] == "Charts"
    assert [w["key"] for w in widget_list(ctx("stock.view"))] == ["stock.today", "stock.private", "stock.chart"]


def test_a_panel_says_whether_its_operation_is_a_live_query(modules, monkeypatch):
    # BASE-G168: the Home follows a live query and asks once for one that is not.
    from live.live_registry import live_registry

    modules(module("stock", widgets=[Widget(key="today", title="Today", kind="kpi", operation="stock.item.count"),
                                     Widget(key="chart", title="Chart", component="StockChart")]))
    monkeypatch.setitem(live_registry.subscribable, "stock.item.count", ["stock.item.created"])
    assert [(w["key"], w["live"]) for w in widget_list(ctx())] == [("stock.today", True), ("stock.chart", False)]


def test_a_panel_of_some_verticals_shows_only_in_a_hub_of_one_of_them(modules):
    modules(module("stock", widgets=[Widget(key="tables", title="Tables", component="Tables", verticals=["restaurant"])]))
    assert widget_list(ctx()) == []

    Hub.objects.filter(slug="a").update(vertical="restaurant")
    assert [w["key"] for w in widget_list(ctx())] == ["stock.tables"]


def test_panels_of_a_module_off_or_out_of_the_store(modules, settings):
    panel = Widget(key="w", title="W", component="W")
    modules(module("stock", widgets=[panel]), module("demo", widgets=[panel], listed=False), on=["demo"])
    assert [w["key"] for w in widget_list(ctx())] == ["demo.w"]

    settings.SHOW_UNLISTED_MODULES = False
    assert widget_list(ctx()) == []

    Hub.objects.filter(slug="a").update(is_demo=True)
    assert [w["key"] for w in widget_list(ctx())] == ["demo.w"]


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

    settings.SHOW_UNLISTED_MODULES = False
    assert bell(ctx()) == []

    Hub.objects.filter(slug="a").update(is_demo=True)
    assert [c["key"] for c in bell(ctx())] == ["demo.open"]


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


# --- base.notice.list (PLAN-HUB round 2026-10-23, APPOINTMENT-F28) ----------------------------------------------


def notice_list(context):
    return get("base.notice.list")(context, NoticeListIn()).model_dump(mode="json")["notices"]


def notice(key="added", operation="stock.item.changes", **fields):
    return DeviceNotice(
        key=key,
        operation=operation,
        title=fields.pop("title", (gettext_lazy("New item · {name}"), gettext_lazy("New item"))),
        route=fields.pop("route", "/stock?day={at:.10}"),
        **fields,
    )


CHANGES = {
    "rows": [
        {"id": 7, "at": "2026-10-23T09:45:00Z", "kind": "removed", "name": "Pen", "sku": "P-1", "shelf": ""},
        {"id": 3, "at": "2026-10-23T09:40:00Z", "kind": "added", "name": "", "sku": "B-2", "shelf": "A"},
        {"id": 5, "at": "2026-10-23T09:44:00+02:00", "kind": "added", "name": "Ink", "sku": "I-9", "shelf": "C"},
    ]
}


def test_the_rows_each_notice_tells_with_its_texts_the_newest_first(modules, declare):
    """Each declaration takes the rows that pass its ``when``; the title is the first template filled in, the body
    joins the parts filled in, and the route is filled in too. One query for the notices that share it."""
    calls = []
    declare("stock.item.changes", lambda c, data: calls.append(data) or CHANGES)
    modules(
        module(
            "stock",
            notices=[
                notice(when=[SetupCheck(field="kind", equals="added")], body=["{sku}", gettext_lazy("shelf {shelf}")]),
                notice("removed", when=[SetupCheck(field="kind", equals="removed")], title=["Item removed · {name}"]),
            ],
        )
    )

    assert notice_list(ctx()) == [
        {
            "key": "stock.removed",
            "app": "stock",
            "id": "7",
            "at": "2026-10-23T09:45:00Z",
            "title": "Item removed · Pen",
            "body": "",
            "route": "/stock?day=2026-10-23",
        },
        {
            "key": "stock.added",
            "app": "stock",
            "id": "3",
            "at": "2026-10-23T09:40:00Z",
            "title": "New item",
            "body": "B-2 · shelf A",
            "route": "/stock?day=2026-10-23",
        },
        {
            "key": "stock.added",
            "app": "stock",
            "id": "5",
            "at": "2026-10-23T09:44:00+02:00",
            "title": "New item · Ink",
            "body": "I-9 · shelf C",
            "route": "/stock?day=2026-10-23",
        },
    ]
    assert len(calls) == 1


def test_the_texts_are_in_the_persons_language(modules, declare):
    declare("stock.item.changes", CHANGES)
    modules(module("stock", notices=[notice(when=[SetupCheck(field="id", equals=5)], title=[gettext_lazy("Failed events")])]))

    assert [n["title"] for n in notice_list(ctx(language="es"))] == ["Eventos caídos"]


def test_the_query_runs_as_the_person_with_the_notices_params(modules, declare):
    seen = []
    declare("stock.item.changes", lambda c, data: seen.append((c.actor, data.model_dump())) or {"rows": []})
    modules(module("stock", notices=[notice(params={"limit": 5})]))

    assert notice_list(ctx(actor="bea")) == []
    assert seen == [("bea", {"limit": 5})]


def test_a_notice_the_person_may_not_see_or_whose_query_fails_is_left_out(modules, declare, caplog):
    def broken(c, data):
        raise RuntimeError("boom")

    declare("stock.item.changes", CHANGES)
    declare("stock.broken.changes", broken)
    modules(
        module(
            "stock",
            permissions=["stock.view"],
            notices=[notice(permission="stock.view"), notice("broken", "stock.broken.changes")],
        )
    )

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert notice_list(ctx()) == []
    assert "stock.broken" in caplog.text
    assert len(notice_list(ctx("stock.view"))) == 3


def test_a_template_its_translation_breaks_falls_to_the_next_and_is_logged(modules, declare, caplog):
    """A translator's typo in a field (``{nombre}``) must not lose the notice: the next title, and a line in the log."""
    declare("stock.item.changes", {"rows": [CHANGES["rows"][2]]})
    modules(module("stock", notices=[notice(title=["{nombre}", "New item"], body=["{sku:%Y}", "{shelf}"])]))

    with caplog.at_level(logging.WARNING, logger="base.home"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"]) == ("New item", "C")
    assert "stock.added" in caplog.text


def test_a_row_without_a_title_filled_in_is_not_told(modules, declare, caplog):
    declare("stock.item.changes", {"rows": [CHANGES["rows"][1]]})
    modules(module("stock", notices=[notice(title=["New item · {name}"])]))

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert notice_list(ctx()) == []
    assert "stock.added" in caplog.text


BOOKING = {
    "id": 9,
    "at": "2026-10-23T08:00:00Z",
    "offset": "2026-10-23T09:44:00+02:00",
    "wall": "2026-10-23T10:15:00",
    "day": "2026-10-23",
    "opens": "09:30:00",
    "code": "2026",
}


def test_a_template_formats_the_rows_dates_and_hours_on_the_businesss_clock(modules, declare):
    """The rows reach base as JSON, so a date is text: ``{at:%H:%M}`` reads it as the date, hour or instant it says,
    an instant on the business's clock (Django's zone) and one without an offset as it says; ``{at:.10}`` still
    slices the text, also beside a date format on the same field."""
    declare("stock.item.changes", {"rows": [BOOKING]})
    modules(
        module(
            "stock",
            notices=[
                notice(
                    title=["Appointment at {at:%H:%M}"],
                    body=["{offset:%H:%M}", "{wall:%H:%M}", "{day:%d/%m/%Y}", "opens {opens:%H:%M}"],
                    route="/agenda?date={at:.10}&hour={at:%H}",
                )
            ],
        )
    )

    with timezone.override("Europe/Madrid"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"], told["route"]) == (
        "Appointment at 10:00",
        "09:44 · 10:15 · 23/10/2026 · opens 09:30",
        "/agenda?date=2026-10-23&hour=10",
    )
    assert told["at"] == "2026-10-23T08:00:00Z"
    with timezone.override("Atlantic/Canary"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"]) == ("Appointment at 09:00", "08:44 · 10:15 · 23/10/2026 · opens 09:30")


def test_a_date_format_on_a_field_that_is_no_iso_date_is_logged_and_that_text_left_out(modules, declare, caplog):
    """``{code:%Y}`` on ``"2026"`` (a year as text, not an ISO date) is a module's mistake: never read as some hour."""
    declare("stock.item.changes", {"rows": [BOOKING]})
    modules(module("stock", notices=[notice(title=["Year {code:%Y}", "New item"], body=["{code:%H}", "{day:%d/%m}"])]))

    with caplog.at_level(logging.WARNING, logger="base.home"), timezone.override("Europe/Madrid"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"]) == ("New item", "23/10")
    assert "Year {code:%Y}" in caplog.text


def test_the_notices_of_a_module_off_or_out_of_the_store(modules, declare, settings):
    declare("stock.item.changes", CHANGES)
    modules(module("stock", notices=[notice()]), on=[])
    assert notice_list(ctx()) == []

    modules(module("stock", notices=[notice()], listed=False))
    settings.SHOW_UNLISTED_MODULES = False
    assert notice_list(ctx()) == []


def test_it_says_which_notices_the_person_hears_even_with_nothing_to_tell(modules, declare):
    """So the shell asks the device's permission only where there is something to be told (hub#2046, HUB_APP-F07)."""
    declare("stock.item.changes", {"rows": []})
    modules(
        module("stock", permissions=["stock.view"], notices=[notice(), notice("secret", permission="stock.view")]),
        module("sale", notices=[notice(operation="stock.item.changes")]),
        on=["stock"],
    )

    answer = get("base.notice.list")(ctx(), NoticeListIn()).model_dump(mode="json")

    assert answer == {"notices": [], "sources": ["stock.added"]}
    assert get("base.notice.list")(ctx("stock.view"), NoticeListIn()).model_dump(mode="json")["sources"] == [
        "stock.added",
        "stock.secret",
    ]
