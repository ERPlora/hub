"""The appointment app declares its module metadata, its menu, its permissions and what each role gets."""

import pytest
from django.apps import apps
from django.utils import translation
from live.live_registry import live_registry
from live.meta import BellCounter, Category, LiveAppConfig, Nav, module_configs

from base.tenancy.tests.business import HUB_DB
from base.tests import help_videos
from base.tests.roles import grants_by_role
from base.tests.shell_icons import shell_icon_registry

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
#: Deleting and the settings are the owner's and the admin's.
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
    assert list(appointment().permissions) == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(appointment().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    everything = set(PERMISSIONS)
    assert grants_by_role(appointment()) == {
        "hub_owner": everything,
        "hub_admin": everything,
        "hub_manager": everything - ADMIN_ONLY,
        "hub_employee": EMPLOYEE,
        "hub_accountant": set(),
    }


def test_navigation_is_the_agenda_and_its_settings_with_registered_icons():
    entries = appointment().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(entry.id, str(entry.label), entry.icon, entry.path, entry.permission) for entry in entries] == [
        ("appointments", "Agenda", "ion:calendar-outline", "/appointment/agenda", "appointment.view_own_appointment"),
        ("settings", "Settings", "ion:settings-outline", "/appointment/settings", "appointment.manage_settings"),
    ]


#: The reads that are no assistant tool: what names a blocked period on the assistant's card (hub#635), as the model reads
#: the blocks by their list; the agenda's list of the bookings to confirm, as the model counts them and lists them
#: by their status; and the blocks still to come that an export of the business carries.
INTERNAL_READS = {
    "appointment.blocked_time.get", "appointment.appointment.list_to_confirm", "appointment.blocked_time.list_upcoming",
}


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import INTERNAL, registry

    ops = {name: op for name, op in registry.items() if name.startswith("appointment.")}
    assert ops, "the appointment app declares no operation"
    assert {name for name, op in ops.items() if op.ai is INTERNAL} == INTERNAL_READS
    for name, op in ops.items():
        if name in INTERNAL_READS:
            assert (op.kind, op.expose_api) == ("query", False), name
            continue
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
    """«New appointment · {customer}» or «Appointment cancelled · {customer}», with the services, «{day} at {hour}» and
    the professional; a tap opens the agenda on that day. Of the agenda the person sees (its query's own rule),
    refreshed by a booking and a cancellation."""
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


# ── The Home's hooks ────────────────────────────────────────────────────────────────────────────────

#: What changes how many upcoming bookings wait for confirmation in the agenda the person sees: one is booked
#: pending; it is confirmed, started, completed (charged at the till), cancelled, deleted or restored; it moves (to
#: the past or to another professional) or its professional leaves. Never a no-show (only once its start is past,
#: when it no longer counts), an edit of its notes or phone, a charge that leaves it as it was, nor a card merged
#: into another (same professional, time and state).
TO_CONFIRM = [
    "appointment.appointment.created",
    "appointment.appointment.confirmed",
    "appointment.appointment.started",
    "appointment.appointment.completed",
    "appointment.appointment.cancelled",
    "appointment.appointment.rescheduled",
    "appointment.appointment.unassigned",
    "appointment.appointment.deleted",
    "appointment.appointment.restored",
]


def test_the_bell_counts_the_appointments_to_confirm():
    """The bell's «Appointments to confirm», on the query the agenda's «N to confirm» reads, leading to the agenda's
    list of every booking to confirm. Whoever sees an agenda sees it (its query counts the person's own, or everybody's for
    whoever sees them all)."""
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
        "/appointment/agenda?to_confirm=1",
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
    icons = shell_icon_registry()
    assert f"'{counter.icon.removeprefix('ion:')}'" in icons


def test_citas_has_no_setup_steps_nor_panels():
    assert (appointment().setup, appointment().widgets) == ([], [])


def test_its_help_window_plays_the_app_s_tour_in_spanish_and_in_english():
    assert appointment().help.videos == {"es": "iDYOJPslKLo", "en": "T9O2qIaHX38"}


#: The short video of each task, with the flows it shows: its Spanish and its English one.
TASK_VIDEOS = [
    (("APPOINTMENT-F01", "APPOINTMENT-F02"), "7k8rDOavPPQ", "jqE5frTxwIs"),
    (("APPOINTMENT-F03",), "JEZ7xwTUQRg", "_IJqA5Llo58"),
    (("APPOINTMENT-F04", "APPOINTMENT-F22"), "3iicsBB4OJU", "vti0BeNrB0A"),
    (("APPOINTMENT-F07", "APPOINTMENT-F08"), "SCCcOjjX0-Q", "5RkcBExG2Sc"),
    (("APPOINTMENT-F09",), "lyPRKIKNyzE", "_7B2JQ7NPCM"),
    (("APPOINTMENT-F27",), "CS_8cW8l4ro", "wF2fyfpId5Q"),
    (("APPOINTMENT-F19",), "apnOcQN7PlY", "YFmNll_QLbc"),
]


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_each_task_of_the_help_window_shows_its_short_videos_in_the_person_s_language(language):
    assert help_videos.shown("appointment", language) == help_videos.by_task(TASK_VIDEOS, language)
