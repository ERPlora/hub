"""Live queries of the tax app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.tax.events import ALIAS_CREATED, CATEGORY_CREATED, RULE_EVENTS, SETTINGS_UPDATED

# The categories show the rate in force today: every rule event, and the business's region, may change it.
live("tax.category.list", on=[CATEGORY_CREATED, *RULE_EVENTS])
live("tax.rule.list", on=RULE_EVENTS)
live("tax.rule.status", on=RULE_EVENTS)
# The pickers of the rules screen: the roots a component may hang from, the countries in use.
live("tax.rule.parent_candidates", on=RULE_EVENTS)
live("tax.rule.countries", on=RULE_EVENTS)
live("tax.alias.list", on=[ALIAS_CREATED])
live("tax.settings.get", on=[SETTINGS_UPDATED])
