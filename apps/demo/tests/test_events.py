"""The demo app's event vocabulary: ``demo.<entity>.<fact in the past tense>``."""

import re

from live.operations import NAME_RE

from apps.demo import events

PAST_FACT = re.compile(r"^demo\.item\.[a-z_]+ed$")


def declared():
    return {name: value for name, value in vars(events).items() if name.isupper() and isinstance(value, str)}


def test_the_four_events():
    assert declared() == {
        "ITEM_CREATED": "demo.item.created",
        "ITEM_UPDATED": "demo.item.updated",
        "ITEM_DELETED": "demo.item.deleted",
        "ITEM_LINE_ADDED": "demo.item.line_added",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())
