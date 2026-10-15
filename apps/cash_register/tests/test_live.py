"""Live queries of the cash register app: which events re-run which screen.

Sale's charges, voids and refunds re-run the open shift (its lines, its figures, its expected cash), so a
cash sale charged at the till shows up in the drawer at once.
"""

from pathlib import Path

from live.live_registry import live_registry

from apps.cash_register import events

SOURCES = [
    Path(events.__file__).read_text(),
    Path(events.__file__).parents[1].joinpath("sale", "events.py").read_text(),
]


def queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("cash_register.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_every_reading_is_live():
    assert set(queries()) == {
        "cash_register.settings.get",
        "cash_register.register.list",
        "cash_register.session.list",
        "cash_register.session.current",
        "cash_register.session.get",
        "cash_register.movement.list",
        "cash_register.count.list",
        "cash_register.currency.get",
    }


def test_every_event_is_a_literal_of_an_events_module():
    for on in queries().values():
        for event in on:
            assert any(f'"{event}"' in source for source in SOURCES), event


def test_a_sale_re_runs_the_open_shift():
    for event in events.SALE_EVENTS:
        assert live_registry.affected([event]) >= {
            "cash_register.session.list",
            "cash_register.session.current",
            "cash_register.session.get",
            "cash_register.movement.list",
        }, event


def test_a_movement_re_runs_the_shift_but_not_the_settings():
    affected = live_registry.affected([events.MOVEMENT_ADDED])
    assert {
        "cash_register.session.current",
        "cash_register.session.get",
        "cash_register.movement.list",
    } <= affected
    assert "cash_register.settings.get" not in affected


def test_a_count_re_runs_the_counts_and_the_detail():
    assert {
        "cash_register.count.list",
        "cash_register.session.get",
    } <= live_registry.affected([events.COUNT_ADDED])


def test_the_blind_count_setting_re_runs_every_expected():
    assert {
        "cash_register.settings.get",
        "cash_register.session.list",
        "cash_register.session.current",
        "cash_register.session.get",
    } <= live_registry.affected([events.SETTINGS_UPDATED])


def test_opening_and_closing_re_run_the_sessions_and_the_unassigned_lines():
    for event in (events.SESSION_OPENED, events.SESSION_CLOSED):
        assert {
            "cash_register.session.list",
            "cash_register.session.current",
            "cash_register.session.get",
            "cash_register.movement.list",
        } <= live_registry.affected([event])


def test_the_drawers_re_run_their_list_and_the_sessions_that_name_them():
    assert {
        "cash_register.register.list",
        "cash_register.session.list",
        "cash_register.session.get",
    } <= (live_registry.affected([events.REGISTER_UPDATED]))
