"""Live queries of the tax app: which events re-run which list."""

from pathlib import Path

from live.live_registry import live_registry

from apps.tax import events

EVENTS_SOURCE = Path(events.__file__).read_text()
# The business's region changes which rate applies, as a rule does (TAX-F11).
RULE_EVENTS = [
    "tax.rule.created",
    "tax.rule.ended",
    "tax.rule.deactivated",
    "tax.rule.activated",
    "tax.settings.updated",
]


def tax_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("tax.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_list_and_its_events():
    assert tax_queries() == {
        # The rate column changes with every rule event.
        "tax.category.list": ["tax.category.created", *RULE_EVENTS],
        "tax.rule.list": RULE_EVENTS,
        "tax.rule.status": RULE_EVENTS,
        # The pickers of the rules screen follow the rules.
        "tax.rule.parent_candidates": RULE_EVENTS,
        "tax.rule.countries": RULE_EVENTS,
        "tax.alias.list": ["tax.alias.created"],
        "tax.settings.get": ["tax.settings.updated"],
    }


def test_every_event_is_a_literal_of_events_py():
    for on in tax_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_ending_a_rule_re_runs_the_rules_the_categories_and_the_status():
    assert live_registry.affected([events.RULE_ENDED]) >= {"tax.rule.list", "tax.category.list", "tax.rule.status"}
    assert "tax.alias.list" not in live_registry.affected([events.RULE_ENDED])


def test_a_new_alias_re_runs_only_the_aliases():
    assert {name for name in live_registry.affected([events.ALIAS_CREATED]) if name.startswith("tax.")} == {
        "tax.alias.list"
    }


def test_a_new_region_re_prices_the_till_and_the_categories():
    affected = live_registry.affected([events.SETTINGS_UPDATED])
    assert affected >= {
        "tax.settings.get",
        "tax.category.list",
        "sale.checkout.preview",
        "sale.department.list",
    }
