"""The cash register app declares its module metadata, its menu, its permissions, what each role gets
and its scheduled task (the daily auto-close the phase-2 worker runs)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

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
