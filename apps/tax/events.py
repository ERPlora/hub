"""Events of the tax app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

The tax app reacts to no event of another app, so this module only names its own.
"""

CATEGORY_CREATED = "tax.category.created"
ALIAS_CREATED = "tax.alias.created"
RULE_CREATED = "tax.rule.created"
RULE_ENDED = "tax.rule.ended"
RULE_DEACTIVATED = "tax.rule.deactivated"
RULE_ACTIVATED = "tax.rule.activated"
#: The business kept another region (TAX-F11): the rate of every category may change with it.
SETTINGS_UPDATED = "tax.settings.updated"

ALL = [
    CATEGORY_CREATED,
    ALIAS_CREATED,
    RULE_CREATED,
    RULE_ENDED,
    RULE_DEACTIVATED,
    RULE_ACTIVATED,
    SETTINGS_UPDATED,
]
#: Every event that may change which rules apply today (TAX-F17, the Home's «Your taxes»): a rule, never the region.
RULE_IN_FORCE_EVENTS = [RULE_CREATED, RULE_ENDED, RULE_DEACTIVATED, RULE_ACTIVATED]
#: Every event that changes which rate applies: a rule, or the business's region.
RULE_EVENTS = [*RULE_IN_FORCE_EVENTS, SETTINGS_UPDATED]
