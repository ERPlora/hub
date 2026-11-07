"""The Home's rules (PLAN-HUB round 2026-10-21), as the old hub's ``setup_status.rs`` had them.

The cases are those of its tests (``crates/runtime/src/setup_status.rs`` at ``9dd38215``): which row a step reads,
when a condition passes, which countries a step applies to, its level and the counters of the document.
"""

from types import SimpleNamespace

import pytest
from django.utils.translation import override
from live.meta import BellCounter, SetupCheck

from base import home

# --- The row a step reads -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "row"),
    [
        ({"rows": [{"a": 1}, {"a": 2}], "total": 2}, {"a": 1}),
        ({"items": [{"b": 1}]}, {"b": 1}),
        ({"rows": [], "total": 0}, None),
        ({"items": []}, None),
        ({"count": 3}, {"count": 3}),  # a single object is its own row (``*.status``, ``count_to_confirm``)
        ({"configured": False, "series": 0}, {"configured": False, "series": 0}),
    ],
)
def test_the_first_row_of_a_result(result, row):
    assert home.first_row(result) == row


# --- Conditions (``configured_when``) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        (True, True),
        (False, False),
        (0, False),
        (0.0, False),
        (3, True),
        (-1, True),
        ("", False),
        ("   ", False),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        (" x ", True),
        ([], False),
        ([0], True),
        ({}, True),  # an object is truthy, as in the old hub
    ],
)
def test_truthy_is_the_old_hubs(value, expected):
    assert home.truthy(value) is expected


@pytest.mark.parametrize(
    ("value", "text"),
    [("ready", "ready"), (None, ""), (True, "true"), (False, "false"), (3, "3"), (1.5, "1.5")],
)
def test_as_text_compares_laxly(value, text):
    assert home.as_text(value) == text


@pytest.mark.parametrize(
    ("row", "check", "passes"),
    [
        ({"active": 2}, SetupCheck(field="active", truthy=True), True),
        ({"active": 0}, SetupCheck(field="active", truthy=True), False),
        ({"active": 0}, SetupCheck(field="active", truthy=False), True),
        ({}, SetupCheck(field="active", truthy=False), True),  # a missing field is null
        ({}, SetupCheck(field="active", truthy=True), False),
        ({"state": "ready"}, SetupCheck(field="state", equals="ready"), True),
        ({"state": "draft"}, SetupCheck(field="state", equals="ready"), False),
        ({"series": 2}, SetupCheck(field="series", equals="2"), True),  # compared as text
        ({"series": 2}, SetupCheck(field="series", equals=2), True),
        ({"on": True}, SetupCheck(field="on", equals=True), True),
        ({"on": False}, SetupCheck(field="on", equals=True), False),
        ({"on": 0}, SetupCheck(field="on", equals=0), True),
        ({"active": 2}, SetupCheck(field="active"), False),  # a half-written condition never passes
    ],
)
def test_a_condition_on_the_first_row(row, check, passes):
    assert home.passes(row, check) is passes


def test_configured_needs_a_row_and_every_condition():
    checks = [SetupCheck(field="a", truthy=True), SetupCheck(field="b", equals="x")]

    assert home.is_configured({"a": 1, "b": "x"}, checks) is True
    assert home.is_configured({"a": 1, "b": "y"}, checks) is False
    assert home.is_configured(None, checks) is False
    assert home.is_configured({"anything": 0}, []) is True  # no conditions: having a row is enough
    assert home.is_configured(None, []) is False


# --- Countries ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("countries", "hub_country", "applies"),
    [
        ([], "ES", True),
        ([], "", True),
        (["ES"], "ES", True),
        (["es"], "ES", True),
        ([" ES "], "es", True),
        (["ES", "PT"], "PT", True),
        (["ES"], "FR", False),
        # hub#682: a hub without a country (a demo, ERPlora's own) is in ERPlora's market, Spain
        (["ES"], "", True),
        (["es"], "", True),
        (["PT"], "", False),
    ],
)
def test_a_step_applies_to_its_countries(countries, hub_country, applies):
    assert home.applies_to_country(countries, hub_country) is applies


# --- Level ------------------------------------------------------------------------------------------------


def test_only_bases_list_is_legal():
    assert home.LEGAL_STEPS == frozenset({"invoice.business_identity"})
    assert home.level_of("invoice.business_identity", required=False) == home.LEVEL_LEGAL
    assert home.level_of("invoice.business_identity", required=True) == home.LEVEL_LEGAL
    assert home.level_of("invoice.numbering", required=True) == home.LEVEL_FUNCTIONAL
    assert home.level_of("printing.printer", required=False) == home.LEVEL_RECOMMENDED


# --- The document ---------------------------------------------------------------------------------------


def item(key, state, level=home.LEVEL_FUNCTIONAL, order=500):
    return {"key": key, "state": state, "level": level, "order": order}


def test_the_document_orders_by_order_then_key_and_counts():
    items = [
        item("team", home.STATE_PENDING, home.LEVEL_RECOMMENDED, 80),
        item("b.x", home.STATE_DONE),
        item("invoice.business_identity", home.STATE_PENDING, home.LEVEL_LEGAL, 40),
        item("a.x", home.STATE_PENDING),
        item("apps", home.STATE_UNAVAILABLE, order=10),
        item("invoice.done", home.STATE_DONE, home.LEVEL_LEGAL, 40),
    ]

    document = home.document(items)

    assert [entry["key"] for entry in document["items"]] == [
        "apps",
        "invoice.business_identity",
        "invoice.done",
        "team",
        "a.x",
        "b.x",
    ]
    assert (document["total"], document["pending"], document["unavailable"], document["blocking_pending"]) == (
        6,
        3,
        1,
        1,
    )


def test_an_empty_document():
    assert home.document([]) == {"total": 0, "pending": 0, "unavailable": 0, "blocking_pending": 0, "items": []}


# --- Which modules bring their hooks --------------------------------------------------------------------


def config(label, listed=True):
    return SimpleNamespace(label=label, listed=listed)


def test_only_the_modules_on_in_the_scope_bring_their_hooks(monkeypatch, settings):
    settings.SHOW_UNLISTED_MODULES = True
    monkeypatch.setattr("base.home.module_configs", lambda: [config("sale"), config("stock"), config("demo", False)])

    assert [c.label for c in home.home_modules({"sale", "demo", "base"})] == ["sale", "demo"]


def test_a_module_out_of_the_store_brings_none_unless_the_setting_says_so(monkeypatch, settings):
    """``demo`` (``listed = False``) is the platform's reference, not a customer's app: its example step, panel and
    counter are for the tests and the e2e (``SHOW_UNLISTED_MODULES``, on with ``DEBUG``), never for a customer."""
    monkeypatch.setattr("base.home.module_configs", lambda: [config("sale"), config("demo", False)])

    settings.SHOW_UNLISTED_MODULES = False
    assert [c.label for c in home.home_modules({"sale", "demo"})] == ["sale"]
    settings.SHOW_UNLISTED_MODULES = True
    assert [c.label for c in home.home_modules({"sale", "demo"})] == ["sale", "demo"]


def test_the_setting_is_off_in_production_and_on_with_debug():
    from django.conf import settings

    from config import settings as hub_settings

    assert hub_settings.SHOW_UNLISTED_MODULES == hub_settings.DEBUG
    assert settings.SHOW_UNLISTED_MODULES is True  # the suite runs with the development settings


# --- The bell by the clock (FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE) --------------------------------------

UNSET = object()


def bell_module(refresh=UNSET, label="printing", keys=("stalled",)):
    """A module with the counters ``keys`` in its bell and, unless ``UNSET``, ``bell_refresh_every = refresh``."""
    module = SimpleNamespace(
        label=label, bell=[BellCounter(key=key, operation=f"{label}.thing.count", route="/", label="L") for key in keys]
    )
    if refresh is not UNSET:
        module.bell_refresh_every = refresh
    return module


@pytest.mark.parametrize(
    ("refresh", "errors"),
    [
        (UNSET, 0),
        ({}, 0),
        ({"stalled": home.MIN_BELL_REFRESH_SECONDS}, 0),
        ({"stalled": 60}, 0),
        (60, 1),  # not per counter
        ({"other": 60}, 1),  # no such counter in its bell
        ({"stalled": home.MIN_BELL_REFRESH_SECONDS - 1}, 1),  # every open screen a poller
        ({"stalled": True}, 1),
        ({"stalled": 60.0}, 1),
        ({"stalled": "60"}, 1),
    ],
)
def test_how_often_a_counter_is_read_again_is_checked_at_start(refresh, errors):
    found = home.bell_refresh_errors([bell_module(refresh)])
    assert len(found) == errors
    assert all(error.id == "base.E007" for error in found)


# ── What an app says its plan includes (BASE-F40: «Usage and plan» of System) ──────────────────────────────────────────


def metered(**declared):
    spec = {"operation": "demo.item.list", "used": "used", "limit": "limit", "label": "Things", **declared}
    return SimpleNamespace(label="things", plan_meter=spec)


def test_a_meter_says_what_its_app_answers(monkeypatch):
    monkeypatch.setattr(home, "run_hook", lambda ctx, operation, params: {"used": 40, "limit": 150})

    assert home.plan_meters(None, [metered()]) == [
        {"key": "things", "label": "Things", "used": 40, "limit": 150, "available": True}
    ]


def test_an_app_that_declares_no_meter_is_left_out(monkeypatch):
    monkeypatch.setattr(home, "run_hook", lambda ctx, operation, params: pytest.fail("nothing to ask"))

    assert home.plan_meters(None, [SimpleNamespace(label="things")]) == []


def test_a_meter_whose_figures_were_never_measured_says_so_never_a_zero(monkeypatch):
    monkeypatch.setattr(home, "run_hook", lambda ctx, operation, params: {"used": 0, "limit": 0, "since": None})

    assert home.plan_meters(None, [metered(measured="since")]) == [
        {"key": "things", "label": "Things", "used": None, "limit": None, "available": True}
    ]


def test_a_meter_measured_gives_its_figures_even_at_zero(monkeypatch):
    monkeypatch.setattr(home, "run_hook", lambda ctx, operation, params: {"used": 0, "limit": 0, "since": "2026-10-01"})

    assert home.plan_meters(None, [metered(measured="since")]) == [
        {"key": "things", "label": "Things", "used": 0, "limit": 0, "available": True}
    ]


def test_a_meter_that_fails_is_unavailable_and_the_others_go_on(monkeypatch, caplog):
    def fails_for_broken(ctx, operation, params):
        if operation == "broken":
            raise RuntimeError("its query failed")
        return {"used": 1, "limit": 2}

    monkeypatch.setattr(home, "run_hook", fails_for_broken)

    meters = home.plan_meters(None, [metered(operation="broken"), metered()])

    assert meters == [
        {"key": "things", "label": "Things", "used": None, "limit": None, "available": False},
        {"key": "things", "label": "Things", "used": 1, "limit": 2, "available": True},
    ]
    assert "left out" in caplog.text


def test_a_meter_says_its_label_in_the_active_language(monkeypatch):
    from django.utils.translation import gettext_lazy, override

    monkeypatch.setattr(home, "run_hook", lambda ctx, operation, params: {"used": 1, "limit": 2})

    with override("es"):
        assert home.plan_meters(None, [metered(label=gettext_lazy("Failed events"))])[0]["label"] == "Eventos caídos"


@pytest.mark.parametrize(
    ("declared", "errors"),
    [
        (None, 0),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo", "label": "X"}, 0),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo", "label": "X", "measured": "plan_slug"}, 0),
        ("base.plan.usage", 1),
        ({"operation": "nothing.at.all", "used": "known", "limit": "demo", "label": "X"}, 1),
        ({"operation": "base.plan.usage", "used": "nope", "limit": "demo", "label": "X"}, 1),
        ({"operation": "base.plan.usage", "used": "known", "limit": "nope", "label": "X"}, 1),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo", "label": "X", "measured": "nope"}, 1),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo"}, 1),
    ],
)
def test_what_an_app_declares_as_its_meter_is_checked_at_start(declared, errors):
    found = home.plan_meter_errors([SimpleNamespace(label="things", plan_meter=declared)])

    assert len(found) == errors
    assert all(error.id == "base.E013" for error in found)


def test_the_check_of_the_meters_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.all_live_app_configs", lambda: [SimpleNamespace(label="things", plan_meter="nope")])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E013"] == ["base.E013"]


def test_the_check_of_the_bells_clock_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.all_live_app_configs", lambda: [bell_module({"other": 60})])
    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E007"] == ["base.E007"]


# ── The cards an app puts in System (hub#683: the old hub's «Your printer» in Resources) ─────────────────────────────


def carded(*cards, permissions=("things.view",), path="/nowhere"):
    return SimpleNamespace(label="things", path=path, permissions=list(permissions), system_cards=list(cards))


def person(*permissions):
    from live.context import OperationContext, Scope

    return OperationContext(scope=Scope("host", "a"), actor="ana", permissions=frozenset(permissions), language="en")


def test_a_card_is_its_apps_component_named_by_the_app():
    card = {"key": "printer", "component": "ThingsCard"}

    assert home.system_cards(person(), [carded(card)]) == [
        {"key": "things.printer", "app": "things", "component": "ThingsCard"}
    ]


def test_an_app_that_declares_no_card_brings_none():
    assert home.system_cards(person(), [SimpleNamespace(label="things")]) == []


def test_a_card_with_a_permission_only_for_whoever_has_it_in_the_order_declared():
    first = {"key": "printer", "component": "ThingsCard", "permission": "things.view"}
    second = {"key": "drawer", "component": "DrawerCard"}

    assert [card["key"] for card in home.system_cards(person(), [carded(first, second)])] == ["things.drawer"]
    assert [card["key"] for card in home.system_cards(person("things.view"), [carded(first, second)])] == [
        "things.printer",
        "things.drawer",
    ]


@pytest.fixture
def components(tmp_path):
    """An app's folder with ``frontend/components/ThingsCard.vue``."""
    folder = tmp_path / "frontend" / "components"
    folder.mkdir(parents=True)
    (folder / "ThingsCard.vue").write_text("<template><p /></template>\n")
    return tmp_path


@pytest.mark.parametrize(
    ("cards", "errors"),
    [
        (None, 0),
        ([], 0),
        ([{"key": "printer", "component": "ThingsCard"}], 0),
        ([{"key": "printer", "component": "ThingsCard", "permission": "things.view"}], 0),
        ({"key": "printer", "component": "ThingsCard"}, 1),  # one card, not a list of them
        (["ThingsCard"], 1),
        ([{"component": "ThingsCard"}], 1),  # no key
        ([{"key": "", "component": "ThingsCard"}], 1),
        ([{"key": "printer"}], 1),  # no component
        ([{"key": "printer", "component": "MissingCard"}], 1),  # no such file: the card would never mount
        ([{"key": "printer", "component": "../ThingsCard"}], 1),  # a name, never a path
        ([{"key": "printer", "component": "../components/ThingsCard"}], 1),  # a file, but the SPA would never mount it
        ([{"key": "printer", "component": "ThingsCard", "permission": "other.view"}], 1),  # not the app's
        ([{"key": "printer", "component": "ThingsCard", "permision": "things.view"}], 1),  # a field misspelt
        ([{"key": "printer", "component": "ThingsCard"}, {"key": "printer", "component": "ThingsCard"}], 1),
    ],
)
def test_what_an_app_declares_as_its_cards_is_checked_at_start(components, cards, errors):
    declared = SimpleNamespace(label="things", path=str(components), permissions=["things.view"])
    if cards is not None:
        declared.system_cards = cards

    found = home.system_card_errors([declared])

    assert len(found) == errors
    assert all(error.id == "base.E015" for error in found)


def test_the_check_of_the_cards_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.all_live_app_configs", lambda: [carded({"key": "printer"})])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E015"] == ["base.E015"]


# ── The apps a business must have on in its country (hub#997, PLAN-HUB round 2026-11-07) ───────────────────────────


def obliged(label="fiscal", countries=("PT",), platform_turns_on=False, **more):
    """A stand-in app that declares where it is mandatory, as tax and verifactu do; base never names a real one. Its
    store icon is not the shell's: the shell paints an app with its first menu entry's."""
    from live.meta import Nav

    declared = {"countries": countries if countries == "all" else list(countries), "platform_turns_on": platform_turns_on}
    more.setdefault("navigation", [Nav("records", "Records", "ion:list-outline", f"/{label}/records")])
    return SimpleNamespace(label=label, verbose_name=label.capitalize(), icon="ion:calculator-outline", mandatory=declared, **more)


@pytest.mark.parametrize(
    ("countries", "hub_country", "mandatory"),
    [
        ("all", "PT", True),
        ("all", "JP", True),
        ("all", "", True),
        (["PT"], "PT", True),
        (["pt"], "PT", True),
        (["PT", "ES"], "ES", True),
        (["PT"], "FR", False),
        ([], "PT", False),  # a slip the check refuses (base.E016) never reads as «every country»
        # A business without a country (a demo, ERPlora's own) is in ERPlora's market, Spain (hub#682).
        (["ES"], "", True),
        (["PT"], "", False),
    ],
)
def test_an_app_is_mandatory_in_the_countries_it_declares(countries, hub_country, mandatory):
    assert home.mandatory_in(obliged(countries=countries), hub_country) is mandatory


def test_an_app_that_declares_nothing_is_mandatory_nowhere():
    assert home.mandatory_in(SimpleNamespace(label="things"), "ES") is False


def test_a_mandatory_app_off_is_a_step_of_the_platform_to_turn_it_on():
    with override("en"):
        steps = home.mandatory_steps([obliged()], on=frozenset(), hub_country="PT")

    assert steps == [
        {
            "key": "base.mandatory.fiscal",
            "app": "base",
            "state": "pending",
            "required": True,
            "level": "functional",
            "actionable": True,
            "title": "Turn on Fiscal",
            "description": "It is mandatory for businesses in Portugal.",
            "icon": "ion:list-outline",
            "route": "/apps#all",
            "order": 15,
        }
    ]


def test_the_step_says_the_app_and_the_country_in_the_persons_language():
    from django.utils.translation import gettext_lazy

    app = obliged(countries=["ES"])
    app.verbose_name = gettext_lazy("Taxes")

    with override("es"):
        (step,) = home.mandatory_steps([app], on=frozenset(), hub_country="")

    assert (step["title"], step["description"]) == ("Activa Impuestos", "Es obligatoria para los negocios de España.")


def test_the_step_goes_once_the_app_is_on_and_never_comes_for_another_country():
    apps = [obliged("fiscal", ["PT"]), obliged("ledger", "all"), obliged("seal", ["FR"]), SimpleNamespace(label="things")]

    assert [step["key"] for step in home.mandatory_steps(apps, on=frozenset(), hub_country="PT")] == [
        "base.mandatory.fiscal",
        "base.mandatory.ledger",
    ]
    assert [step["key"] for step in home.mandatory_steps(apps, on=frozenset({"fiscal"}), hub_country="PT")] == [
        "base.mandatory.ledger"
    ]
    assert home.mandatory_steps(apps, on=frozenset({"fiscal", "ledger"}), hub_country="PT") == []


def test_the_step_has_the_icon_the_shell_paints_for_the_app_never_its_store_one():
    """The store's icon is baked apart, and HubIcon refuses a name the shell has not registered: the step paints the
    app as «My apps» and the launcher do, by its first menu entry, or the shell's own for an app without a menu."""
    assert home.mandatory_steps([obliged()], on=frozenset(), hub_country="PT")[0]["icon"] == "ion:list-outline"
    assert home.mandatory_steps([obliged(navigation=[])], on=frozenset(), hub_country="PT")[0]["icon"] == "ion:apps-outline"


@pytest.mark.parametrize(
    ("declared", "errors"),
    [
        (None, 0),
        ({"countries": "all", "platform_turns_on": True}, 0),
        ({"countries": ["ES"], "platform_turns_on": False}, 0),
        ({"countries": ("ES", "PT"), "platform_turns_on": False}, 0),
        (["ES"], 1),  # the countries alone, not what the platform may do
        ({"countries": [], "platform_turns_on": False}, 1),  # mandatory nowhere: an empty list must not read as «all»
        ({"countries": "ES", "platform_turns_on": False}, 1),  # a code, not a list of them
        ({"countries": ["Spain"], "platform_turns_on": False}, 1),  # ISO 3166-1 alpha-2, never a name
        ({"countries": ["es"], "platform_turns_on": False}, 1),  # upper-case, as the business's country comes
        ({"countries": ["ES", "ES"], "platform_turns_on": False}, 1),
        ({"countries": "all"}, 1),  # it must say whether the platform turns it on by itself
        ({"countries": "all", "platform_turns_on": "yes"}, 1),
        ({"countries": "all", "platform_turns_on": True, "verticals": ["restaurant"]}, 1),  # a field misspelt or not ours
    ],
)
def test_what_an_app_declares_as_mandatory_is_checked_at_start(declared, errors):
    app = SimpleNamespace(label="things")
    if declared is not None:
        app.mandatory = declared

    found = home.mandatory_errors([app])

    assert len(found) == errors
    assert all(error.id == "base.E016" for error in found)


def test_the_check_of_the_mandatory_apps_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.all_live_app_configs", lambda: [SimpleNamespace(label="things", mandatory=["ES"])])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E016"] == ["base.E016"]


def test_base_names_no_app_where_it_reads_the_mandatory_ones():
    """Modularity (hub#997): which apps are mandatory, and where, only their own ``LiveAppConfig`` says. No literal of the
    code that reads it names an app, nor one of its operations or steps (``"verifactu"``, ``"tax.rules"``)."""
    import ast
    import inspect

    from live.meta import module_configs
    from live.operations import get

    from base import queries

    labels = {config.label for config in module_configs()}
    readers = [
        home.mandatory_in,
        home.mandatory_steps,
        home.mandatory_problems,
        home.mandatory_errors,
        get("base.setup.status").fn,
        queries._platform_steps,
    ]
    named = sorted(
        node.value
        for reader in readers
        for node in ast.walk(ast.parse(inspect.getsource(inspect.unwrap(reader)).lstrip()))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (node.value in labels or node.value.split(".")[0] in labels)
    )
    assert labels and named == []
