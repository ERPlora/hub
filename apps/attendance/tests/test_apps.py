"""The attendance app declares its module metadata, its menu entries, its permissions, what each role
gets, its scheduled task and the assistant's contract of every operation (``ai`` and described input
fields)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, Widget, module_configs, permissions_for_role
from live.operations import registry

from apps.attendance import events as E
from apps.attendance import queries, services  # noqa: F401  (importing them registers the operations)

# The old module's four permissions (module.json), plus clocking someone else (ATTENDANCE-F12).
PERMISSIONS = [
    "attendance.clock",
    "attendance.view_all",
    "attendance.correct",
    "attendance.clock_others",
    "attendance.manage_settings",
]
QUERIES = {
    "attendance.record.current",
    "attendance.record.list",
    "attendance.record.detail",
    "attendance.record.export",
    "attendance.correction.list",
    "attendance.presence.list",
    "attendance.presence.count",
    "attendance.person.list",
    "attendance.person.detail",
    "attendance.settings.get",
}
COMMANDS = {
    "attendance.record.clock_in",
    "attendance.record.clock_out",
    "attendance.break.start",
    "attendance.break.end",
    "attendance.record.correct",
    "attendance.settings.update",
    "attendance.record.review_stale",
    "attendance.record.close_for_terminated",
}


def attendance():
    return apps.get_app_config("attendance")


def test_attendance_is_an_installed_live_app_that_requires_staff():
    config = attendance()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.attendance"
    assert config.label == "attendance"
    assert "apps.attendance" in settings.INSTALLED_APPS
    # A working day belongs to a staff record (WORKBOOK «A qué reacciona y lo que necesita»).
    assert config.requires == ["staff"]


def test_attendance_is_a_free_module_of_the_people_group():
    config = attendance()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    # Its own icon, the fingerprint of the old module and of time clocks on the market (UI-REQUESTS.md),
    # registered in the shell; `ion:time-outline` is the Schedules app's on the apps page.
    assert config.icon == "ion:finger-print-outline"
    assert all(
        other.icon != config.icon for other in module_configs() if other is not config
    )


def test_attendance_is_in_the_store_and_in_both_verticals():
    # Every business with employees must keep the working-day record (art. 34.9 ET).
    config = attendance()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert attendance().permissions == PERMISSIONS


def test_roles():
    config = attendance()
    everything = set(PERMISSIONS)
    assert permissions_for_role([config], "hub_owner") == everything
    assert permissions_for_role([config], "hub_admin") == everything
    assert permissions_for_role([config], "hub_manager") == everything
    # The employee clocks, sees their own days and history, reads the settings and exports their own.
    assert permissions_for_role([config], "hub_employee") == {"attendance.clock"}


def test_navigation_is_the_old_menu_with_iconify_icons():
    # The old module's two menu entries («Clock in», «Records») with their old icons, registered ones.
    entries = attendance().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("clock", "Clock in", "ion:time-outline", "/attendance/clock"),
        ("records", "Records", "ion:list-outline", "/attendance/records"),
    ]


def test_the_review_of_forgotten_days_is_a_scheduled_task():
    # ATTENDANCE-F05: every 15 minutes (UTC), collapsing missed runs, as the old module.
    assert attendance().scheduled_tasks == [
        {
            "name": "review_stale",
            "operation": "attendance.record.review_stale",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]


def test_the_operations_are_the_workbooks():
    ops = {name: op for name, op in registry.items() if name.startswith("attendance.")}
    assert {name for name, op in ops.items() if op.kind == "query"} == QUERIES
    assert {name for name, op in ops.items() if op.kind == "command"} == COMMANDS


def test_every_operation_is_described_for_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: it sees every
    # operation, a write says how risky it is, and correcting a working day is high risk.
    ops = {name: op for name, op in registry.items() if name.startswith("attendance.")}
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai or op.ai["risk"] == "high", name
    assert ops["attendance.record.correct"].ai["risk"] == "high"


def test_every_input_field_is_described():
    ops = {name: op for name, op in registry.items() if name.startswith("attendance.")}
    for name, op in ops.items():
        for field_name, field in op.input.model_fields.items():
            assert (field.description or "").strip(), f"{name}.{field_name}"


# The Home's panel (PLAN-HUB round 2026-10-21; FIX-ATTENDANCE-SETUP-HOOKS): the old module's module.json `widgets`, one
# KPI (it had no `setup` nor `bell`), on the count of «Clocked in now» (ATTENDANCE-F11).


def test_the_homes_panel_is_the_old_modules_one():
    """«Clocked in now» on by default, to whoever sees the whole team, in every business (the old sectors were all)."""
    panels = attendance().widgets
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
            "clocked_in_now",
            "kpi",
            None,
            "attendance.presence.count",
            "sm",
            True,
            "attendance.view_all",
            {},
            {"value": "count"},
            {"format": "number"},
        ),
    ]
    assert all(not panel.verticals and not panel.category for panel in panels)


def test_the_panel_maps_a_field_its_query_gives_and_takes_its_params():
    """A map that names no field of the query leaves the panel blank without an error."""
    for panel in attendance().widgets:
        output = registry[panel.operation].output.model_fields
        assert set(panel.map.values()) <= set(output), panel.key
        registry[panel.operation].input.model_validate(dict(panel.params))


def test_a_kpi_says_its_name_once():
    # gh:hub#1105: the old KPIs painted their header twice (the title and options.label with its icon).
    for panel in attendance().widgets:
        assert not {"label", "icon"} & set(panel.options), panel.key


def test_the_panel_is_titled_in_english_and_in_spanish():
    with translation.override("en"):
        assert [str(panel.title) for panel in attendance().widgets] == ["Clocked in now"]
    with translation.override("es"):
        assert [str(panel.title) for panel in attendance().widgets] == ["Fichados ahora"]


def test_the_panel_is_refreshed_by_the_events_that_re_run_its_query():
    """The events attendance emits today (`attendance.record.clocked_in`…), never the old module's
    (`attendance.clocked_in`, `attendance.clocked_out`), as «Clocked in now» in Records follows them."""
    (panel,) = attendance().widgets
    assert list(panel.refresh_on) == [*E.PRESENCE, E.MEMBER_UPDATED, E.MEMBER_TERMINATED]
    assert live_registry.is_subscribable(panel.operation)
    assert set(panel.refresh_on) == set(live_registry.subscribable[panel.operation])
    assert set(panel.refresh_on) == set(live_registry.subscribable["attendance.presence.list"])


def test_the_panels_icon_is_registered_in_the_shell():
    icons = [panel.icon for panel in attendance().widgets]
    assert icons == ["ion:time-outline"]
    shell = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in icons:
        assert f"'{icon.removeprefix('ion:')}':" in shell, icon


def test_attendance_has_no_setup_steps_nor_bell_counters():
    # The old module declared none (its module.json has no `setup` nor `bell`).
    assert attendance().setup == []
    assert attendance().bell == []
