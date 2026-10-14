"""The tax app's event vocabulary: ``tax.<entity>.<fact in the past tense>``."""

import re

from live.operations import NAME_RE

from apps.tax import events

PAST_FACT = re.compile(r"^tax\.(category|rule|alias)\.[a-z_]+ed$")


def declared():
    return {name: value for name, value in vars(events).items() if name.isupper() and isinstance(value, str)}


def test_the_six_events():
    assert declared() == {
        "CATEGORY_CREATED": "tax.category.created",
        "ALIAS_CREATED": "tax.alias.created",
        "RULE_CREATED": "tax.rule.created",
        "RULE_ENDED": "tax.rule.ended",
        "RULE_DEACTIVATED": "tax.rule.deactivated",
        "RULE_ACTIVATED": "tax.rule.activated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_the_rule_events_are_grouped():
    # Every one of them changes which rate applies: the lists of rules and categories re-run.
    assert events.RULE_EVENTS == [events.RULE_CREATED, events.RULE_ENDED, events.RULE_DEACTIVATED, events.RULE_ACTIVATED]
