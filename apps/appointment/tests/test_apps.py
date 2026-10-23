"""The appointment app declares its module metadata, its menu, its permissions and what each role gets."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import BellCounter, Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "appointment.view_appointment",
    "appointment.view_own_appointment",
    "appointment.add_appointment",
    "appointment.add_own_appointment",
    "appointment.change_appointment",
    "appointment.change_own_appointment",
    "appointment.delete_appointment",
    "appointment.view_schedule",
    "appointment.manage_schedule",
    "appointment.manage_settings",
]
#: Deleting and the settings are the owner's and the admin's (the old module's admin).
ADMIN_ONLY = {"appointment.delete_appointment", "appointment.manage_settings"}
#: The employee sees and manages their own agenda (WORKBOOK «Quién puede qué»).
EMPLOYEE = {
    "appointment.view_own_appointment",
    "appointment.add_own_appointment",
    "appointment.change_own_appointment",
    "appointment.view_schedule",
}


def appointment():
    return apps.get_app_config("appointment")


def test_appointment_is_a_live_app():
    config = appointment()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.appointment"
    assert config.label == "appointment"


def test_appointment_is_a_free_module_of_the_people_group_with_a_registered_icon():
    config = appointment()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    assert config.icon == "ion:calendar-outline"
    assert str(config.verbose_name) == "Appointments"


def test_appointment_requires_customer_service_staff_and_schedule():
    # The customer of an appointment, its services, its professional and the business's hours.
    assert appointment().requires == ["customer", "service", "staff", "schedule"]


def test_appointment_is_in_the_store_and_in_the_hair_salon_template():
    config = appointment()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert appointment().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(appointment().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = appointment()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert (
        permissions_for_role([config], "hub_manager") == set(PERMISSIONS) - ADMIN_ONLY
    )
    assert permissions_for_role([config], "hub_employee") == EMPLOYEE


def test_navigation_is_the_old_modules_single_entry_with_a_registered_icon():
    entries = appointment().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("appointments", "Appointments", "ion:calendar-outline", "/appointment/agenda"),
    ]


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("appointment.")}
    assert ops, "the appointment app declares no operation"
    for name, op in ops.items():
        assert op.ai and op.ai.get("description"), name
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name


def test_cancelling_marking_a_no_show_charging_and_deleting_are_high_risk():
    from live.operations import get

    for name in (
        "appointment.appointment.cancel",
        "appointment.appointment.mark_no_show",
        "appointment.appointment.charge",
        "appointment.appointment.delete",
        "appointment.appointment.bulk_delete",
        "appointment.recurring.delete",
        "appointment.blocked_time.delete",
    ):
        assert get(name).ai["risk"] == "high", name


def test_it_tells_the_device_of_the_customers_own_bookings_and_cancellations():
    """APPOINTMENT-F28 (old-hub:HUB_SHELL-F66): «New appointment · {customer}» or «Appointment cancelled · {customer}»,
    with the services, «{day} at {hour}» and the professional; a tap opens the agenda on that day. Of the agenda the
    person sees (its query's own rule), refreshed by a booking and a cancellation."""
    from live.meta import DeviceNotice, SetupCheck

    booked, cancelled = appointment().notices
    assert all(isinstance(notice, DeviceNotice) for notice in (booked, cancelled))
    assert [(n.key, n.operation, list(n.when)) for n in (booked, cancelled)] == [
        ("booked", "appointment.appointment.notices", [SetupCheck(field="kind", equals="booked")]),
        ("cancelled", "appointment.appointment.notices", [SetupCheck(field="kind", equals="cancelled")]),
    ]
    assert [str(text) for text in booked.title] == ["New appointment · {customer_name}", "New appointment"]
    assert [str(text) for text in cancelled.title] == ["Appointment cancelled · {customer_name}", "Appointment cancelled"]
    for notice in (booked, cancelled):
        assert [str(text) for text in notice.body] == [
            "{service_names}",
            "{start_date_label} at {start_time_label}",
            "{staff_name}",
        ]
        assert notice.route == "/appointment/agenda?date={start:.10}"
        assert notice.permission == "appointment.view_own_appointment"
        assert list(notice.refresh_on) == ["appointment.appointment.created", "appointment.appointment.cancelled"]


# ── The Home's hooks (PLAN-HUB round 2026-10-21) ────────────────────────────────────────────────────

#: What changes how many upcoming bookings wait for confirmation in the agenda the person sees: one is booked
#: pending; it is confirmed, started, completed (charged at the till), cancelled or deleted; it moves (to the past
#: or to another professional) or its professional leaves. Never a no-show (only once its start is past, when it
#: no longer counts), an edit of its notes or phone, a charge that leaves it as it was, nor a card merged into
#: another (same professional, time and state).
TO_CONFIRM = [
    "appointment.appointment.created",
    "appointment.appointment.confirmed",
    "appointment.appointment.started",
    "appointment.appointment.completed",
    "appointment.appointment.cancelled",
    "appointment.appointment.rescheduled",
    "appointment.appointment.unassigned",
    "appointment.appointment.deleted",
]


def test_the_bell_counts_the_appointments_to_confirm():
    """The old module's counter of the bell (its module.json ``bell``, appointments#169, hub#1678): «Appointments to
    confirm», on the query the agenda's «N to confirm» reads, leading to the agenda. Whoever sees an agenda sees it
    (its query counts the person's own, or everybody's for whoever sees them all)."""
    [counter] = appointment().bell
    assert isinstance(counter, BellCounter)
    assert (
        counter.key,
        counter.operation,
        dict(counter.params),
        counter.route,
        str(counter.label),
        counter.icon,
        counter.permission,
    ) == (
        "to_confirm",
        "appointment.appointment.count_to_confirm",
        {},
        "/appointment/agenda",
        "Appointments to confirm",
        "ion:calendar-outline",
        "appointment.view_own_appointment",
    )
    assert list(counter.refresh_on) == TO_CONFIRM


def test_the_counter_says_the_old_words_in_spanish():
    with translation.override("es"):
        assert str(appointment().bell[0].label) == "Citas por confirmar"


def test_the_counters_events_re_run_its_query_and_its_icon_is_registered():
    counter = appointment().bell[0]
    assert live_registry.is_subscribable(counter.operation)
    assert set(counter.refresh_on) <= set(live_registry.subscribable[counter.operation])
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert f"'{counter.icon.removeprefix('ion:')}'" in icons


def test_citas_has_no_setup_steps_nor_panels():
    # The old module declared neither (its module.json has no `setup` nor `widgets`), and the old hub's
    # setup_status.rs only listed the core's own steps (apps, business details, printer, team).
    assert (appointment().setup, appointment().widgets) == ([], [])
