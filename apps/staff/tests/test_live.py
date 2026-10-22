"""Live queries of the staff app: which events re-run which query."""

from pathlib import Path

from live.live_registry import live_registry

from apps.sale import events as sale_events
from apps.staff import events, services

EVENTS_SOURCE = Path(events.__file__).read_text()
SERVICES_SOURCE = Path(services.__file__).read_text()

MEMBER = [
    events.MEMBER_CREATED,
    events.MEMBER_UPDATED,
    events.MEMBER_DEACTIVATED,
    events.MEMBER_TERMINATED,
]
TIME_OFF = [
    events.TIME_OFF_CREATED,
    events.TIME_OFF_APPROVED,
    events.TIME_OFF_REJECTED,
    events.TIME_OFF_CANCELLED,
]
SCHEDULE = [events.SCHEDULE_CREATED, events.SCHEDULE_UPDATED, events.SCHEDULE_DELETED]
# Sales' events, cited by name in live.py: Sales is no requirement of Staff.
SALE_FIGURES = ["sale.sale.completed", "sale.sale.voided", "sale.sale.refunded"]


def staff_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("staff.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_every_query_of_the_app_but_the_accounts_can_be_followed_live():
    # staff.account.list is not live: accounts come from the SaaS, and no event of this app changes them.
    assert set(staff_queries()) == {
        "staff.member.list",
        "staff.member.detail",
        "staff.member.mine",
        "staff.member.compensation",
        "staff.member.stats",
        "staff.commission.summary",
        "staff.commission.report",
        "staff.role.list",
        "staff.schedule.list",
        "staff.schedule.detail",
        "staff.availability.for_member",
        "staff.time_off.list",
        "staff.time_off.detail",
        "staff.time_off.today",
        "staff.time_off.mine",
        "staff.settings.get",
    }


def test_each_query_and_its_events():
    queries = staff_queries()
    # The directory and the pay show the role's name: a renamed role re-runs them.
    for name in (
        "staff.member.list",
        "staff.member.mine",
        "staff.member.compensation",
        "staff.commission.summary",
    ):
        assert queries[name] == [*MEMBER, events.ROLE_UPDATED], name
    assert queries["staff.member.detail"] == [
        events.MEMBER_UPDATED,
        events.MEMBER_DEACTIVATED,
        events.MEMBER_TERMINATED,
        events.ROLE_UPDATED,
    ]
    assert queries["staff.member.stats"] == [*MEMBER, *TIME_OFF]
    # The report names and rates people (a renamed role too) and reads what Sales sold.
    assert queries["staff.commission.report"] == [*MEMBER, events.ROLE_UPDATED, *SALE_FIGURES]
    # «Members» of a role counts the active people.
    assert queries["staff.role.list"] == [
        events.ROLE_CREATED,
        events.ROLE_UPDATED,
        *MEMBER,
    ]
    assert queries["staff.schedule.list"] == [*SCHEDULE, events.MEMBER_TERMINATED]
    assert queries["staff.schedule.detail"] == [
        events.SCHEDULE_UPDATED,
        events.SCHEDULE_DELETED,
        events.MEMBER_TERMINATED,
    ]
    # Only an approved absence (and its cancellation) changes what is available.
    assert queries["staff.availability.for_member"] == [
        *SCHEDULE,
        events.TIME_OFF_APPROVED,
        events.TIME_OFF_CANCELLED,
        events.MEMBER_TERMINATED,
    ]
    assert queries["staff.time_off.list"] == [
        *TIME_OFF,
        events.MEMBER_UPDATED,
        events.MEMBER_TERMINATED,
    ]
    assert queries["staff.time_off.detail"] == [
        events.TIME_OFF_APPROVED,
        events.TIME_OFF_REJECTED,
        events.TIME_OFF_CANCELLED,
        events.MEMBER_UPDATED,
        events.MEMBER_TERMINATED,
    ]
    assert queries["staff.time_off.today"] == [
        events.TIME_OFF_APPROVED,
        events.TIME_OFF_CANCELLED,
        events.MEMBER_UPDATED,
        events.MEMBER_TERMINATED,
    ]
    assert queries["staff.time_off.mine"] == [*TIME_OFF, *MEMBER]
    assert queries["staff.settings.get"] == [events.SETTINGS_UPDATED]


def test_every_event_is_a_literal_of_events_py_recorded_by_a_service():
    for on in staff_queries().values():
        for event in on:
            if event in SALE_FIGURES:
                continue
            assert f'"{event}"' in EVENTS_SOURCE, event
    for name, value in vars(events).items():
        if name.isupper() and isinstance(value, str):
            assert f"events.{name}" in SERVICES_SOURCE, name


def test_the_sales_events_the_report_follows_are_the_ones_sales_records():
    recorded = {value for value in vars(sale_events).values() if isinstance(value, str)}
    assert set(SALE_FIGURES) <= recorded


def test_a_pending_request_does_not_re_run_who_is_away_or_the_availability():
    affected = live_registry.affected([events.TIME_OFF_CREATED])
    assert "staff.time_off.today" not in affected
    assert "staff.availability.for_member" not in affected
    assert {
        "staff.time_off.list",
        "staff.member.stats",
        "staff.time_off.mine",
    } <= affected
