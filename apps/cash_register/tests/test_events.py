"""The cash register app's events (``cash_register.<entity>.<fact>``) and why it reacts to none.

The drawer reads sale's lines from sale (its requirement) when they are looked at, so it needs no reaction
to sale's events and loses nothing without the outbox relay: its live queries only re-run on them.
"""

import re

from live.context import Scope
from live.operations import NAME_RE

from apps.cash_register import events

PAST_FACT = re.compile(r"^cash_register\.[a-z_]+\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper()
        and isinstance(value, str)
        and value.startswith("cash_register.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "SETTINGS_UPDATED": "cash_register.settings.updated",
        "REGISTER_CREATED": "cash_register.register.created",
        "REGISTER_UPDATED": "cash_register.register.updated",
        "SESSION_OPENED": "cash_register.session.opened",
        "SESSION_CLOSED": "cash_register.session.closed",
        "MOVEMENT_ADDED": "cash_register.movement.added",
        "COUNT_ADDED": "cash_register.count.added",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_the_sale_events_that_change_a_shift():
    assert events.SALE_EVENTS == [
        "sale.sale.completed",
        "sale.sale.voided",
        "sale.sale.refunded",
    ]


def test_it_reacts_to_no_event():
    assert events.REACTIONS == {}
    for name in events.SALE_EVENTS:
        assert events.react(Scope("host", "a"), name, {"sale_id": "x"}) is None
