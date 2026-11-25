"""How a category and a rule that exist are named, in a call and on the assistant's card.

A category may be named by its key, its name or an alias wherever an existing one is referred to
(``tax_category_key`` of a rule, an alias, a calculation, a lookup): the assistant is used by voice.
"""

from typing import Annotated

from django.utils.translation import gettext_noop
from pydantic import StringConstraints

from base.schemas.assistant import names

#: An existing category, by its key, its name or an alias (``queries.naming.resolve_category_text``).
CategoryRef = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]

CATEGORY_REF = "The tax category: its key (product.generic), its name (Restaurant — food) or an alias (beer)."
#: How the assistant's card names the category a write refers to, as the Rules and Aliases screens do.
CATEGORY = gettext_noop("Category")
#: What the assistant's card calls the rule a write acts on by its id (its Spanish in this app's catalog), as the Rules
#: list calls one, never «Record».
T_RULE = gettext_noop("Rule")
#: How the assistant's card names a rule a write acts on, and a category the write of any app takes, with the rate it
#: charges today (``REFERS``): never by an id or a key.
A_RULE = names("tax.rule.get", name=("label",))
A_TAX_CATEGORY = names("tax.category.get", by="key", name=("label",), as_said=True)
#: The category of a rule: its name alone, because the rule has a country and a rate of its own.
A_RULE_CATEGORY = names("tax.category.get", by="key", name=("display_name",), as_said=True)
