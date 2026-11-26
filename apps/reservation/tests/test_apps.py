"""The reservation app declares its module metadata, its menu, its permissions and what each role gets."""

import pytest
from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs
from live.operations import INTERNAL

from base import assistant
from base.tenancy.tests.business import HUB_DB
from base.tests import help_videos
from base.tests.roles import grants_by_role

PERMISSIONS = [
    "reservation.view_reservation",
    "reservation.add_reservation",
    "reservation.change_reservation",
    "reservation.delete_reservation",
    "reservation.view_timeslot",
    "reservation.change_timeslot",
    "reservation.view_blockeddate",
    "reservation.change_blockeddate",
    "reservation.view_waitlistentry",
    "reservation.change_waitlistentry",
    "reservation.view_settings",
    "reservation.manage_settings",
]
#: Deleting a reservation for good is the owner's and the admin's (cancelling keeps it, with its reason).
ADMIN_ONLY = {"reservation.delete_reservation"}
#: The host or the waiter at the door (WORKBOOK «Referencia adoptada», duda 1): takes, confirms, seats,
#: edits and cancels reservations and keeps the waitlist; the slots, the blocked days and the rules are
#: the manager's.
EMPLOYEE = {
    "reservation.view_reservation",
    "reservation.add_reservation",
    "reservation.change_reservation",
    "reservation.view_timeslot",
    "reservation.view_blockeddate",
    "reservation.view_waitlistentry",
    "reservation.change_waitlistentry",
    "reservation.view_settings",
}

OPERATIONS = {
    "reservation.reservation.list",
    "reservation.reservation.get",
    "reservation.availability.day",
    "reservation.availability.tables",
    "reservation.time_slot.list",
    "reservation.time_slot.get",
    "reservation.blocked_date.list",
    "reservation.blocked_date.get",
    "reservation.waitlist.list",
    "reservation.waitlist.get",
    "reservation.settings.get",
    "reservation.reservation.create",
    "reservation.reservation.update",
    "reservation.reservation.confirm",
    "reservation.reservation.seat",
    "reservation.reservation.complete",
    "reservation.reservation.cancel",
    "reservation.reservation.no_show",
    "reservation.reservation.delete",
    "reservation.reservation.release_unconfirmed",
    "reservation.time_slot.create",
    "reservation.time_slot.delete",
    "reservation.blocked_date.create",
    "reservation.blocked_date.delete",
    "reservation.waitlist.create",
    "reservation.waitlist.update",
    "reservation.waitlist.convert",
    "reservation.waitlist.delete",
    "reservation.settings.update",
    "reservation.customer.reassign",
    "reservation.customer.erase",
    "reservation.reservation.check",
}
#: What only the assistant's card reads before it is shown: no tool, no route (``ai=INTERNAL``).
INTERNAL_READS = {"reservation.reservation.check"}
#: The writes the assistant's card checks first by a read of the app (``ai["check"]``).
CHECKED = {"reservation.reservation.create": "reservation.reservation.check"}


def reservation():
    return apps.get_app_config("reservation")


def test_reservation_is_a_live_app():
    config = reservation()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.reservation"
    assert config.label == "reservation"


def test_reservation_is_a_free_module_of_the_restaurant_group_with_a_registered_icon():
    config = reservation()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.RESTAURANT
    assert config.premium is False
    # The old module's first menu icon, registered in the shell (ION_ICONS); a restaurant table of its
    # own waits in UI-REQUESTS.md.
    assert config.icon == "ion:calendar-outline"
    assert str(config.verbose_name) == "Reservations"


def test_reservation_requires_tables_customers_and_schedules():
    # The table is a table of Tables, the guest a card of Customers, and a booking fits the business's
    # opening hours of Schedules.
    assert reservation().requires == ["table", "customer", "schedule"]


def test_reservation_is_in_the_store_and_in_the_restaurant_template():
    config = reservation()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert list(reservation().permissions) == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(reservation().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    everything = set(PERMISSIONS)
    assert grants_by_role(reservation()) == {
        "hub_owner": everything,
        "hub_admin": everything,
        "hub_manager": everything - ADMIN_ONLY,
        "hub_employee": EMPLOYEE,
        "hub_accountant": set(),
    }


def test_navigation_is_the_three_sections_of_the_old_module_and_the_settings_with_its_icons():
    # Settings opens only to whoever may save them, and so does its tab of the pages.
    entries = reservation().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(entry.id, str(entry.label), entry.icon, entry.path, entry.permission) for entry in entries] == [
        (
            "reservations",
            "Reservations",
            "ion:calendar-outline",
            "/reservation/reservations",
            "reservation.view_reservation",
        ),
        ("waitlist", "Waitlist", "ion:people-outline", "/reservation/waitlist", "reservation.view_waitlistentry"),
        ("availability", "Availability", "ion:time-outline", "/reservation/availability", "reservation.change_timeslot"),
        ("settings", "Settings", "ion:settings-outline", "/reservation/settings", "reservation.manage_settings"),
    ]


#: Done at the door by whoever receives the party (``ai.in_person``): never granted to an automation (FLOW-F12), and
#: still of normal risk, so the assistant seats by voice without a confirmation card.
IN_PERSON = {"reservation.reservation.seat"}
#: The writes whose card says their data in an order of their own (``ai["summary"]``): for whom, the day and the time.
SUMMARISED = {"reservation.reservation.create"}


def test_seating_is_done_in_person_and_of_normal_risk():
    from live.operations import get

    from live.assistant import risk

    seat = get("reservation.reservation.seat")
    assert seat.ai["in_person"] is True
    assert risk(seat) == "normal"


def test_the_operations_are_the_workbook_ones():
    from live.operations import registry

    assert {name for name in registry if name.startswith("reservation.")} == OPERATIONS


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    operations = [
        op for name, op in registry.items() if name.startswith("reservation.")
    ]
    assert len(operations) == len(OPERATIONS)
    internal = {op.name for op in operations if op.ai is INTERNAL}
    assert internal == INTERNAL_READS
    assert all(not registry[name].expose_api for name in internal)
    for op in operations:
        if op.name in internal:
            continue
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        if op.name in CHECKED:
            expected = expected | {"check"}
            assert op.ai["check"] == CHECKED[op.name]
        if assistant.tools.is_tool(op):  # what a person types to ask for it (live.E020: reservation is listed)
            expected = expected | {"asks"}
        if op.name in IN_PERSON:
            expected = expected | {"in_person"}
        if op.name in SUMMARISED:
            expected = expected | {"summary"}
        assert set(op.ai) == expected, op.name
        assert op.ai.get("in_person", False) is (op.name in IN_PERSON), op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name


def test_cancelling_marking_a_no_show_and_deleting_are_high_risk():
    from live.operations import registry

    high = {
        name
        for name, op in registry.items()
        if name.startswith("reservation.")
        and op.kind == "command"
        and op.ai["risk"] == "high"
    }
    assert high == {
        "reservation.reservation.cancel",
        "reservation.reservation.no_show",
        "reservation.reservation.delete",
        "reservation.time_slot.delete",
        "reservation.blocked_date.delete",
        "reservation.waitlist.delete",
    }


def test_every_input_field_says_what_it_is():
    # The assistant reads the JSON Schema of each input: a field without a description is a guess.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("reservation."):
            continue
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}: {field}"


def test_the_unconfirmed_reservations_are_released_every_quarter_of_an_hour():
    # RESERVATION-F13: the worker runs it on every hub as the system (cron in UTC).
    assert reservation().scheduled_tasks == [
        {
            "name": "release_unconfirmed_reservations",
            "operation": "reservation.reservation.release_unconfirmed",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]


def test_the_reactions_are_the_platforms_only():
    from live.operations import get

    for name in ("reservation.customer.reassign", "reservation.customer.erase"):
        assert get(name).permission == "reservation.system", name


def test_its_help_window_plays_the_app_s_tour_in_spanish_and_in_english():
    assert reservation().help.videos == {"es": "6-9Ca12M6o0", "en": "WlNYEi3jCjU"}


#: The short video of each task, with the flows it shows: its Spanish and its English one.
TASK_VIDEOS = [
    (("RESERVATION-F06", "RESERVATION-F23"), "dtI39MRe1gk", "rFYllyUQe2Q"),
    (("RESERVATION-F07",), "WW1mMVh51hM", "o37Ho17tWnI"),
    (("RESERVATION-F08", "RESERVATION-F09", "RESERVATION-F20"), "S8LU9RkaLDc", "Hf2TuSIgJ1Y"),
    (("RESERVATION-F10",), "6azOhfKZCwk", "ISpAS2jfrOc"),
    (("RESERVATION-F14", "RESERVATION-F15"), "j_NWW1dEiYs", "zvNv_-7YbHc"),
    (("RESERVATION-F02",), "AL8cmSYK11k", "ZOUn-FIILR4"),
    (("RESERVATION-F03", "RESERVATION-F04"), "bdFYu4Joc3w", "Frt5bMCp6lo"),
]


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_each_task_of_the_help_window_shows_its_short_videos_in_the_person_s_language(language):
    assert help_videos.shown("reservation", language) == help_videos.by_task(TASK_VIDEOS, language)
