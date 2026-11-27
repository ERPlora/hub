"""The Home's live queries ``base.setup.status`` and ``base.widget.list``, and System's ``base.system.cards``; the bell
and the device's notices are in ``test_queries_home_bell.py`` and ``test_queries_home_notices.py``.

Each module declares its steps, panels and counters in its ``LiveAppConfig`` and base runs
their queries by name, as the person of the request, with the old hub's rules (``setup_status.rs``): only modules on
in the scope, the hub's country, the person's permission (but a pending ⛔ stays, not actionable), a step whose query
fails is left out. The stand-in modules here name real operations registered for the test.
"""

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from django.conf import settings
from django.utils.translation import gettext_lazy
from live.assistant import description
from live.context import OperationContext, system_context
from live.errors import NotFound
from live.live_registry import live_registry
from live.meta import Nav, SetupCheck, SetupStep, Widget
from live.operations import Operation, get, registry
from live.outbox import channel_for
from live.models import OutboxEvent
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict, Field

from apps.demo.models import Item
from apps.demo.schemas import ItemIn
from base.models import Hub, Membership
from base.sensitive import COSTS, VIEW_COSTS
from base.schemas.home import (
    NoticeListIn,
    NoticeListOut,
    SetupStatusIn,
    SetupStatusOut,
    SystemCardsIn,
    SystemCardsOut,
    WidgetListIn,
    WidgetListOut,
)
from base.schemas.bell import BellCountersIn, BellCountersOut
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a

__all__ = ["in_business_a"]
pytestmark = HUB_DB
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
        monkeypatch.setattr("base.home.shown_modules.module_configs", lambda: list(configs))
        monkeypatch.setattr("base.activation.module_configs", lambda: list(configs))
        monkeypatch.setattr("base.queries.home.active_apps", lambda scope: frozenset(labels | {"base"}))

    use()
    return use


def module(label, *, setup=(), widgets=(), bell=(), notices=(), listed=True, permissions=(), name=None, **more):
    return SimpleNamespace(
        label=label,
        verbose_name=name or label.capitalize(),
        listed=listed,
        setup=list(setup),
        widgets=list(widgets),
        bell=list(bell),
        notices=list(notices),
        permissions=dict.fromkeys(permissions, "A phrase"),
        **more,
    )


def ctx(*permissions, scope=A, actor="ana", language="en"):
    return OperationContext(scope=scope, actor=actor, permissions=frozenset({HOME, *permissions}), language=language)


def setup_status(context):
    return get("base.setup.status")(context, SetupStatusIn()).model_dump(mode="json")


def in_b(read, context):
    with use_hub(Hub.objects.get(slug=B.key)):
        return read(context)


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
        ("base.system.cards", SystemCardsIn, SystemCardsOut),
    ],
)
def test_declarations(name, input, output):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == ("query", HOME, input, output)


def test_the_assistant_reads_the_setup_status():
    """The assistant gets the same document as a tool; it never takes on a step «not available»."""
    assert "not available" in description(get("base.setup.status"))


# --- base.setup.status: the platform's steps (base.apps, base.team) ----------------------------------------


def test_the_platforms_steps_for_an_administrator(modules, make_user):
    modules(module("sale"))
    make_user("ana", host=A.key, role=Membership.Role.OWNER)

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


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_list_comes_with_its_title_as_the_home_shows_it_in_the_language_of_who_asks(modules, language):
    """The assistant names the list by this title, never by English words of its tool's description in a Spanish chat."""
    catalogue = json.loads((Path(settings.BASE_DIR) / f"base/frontend/locale/{language}.json").read_text(encoding="utf-8"))
    assert setup_status(ctx(language=language))["title"] == catalogue["base"]["setup"]["title"]


def test_your_apps_is_pending_without_an_app_on_and_unavailable_when_none_can_be(modules):
    modules(module("sale"), module("stock"), on=[])
    assert by_key(setup_status(ctx(ADMIN)))["base.apps"]["state"] == "pending"

    modules(module("demo", listed=False))  # the reference app is no business app
    document = setup_status(ctx(ADMIN))
    assert by_key(document)["base.apps"]["state"] == "unavailable"
    assert document["unavailable"] == 1


def test_your_team_is_done_with_two_active_people_in_this_hub(modules, make_user):
    modules(module("sale"))
    make_user("ana", host=A.key, role=Membership.Role.OWNER)
    make_user("bea", host=B.key)  # another hub's
    make_user("cris", host=A.key, is_active=False)
    assert by_key(setup_status(ctx(ADMIN)))["base.team"]["state"] == "pending"

    make_user("dani", host=A.key)
    assert by_key(setup_status(ctx(ADMIN)))["base.team"]["state"] == "done"


def test_whoever_cannot_administer_the_hub_gets_no_platform_step(modules):
    modules(module("sale"))
    assert setup_status(ctx()) == {
        "title": "Finish setting up your business",
        "total": 0,
        "pending": 0,
        "unavailable": 0,
        "blocking_pending": 0,
        "items": [],
    }


# --- base.setup.status: the apps a business must have on in its country (hub#997) -----------------------------------


def fiscal(countries=("ES",), turns_on=False, **more):
    """A stand-in app mandatory in ``countries`` (or ``"all"``), declared as its ``LiveAppConfig`` would."""
    declared = {"countries": countries if countries == "all" else list(countries), "platform_turns_on": turns_on}
    navigation = [Nav("records", "Records", "ion:list-outline", "/fiscal/records")]
    return module("fiscal", mandatory=declared, icon="ion:calculator-outline", navigation=navigation, **more)


def test_an_app_the_platform_turns_on_by_itself_is_not_one_of_your_apps_in_its_country(modules, hub_b):
    """A business is born with it on (hub#997): with it alone its till has nothing to sell, so «Your apps» still asks for
    one. In a country where the platform does not turn it on, the business chose it: it counts."""
    modules(module("sale"), fiscal(("PT",), turns_on=True), on=["fiscal"])
    Hub.objects.filter(slug=A.key).update(country="PT")
    assert by_key(setup_status(ctx(ADMIN)))["base.apps"]["state"] == "pending"
    # B has no country: Spain, where it is no app the platform turns on.
    assert by_key(in_b(setup_status, ctx(ADMIN, scope=B)))["base.apps"]["state"] == "done"

    modules(module("sale"), fiscal(("PT",), turns_on=True), on=["fiscal", "sale"])
    assert by_key(setup_status(ctx(ADMIN)))["base.apps"]["state"] == "done"


def test_a_mandatory_app_off_in_the_businesss_country_is_an_important_step_until_it_is_on(modules, make_user):
    make_user("ana", host=A.key, role=Membership.Role.OWNER)
    modules(module("sale"), fiscal(), on=["sale"])

    document = setup_status(ctx(ADMIN))

    assert keys(document) == ["base.apps", "base.mandatory.fiscal", "base.team"]
    step = by_key(document)["base.mandatory.fiscal"]
    assert {k: step[k] for k in ("app", "state", "level", "required", "actionable", "route", "icon", "title")} == {
        "app": "base",
        "state": "pending",
        "level": "functional",
        "required": True,
        "actionable": True,
        "route": "/apps#all",
        "icon": "ion:list-outline",
        "title": "Turn on Fiscal",
    }
    assert (document["pending"], document["blocking_pending"]) == (2, 0)

    modules(module("sale"), fiscal(), on=["sale", "fiscal"])
    assert "base.mandatory.fiscal" not in keys(setup_status(ctx(ADMIN)))


def test_a_mandatory_app_is_asked_for_only_in_its_countries_each_hub_by_its_own(modules, hub_b):
    modules(module("sale"), fiscal(), on=["sale"])
    Hub.objects.filter(slug=A.key).update(country="PL")

    assert "base.mandatory.fiscal" not in keys(setup_status(ctx(ADMIN)))
    # B has no country: it is in ERPlora's market, Spain (hub#682).
    assert "base.mandatory.fiscal" in keys(in_b(setup_status, ctx(ADMIN, scope=B)))

    modules(module("sale"), fiscal("all"), on=["sale"])
    assert "base.mandatory.fiscal" in keys(setup_status(ctx(ADMIN)))


def test_a_mandatory_app_says_it_in_the_persons_language(modules):
    modules(module("sale"), fiscal(name=gettext_lazy("Taxes")), on=["sale"])
    Hub.objects.filter(slug=A.key).update(country="FR")
    modules(module("sale"), fiscal("all", name=gettext_lazy("Taxes")), on=["sale"])

    step = by_key(setup_status(ctx(ADMIN, language="es")))["base.mandatory.fiscal"]

    assert (step["title"], step["description"]) == ("Activa Impuestos", "Es obligatoria para los negocios de Francia.")


def test_only_whoever_turns_apps_on_is_asked_to_turn_a_mandatory_one_on(modules):
    modules(module("sale"), fiscal(), on=["sale"])

    assert keys(setup_status(ctx())) == []


def test_an_app_out_of_the_store_is_never_asked_for_on_a_customers_hub(modules, settings):
    modules(module("sale"), fiscal(listed=False), on=["sale"])
    settings.SHOW_UNLISTED_MODULES = False

    assert "base.mandatory.fiscal" not in keys(setup_status(ctx(ADMIN)))


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
    """The person at the till cannot set the business details up, yet they are what stops the invoice."""
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


# --- VeriFactu's way to the AEAT: a wall only where the hub files in production ------------------------------------

ROUTE = "verifactu.sending_route"


def sending_route(modules, declare, *, environment, ready, permission=None):
    """VeriFactu's step as base sees it, its query answering the hub's environment and whether its way is ready."""
    declare(
        "verifactu.config.get",
        {"environment": environment, "route_ready_for_production": ready},
        permission=permission,
    )
    route = step("sending_route", "verifactu.config.get", permission="verifactu.configure", required=True,
                 configured_when=[SetupCheck(field="route_ready_for_production", truthy=True)])
    modules(module("verifactu", setup=[route], permissions=["verifactu.view_record", "verifactu.configure"]))


def seen(document, key=ROUTE):
    item = by_key(document)[key]
    return item["level"], item["state"], item["actionable"]


def test_in_production_a_way_to_the_aeat_not_ready_is_a_wall_for_everybody(modules, declare):
    """A hub in production whose way broke (authorisation revoked, certificate expired or removed) has every sale
    refused: its step is ⛔, counted by the strip, and told to the person at the till too, not actionable."""
    sending_route(modules, declare, environment="production", ready=False)

    owner, employee = setup_status(ctx("verifactu.configure")), setup_status(ctx())

    assert (seen(owner), owner["blocking_pending"]) == (("legal", "pending", True), 1)
    assert (seen(employee), employee["blocking_pending"]) == (("legal", "pending", False), 1)


def test_in_testing_the_way_stays_functional_and_the_till_sells(modules, declare):
    """A hub in testing sells without a way to the AEAT, so nothing tells it that it cannot invoice."""
    sending_route(modules, declare, environment="testing", ready=False)

    owner = setup_status(ctx("verifactu.configure"))

    assert (seen(owner), owner["blocking_pending"]) == (("functional", "pending", True), 0)
    assert keys(setup_status(ctx())) == []  # a functional step goes to whoever can do it


def test_in_production_with_the_way_ready_the_step_is_done_and_off_the_strip(modules, declare):
    sending_route(modules, declare, environment="production", ready=True)

    owner = setup_status(ctx("verifactu.configure"))

    assert (by_key(owner)[ROUTE]["state"], owner["blocking_pending"]) == ("done", 0)
    assert keys(setup_status(ctx())) == []  # done: not the till's task


def test_whoever_may_not_read_the_way_still_has_its_wall_in_production(modules, declare, caplog):
    """A wall whose query the person may not run is read as the system, never dropped. Outside it the
    step is as any functional one: whoever may not read its query is not told, and the failure is logged."""
    sending_route(modules, declare, environment="production", ready=False, permission="verifactu.view_record")

    document = setup_status(ctx())

    assert (seen(document), document["blocking_pending"]) == (("legal", "pending", False), 1)

    sending_route(modules, declare, environment="testing", ready=False, permission="verifactu.view_record")
    with caplog.at_level(logging.WARNING, logger="base.home"):
        document = setup_status(ctx("verifactu.configure"))  # may configure it, may not read it

    assert (keys(document), document["blocking_pending"]) == ([], 0)
    assert f"{ROUTE} left out" in caplog.text
    assert "PermissionDenied" in caplog.text  # the denial's own traceback, never «NoneType: None»


def test_in_testing_whoever_may_neither_do_nor_read_the_way_is_skipped_without_a_warning(modules, declare, caplog):
    """No wall in testing: the person at the till is not told about the step, and that is no failure of its query,
    so no Home of theirs logs one."""
    sending_route(modules, declare, environment="testing", ready=False, permission="verifactu.view_record")

    with caplog.at_level(logging.WARNING, logger="base.home"):
        document = setup_status(ctx())  # an employee: may neither configure it nor read it

    assert (keys(document), document["blocking_pending"]) == ([], 0)
    assert [record.getMessage() for record in caplog.records if record.name == "base.home"] == []


def test_only_base_names_the_steps_that_are_walls_in_production(modules, declare):
    """The level is base's: a module's step whose row says production is no wall unless base lists it."""
    declare("stock.catalog.status", {"environment": "production", "n": 0})
    modules(module("stock", setup=[step(required=True, configured_when=[SetupCheck(field="n", truthy=True)])]))

    document = setup_status(ctx())

    assert (seen(document, "stock.catalog"), document["blocking_pending"]) == (("functional", "pending", True), 0)


def test_a_national_step_shows_only_in_a_hub_of_its_country(modules, declare, hub_b):
    declare("stock.catalog.status", {"n": 1})
    modules(module("stock", setup=[step(countries=["PT"])]))
    assert keys(setup_status(ctx())) == []  # the hub has no country: it is in ERPlora's market, Spain

    Hub.objects.filter(slug=A.key).update(country="PT")
    assert keys(setup_status(ctx())) == ["stock.catalog"]
    assert keys(in_b(setup_status, ctx(scope=B))) == []


def test_a_step_for_spain_shows_in_a_hub_without_a_country_and_not_in_another_country(modules, declare, hub_b):
    """hub#682: a hub without a country (a demo, ERPlora's own) is in ERPlora's market, Spain, as VeriFactu counts it."""
    declare("stock.catalog.status", {"n": 1})
    modules(module("stock", setup=[step(countries=["ES"])]))
    assert keys(setup_status(ctx())) == ["stock.catalog"]

    Hub.objects.filter(slug=A.key).update(country="PL")
    assert keys(setup_status(ctx())) == []
    assert keys(in_b(setup_status, ctx(scope=B))) == ["stock.catalog"]  # B has no country

    Hub.objects.filter(slug=A.key).update(country="ES")
    assert keys(setup_status(ctx())) == ["stock.catalog"]


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
    Hub.objects.filter(slug=A.key).update(is_demo=True)
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


def test_the_texts_of_a_panels_options_are_in_the_persons_language(modules):
    # A panel's literal props may carry lazy translations (the text under the figure of a stat, or deeper in a list or
    # a dict); the list gives them in the reader's language and every other prop as declared.
    options = {
        "format": "number",
        "label": gettext_lazy("Contingency queue"),
        "decimals": 0,
        "compact": False,
        "legend": [gettext_lazy("Failed events"), 3],
        "hint": {"text": gettext_lazy("Your team"), "on": True},
    }
    modules(
        module(
            "stock",
            widgets=[
                Widget(key="queue", title=gettext_lazy("Contingency queue"), kind="stat",
                       operation="stock.item.count", options=options),
            ],
        )
    )

    [spanish] = widget_list(ctx(language="es"))
    assert spanish["title"] == "Cola de contingencia"
    assert spanish["options"] == {
        "format": "number",
        "label": "Cola de contingencia",
        "decimals": 0,
        "compact": False,
        "legend": ["Eventos caídos", 3],
        "hint": {"text": "Tu equipo", "on": True},
    }
    [english] = widget_list(ctx())
    assert english["options"] == {
        "format": "number",
        "label": "Contingency queue",
        "decimals": 0,
        "compact": False,
        "legend": ["Failed events", 3],
        "hint": {"text": "Your team", "on": True},
    }


def test_a_panel_says_whether_its_operation_is_a_live_query(modules, monkeypatch):
    # The Home follows a live query and asks once for one that is not.
    from live.live_registry import live_registry

    modules(module("stock", widgets=[Widget(key="today", title="Today", kind="kpi", operation="stock.item.count"),
                                     Widget(key="chart", title="Chart", component="StockChart")]))
    monkeypatch.setitem(live_registry.subscribable, "stock.item.count", ["stock.item.created"])
    assert [(w["key"], w["live"]) for w in widget_list(ctx())] == [("stock.today", True), ("stock.chart", False)]


def test_a_panel_of_some_verticals_shows_only_in_a_hub_of_one_of_them(modules):
    modules(module("stock", widgets=[Widget(key="tables", title="Tables", component="Tables", verticals=["restaurant"])]))
    assert widget_list(ctx()) == []

    Hub.objects.filter(slug=A.key).update(vertical="restaurant")
    assert [w["key"] for w in widget_list(ctx())] == ["stock.tables"]


class StockFiguresOut(BaseModel):
    stock_value: float | None = Field(None, json_schema_extra=COSTS)
    products_in_stock: int = 0


def test_a_panel_whose_figure_is_a_cost_is_not_on_the_list_of_who_does_not_see_costs(modules, monkeypatch):
    # The same figures read by two panels: the stock's value at cost needs «view costs»; its count of products, nothing.
    monkeypatch.setitem(
        registry,
        "stock.figures.get",
        Operation(name="stock.figures.get", kind="query", permission=None, input=AnyIn, output=StockFiguresOut,
                  expose_api=False, ai=None, fn=lambda ctx, data: {}),
    )
    modules(module("stock", widgets=[
        Widget(key="value", title="Stock value", kind="kpi", operation="stock.figures.get", map={"value": "stock_value"}),
        Widget(key="count", title="In stock", kind="stat", operation="stock.figures.get",
               map={"value": "products_in_stock"}),
    ]))

    assert [w["key"] for w in widget_list(ctx())] == ["stock.count"]
    assert [w["key"] for w in widget_list(ctx(VIEW_COSTS))] == ["stock.value", "stock.count"]


def test_panels_of_a_module_off_or_out_of_the_store(modules, settings):
    panel = Widget(key="w", title="W", component="W")
    modules(module("stock", widgets=[panel]), module("demo", widgets=[panel], listed=False), on=["demo"])
    assert [w["key"] for w in widget_list(ctx())] == ["demo.w"]

    settings.SHOW_UNLISTED_MODULES = False
    assert widget_list(ctx()) == []

    Hub.objects.filter(slug=A.key).update(is_demo=True)
    assert [w["key"] for w in widget_list(ctx())] == ["demo.w"]


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


@HUB_DB_COMMITTED
def test_a_demo_item_written_in_b_notifies_b_only_and_re_runs_the_home_there(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        get("demo.item.create")(system_context(B), ItemIn(name="In B"))
        assert list(OutboxEvent.objects.values_list("scope_kind", "scope_key")) == [(B.kind, B.key)]
    assert not OutboxEvent.objects.exists()  # business A's own database

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["demo.item.created"]})]
    assert received(on_a, timeout=0.3) == []
    assert {"base.setup.status", "base.bell.counters"} <= live_registry.affected(["demo.item.created"])


# --- base.system.cards (hub#683: the cards the apps on put in System › «Usage and plan») --------------------------


def system_cards(context):
    return get("base.system.cards")(context, SystemCardsIn()).model_dump(mode="json")["cards"]


PRINTER = {"key": "printer", "component": "SystemPrinterCard", "permission": "stock.view"}


def test_the_cards_of_the_apps_on_that_the_person_may_see(modules):
    modules(module("stock", system_cards=[PRINTER, {"key": "drawer", "component": "DrawerCard"}]), module("sale"))

    assert system_cards(ctx()) == [{"key": "stock.drawer", "app": "stock", "component": "DrawerCard"}]
    assert system_cards(ctx("stock.view")) == [
        {"key": "stock.printer", "app": "stock", "component": "SystemPrinterCard"},
        {"key": "stock.drawer", "app": "stock", "component": "DrawerCard"},
    ]


def test_an_app_off_puts_no_card(modules):
    modules(module("stock", system_cards=[PRINTER]), on=[])

    assert system_cards(ctx("stock.view")) == []


def test_each_business_sees_the_cards_of_its_own_apps(modules, monkeypatch, hub_b):
    modules(module("stock", system_cards=[PRINTER]))
    monkeypatch.setattr("base.queries.home.active_apps", lambda scope: frozenset({"base", "stock"} if scope.key == A.key else {"base"}))

    assert [card["key"] for card in system_cards(ctx("stock.view", scope=A))] == ["stock.printer"]
    assert in_b(system_cards, ctx("stock.view", scope=B)) == []


def test_a_module_out_of_the_store_puts_its_card_only_where_it_shows(modules, settings):
    modules(module("demo", system_cards=[{"key": "w", "component": "W"}], listed=False))
    assert [card["key"] for card in system_cards(ctx())] == ["demo.w"]

    settings.SHOW_UNLISTED_MODULES = False
    assert system_cards(ctx()) == []


def test_the_cards_follow_an_app_turned_on_or_off():
    from base.events import APP_EVENTS, HUB_STATE_APPLIED

    assert {HUB_STATE_APPLIED, *APP_EVENTS} <= set(live_registry.subscribable["base.system.cards"])
