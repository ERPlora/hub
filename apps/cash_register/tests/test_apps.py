"""The cash register app declares its module metadata, its menu, its permissions, what each role gets,
its scheduled task (the daily auto-close the phase-2 worker runs) and its hooks of the Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import (
    Category,
    LiveAppConfig,
    Nav,
    SetupCheck,
    SetupStep,
    Widget,
    module_configs,
    permissions_for_role,
)
from live.operations import registry

from apps.cash_register import events as E
from base import home

PERMISSIONS = [
    "cash_register.view_session",
    "cash_register.add_session",
    "cash_register.close_session",
    "cash_register.view_movement",
    "cash_register.add_movement",
    "cash_register.view_count",
    "cash_register.add_count",
    "cash_register.view_expected_totals",
    "cash_register.manage_settings",
]
TILL = [
    "cash_register.view_session",
    "cash_register.add_session",
    "cash_register.close_session",
    "cash_register.view_movement",
    "cash_register.add_movement",
    "cash_register.view_count",
    "cash_register.add_count",
]


def config():
    return apps.get_app_config("cash_register")


def test_it_is_an_installed_live_app():
    assert isinstance(config(), LiveAppConfig)
    assert config().name == "apps.cash_register"
    assert "apps.cash_register" in settings.INSTALLED_APPS


def test_it_requires_sale_only():
    # The drawer reads sale's charges, voids and refunds (foreign keys and its models); who opens or
    # closes is the context's actor, as in sale, so Staff is no requirement.
    assert config().requires == ["sale"]


def test_it_is_a_free_module_of_the_sales_group_with_a_registered_icon():
    assert config().kind == "app"
    assert config() in module_configs()
    assert config().category is Category.SALES
    assert config().premium is False
    assert config().icon == "ion:cash-outline"
    # Registered in the shell (ION_ICONS): an unregistered icon paints nothing.
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in [config().icon, *(entry.icon for entry in config().navigation)]:
        assert f"'{icon.removeprefix('ion:')}'" in icons, icon


def test_it_is_in_the_store_and_in_both_verticals():
    assert 0 < len(str(config().summary)) <= 120
    assert str(config().description)
    assert config().verticals == ["hair_salon", "restaurant"]
    assert config().listed is True


def test_permissions():
    # The product's ten but «view reports», which no operation asked for (it was the home panel's).
    assert config().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles():
    assert set(config().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_may_do():
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config()], role) == set(PERMISSIONS), role
    # The manager sees the expected cash of a blind count; settings and drawers are the admin's.
    assert permissions_for_role([config()], "hub_manager") == {
        *TILL,
        "cash_register.view_expected_totals",
    }
    # The employee (the old cashier too) opens, records, counts and closes.
    assert permissions_for_role([config()], "hub_employee") == set(TILL)


def test_navigation_is_the_drawer_and_its_settings():
    entries = config().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(e.id, str(e.label), e.path, e.icon) for e in entries] == [
        ("sessions", "Cash register", "/cash_register/sessions", "ion:cash-outline"),
        ("settings", "Settings", "/cash_register/settings", "ion:settings-outline"),
    ]


def test_the_daily_auto_close_is_a_scheduled_task_of_the_app():
    # Declared in the AppConfig for the phase-2 worker: every 5 minutes, collapsed when it catches up.
    assert config().scheduled_tasks == [
        {
            "name": "auto_close_sessions",
            "operation": "cash_register.session.auto_close",
            "cron": "*/5 * * * *",
            "catch_up": "collapse",
        }
    ]


def test_every_operation_is_described_for_the_assistant():
    from live.operations import registry

    ops = {n: op for n, op in registry.items() if n.startswith("cash_register.")}
    assert ops
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name


def test_opening_closing_moving_and_counting_cash_are_high_risk():
    from live.operations import registry

    high = {
        name
        for name, op in registry.items()
        if name.startswith("cash_register.") and op.ai.get("risk") == "high"
    }
    assert high == {
        "cash_register.session.open",
        "cash_register.session.close",
        "cash_register.session.auto_close",
        "cash_register.movement.add",
        "cash_register.count.add",
    }


# The Home's hooks (PLAN-HUB round 2026-10-21; FIX-CASH_REGISTER-SETUP-HOOKS): the old module's module.json `setup`
# and `widgets` (it had no `bell`), on the queries the drawer's own screens already read (CASH_REGISTER-F01, F12).

#: What re-runs the sessions and their figures: an opening, a close, a movement, Sales' lines, the settings (the blind
#: count decides who reads the expected) and a drawer's name, shown on its sessions.
SESSION_EVENTS = [
    E.SESSION_OPENED,
    E.SESSION_CLOSED,
    E.MOVEMENT_ADDED,
    *E.SALE_EVENTS,
    E.SETTINGS_UPDATED,
    E.REGISTER_UPDATED,
]


def test_the_homes_step_is_your_cash_drawer_done_once_the_settings_are_saved():
    """«Your cash drawer» (CASH_REGISTER-F01): the factory values apply from the start, so the step asks for the
    business's own decision — done once the settings were saved, even as they came; whoever manages the settings
    sets it up in Cash register → Settings."""
    (step,) = config().setup
    assert isinstance(step, SetupStep)
    assert (
        step.key,
        step.operation,
        list(step.configured_when),
        dict(step.params),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "drawer",
        "cash_register.settings.get",
        [SetupCheck(field="updated_at", truthy=True)],
        {},
        "/cash_register/settings",
        "cash_register.manage_settings",
        "ion:cash-outline",
        [],
        90,
        False,
    )
    assert "updated_at" in registry[step.operation].output.model_fields
    # Not required, so «Recommended»: a drawer on its factory values stops no sale nor invoice.
    assert home.level_of(f"cash_register.{step.key}", step.required) == home.LEVEL_RECOMMENDED


def test_the_step_speaks_the_language_of_whoever_reads_it():
    (step,) = config().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == (
        "Your cash drawer",
        "Decide how the till opens and closes: the opening float, the closing count and the POS screen that stays "
        "locked until the drawer is open.",
    )
    assert spanish == (
        "Tu caja",
        "Decide cómo se abre y se cierra la caja: el fondo inicial, el arqueo de cierre y la pantalla del TPV que "
        "queda bloqueada hasta abrirla.",
    )


def test_the_step_is_refreshed_when_the_settings_are_saved():
    (step,) = config().setup
    assert list(step.refresh_on) == [E.SETTINGS_UPDATED]
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


PANELS = ["current_session", "recent_sessions"]


def test_the_homes_panels_are_the_old_modules_two():
    """The open session's expected cash on by default, to whoever may see it (F07); the differences of the last eight
    closed sessions, the latest first, to add (gh:cash_register#119: the filter is the one the sessions take)."""
    panels = config().widgets
    assert all(isinstance(panel, Widget) for panel in panels)
    assert [
        (
            panel.key,
            panel.kind,
            panel.component,
            panel.operation,
            panel.size,
            panel.default,
            panel.permission,
            dict(panel.params),
            dict(panel.map),
            dict(panel.options),
        )
        for panel in panels
    ] == [
        (
            "current_session",
            "kpi",
            None,
            "cash_register.session.list",
            "sm",
            True,
            "cash_register.view_expected_totals",
            {"status": "open", "limit": 1},
            {"value": "expected_balance"},
            {"format": "currency"},
        ),
        (
            "recent_sessions",
            "bar-list",
            None,
            "cash_register.session.list",
            "md",
            False,
            "cash_register.view_session",
            {"status": "closed", "sort": "closed_at", "dir": "desc", "limit": 8},
            {"label": "number", "value": "difference"},
            {"valueFormat": "currency"},
        ),
    ]
    # Every business with Cash register on, grouped under the app's own name in «Customize panel»
    # (gh:cash_register#123: never a literal category).
    assert all(not panel.verticals and not panel.category for panel in panels)
    row = registry["cash_register.session.list"].output.model_fields["rows"].annotation.__args__[0].model_fields
    for panel in panels:
        assert set(panel.map.values()) <= set(row), panel.key
        # The params are the ones the query takes (an unknown filter is refused, gh:cash_register#119).
        registry[panel.operation].input.model_validate(dict(panel.params))


def test_a_kpi_says_its_name_once():
    # gh:hub#1105: the old KPIs painted their header twice (the title and options.label with its icon).
    for panel in config().widgets:
        if panel.kind == "kpi":
            assert not {"label", "icon"} & set(panel.options), panel.key


def test_a_money_panel_pins_no_currency_nor_scale():
    """gh:cash_register#121 / gh:hub#2387 / gh:outfitkit#243: the money is in the hub's currency, with its decimals and
    in the reader's language; the old panels fixed EUR, es-ES and a divisor of 100."""
    money = [
        panel
        for panel in config().widgets
        if "currency" in (panel.options.get("format"), panel.options.get("valueFormat"))
    ]
    assert [panel.key for panel in money] == PANELS
    for panel in money:
        assert not {"currency", "locale", "valueDivisor"} & set(panel.options), panel.key


def test_the_panels_are_titled_in_english_and_in_spanish():
    with translation.override("en"):
        english = [str(panel.title) for panel in config().widgets]
    with translation.override("es"):
        spanish = [str(panel.title) for panel in config().widgets]
    assert english == ["Cash register (current session)", "Recent discrepancies"]
    assert spanish == ["Caja (sesión actual)", "Descuadres recientes"]


def test_each_panel_is_refreshed_by_the_events_that_re_run_its_query():
    panels = {panel.key: panel for panel in config().widgets}
    assert list(panels) == PANELS
    for key, panel in panels.items():
        assert list(panel.refresh_on) == SESSION_EVENTS, key
        assert live_registry.is_subscribable(panel.operation), key
        assert set(panel.refresh_on) == set(live_registry.subscribable[panel.operation]), key


def test_the_hooks_icons_are_registered_in_the_shell():
    (step,) = config().setup
    icons = [step.icon, *(panel.icon for panel in config().widgets)]
    assert icons == ["ion:cash-outline", "ion:cash-outline", "ion:swap-vertical-outline"]
    shell = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in icons:
        assert f"'{icon.removeprefix('ion:')}':" in shell, icon


def test_cash_register_has_no_bell_counters():
    # The old module declared none (its module.json has no `bell`).
    assert config().bell == []
