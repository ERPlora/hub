"""The schedule app declares its module metadata, its menu entries, its permissions, what each role gets,
the assistant's contract of every operation (``ai`` and described input fields) and its hook of the Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, module_configs, permissions_for_role
from live.operations import registry

from apps.schedule import events
from apps.schedule import queries, services  # noqa: F401  (importing them registers the operations)
from base import home

# The old module's five permissions (module.json), renamed <app>.<action>.
PERMISSIONS = [
    "schedule.view",
    "schedule.add",
    "schedule.change",
    "schedule.delete",
    "schedule.manage_settings",
]
QUERIES = {
    "schedule.week.get",
    "schedule.special_day.list",
    "schedule.override.list",
    "schedule.settings.get",
    "schedule.business.is_open",
    "schedule.hours.for_range",
}
COMMANDS = {
    "schedule.week.set_day",
    "schedule.week.confirm",
    "schedule.special_day.create",
    "schedule.special_day.bulk_create",
    "schedule.special_day.update",
    "schedule.special_day.delete",
    "schedule.override.create",
    "schedule.override.update",
    "schedule.override.delete",
    "schedule.settings.update",
}
# What the assistant confirms before running: a deletion cannot be undone.
HIGH_RISK = {"schedule.special_day.delete", "schedule.override.delete"}


def schedule():
    return apps.get_app_config("schedule")


def schedule_operations():
    return {name: op for name, op in registry.items() if op.app_label == "schedule"}


def test_schedule_is_a_live_app_that_requires_no_other():
    config = schedule()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.schedule"
    assert config.label == "schedule"
    # The business's hours know nobody of the team: the per-person hours are staff's.
    assert config.requires == []


def test_schedule_is_a_free_module_of_the_people_group():
    config = schedule()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    assert config.icon == "ion:time-outline"
    assert str(config.verbose_name) == "Schedules"


def test_schedule_has_the_store_metadata_and_belongs_to_both_verticals():
    config = schedule()
    assert 0 < len(str(config.summary)) <= 120
    assert "\n" not in str(config.summary)
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert schedule().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(schedule().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_roles():
    config = schedule()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    # The employee only looks.
    assert permissions_for_role([config], "hub_employee") == {"schedule.view"}


def test_every_granted_permission_is_declared():
    config = schedule()
    for granted in config.role_permissions.values():
        for permission in granted:
            assert permission == "schedule.*" or permission in config.permissions, (
                permission
            )


def test_navigation_is_the_three_tabs_of_the_old_module():
    entries = schedule().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    # `star-outline` (the old special days' icon) is not registered: calendar-outline stands in.
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("hours", "Hours", "/schedule/hours", "ion:time-outline"),
        (
            "special_days",
            "Special days",
            "/schedule/special-days",
            "ion:calendar-outline",
        ),
        ("settings", "Settings", "/schedule/settings", "ion:settings-outline"),
    ]


# The operations and the assistant's contract


def test_the_operations_of_the_app():
    operations = schedule_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == QUERIES
    assert {name for name, op in operations.items() if op.kind == "command"} == COMMANDS


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in schedule_operations().items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name


def test_the_high_risk_commands():
    assert {
        name
        for name, op in schedule_operations().items()
        if op.ai.get("risk") == "high"
    } == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant():
    def fields(model, prefix=""):
        for name, field in model.model_fields.items():
            yield f"{prefix}{name}", field
            annotation = getattr(field.annotation, "__args__", (field.annotation,))
            for inner in annotation:
                if hasattr(inner, "model_fields"):
                    yield from fields(inner, f"{prefix}{name}.")

    missing = [
        f"{op.name}: {name}"
        for op in schedule_operations().values()
        for name, field in fields(op.input)
        if not (field.description or "").strip()
    ]
    assert missing == []


def test_the_lists_are_api_and_assistant_operations():
    operations = schedule_operations()
    # The integrations (and the booking of another product) read the hours with an API key.
    for name in (
        "schedule.week.get",
        "schedule.hours.for_range",
        "schedule.business.is_open",
    ):
        assert operations[name].expose_api is True, name


# The Home's hook (PLAN-HUB round 2026-10-21; FIX-SCHEDULE-SETUP-HOOKS): the old module's own item «Confirm your
# opening hours» (module.json `setup`, schedules#42), which reads whether the week is still the default one. The old
# module declared no panel and no bell row.


def test_the_homes_step_is_confirm_your_opening_hours_done_once_the_week_is_confirmed():
    """The old module's item, same order and words: recommended, as it declared it (`required: false`), done once a
    person confirmed the week or saved a day of it (the settings' ``hours_confirmed``, the old `confirmed_hours`), for
    whoever changes the hours, leading to the week (the old `/m/schedules/hours`)."""
    (step,) = schedule().setup
    assert isinstance(step, SetupStep)
    assert (
        step.key,
        step.operation,
        dict(step.params),
        list(step.configured_when),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "hours",
        "schedule.settings.get",
        {},
        [SetupCheck(field="hours_confirmed", truthy=True)],
        "/schedule/hours",
        "schedule.change",
        "ion:time-outline",
        [],
        101,
        False,
    )
    assert "hours_confirmed" in registry[step.operation].output.model_fields
    assert home.level_of(f"schedule.{step.key}", step.required) == home.LEVEL_RECOMMENDED


def test_the_step_says_the_old_words_in_the_language_of_whoever_reads_it():
    # The default week it names is the one migration 0002 plants: Monday to Friday, 09:00–18:00.
    (step,) = schedule().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == (
        "Confirm your opening hours",
        "We set up a default week for you (Monday to Friday, 09:00–18:00). If it matches your business, confirm it "
        "in one tap; if not, edit the days that differ — bookings outside your opening hours are refused.",
    )
    assert spanish == (
        "Confirma tu horario",
        "Hemos puesto un horario por defecto por ti (de lunes a viernes, de 09:00 a 18:00). Si coincide con el de tu "
        "negocio, confírmalo de un toque; si no, edita los días que cambien: las reservas fuera de tu horario se "
        "rechazan.",
    )


def test_the_step_is_refreshed_on_what_confirms_the_week():
    # A day saved or the week confirmed: the only writes of ``hours_confirmed``. Never the settings' first day of the
    # week, a special day or a temporary change: none of them confirms the week.
    (step,) = schedule().setup
    assert list(step.refresh_on) == [events.WEEK_UPDATED]
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


def test_the_steps_icon_is_registered():
    # The app's own icon, the old module's `time-outline`.
    (step,) = schedule().setup
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert f"'{step.icon.removeprefix('ion:')}'" in icons


def test_schedules_brings_no_panels_and_no_bell_rows_to_the_home():
    # The old module declared neither (its module.json has no `widgets` and no `bell`).
    assert (schedule().widgets, schedule().bell) == ([], [])
