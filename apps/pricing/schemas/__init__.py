"""Input and output schemas of the pricing app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in cents (integers, never negative); a quantity is a decimal with three places in the article's own
unit (a service: units); a percent is a rate with two decimals. A price list is named by its id or, as
a person says it (assistant, voice), by its code or its name; a rule by its id, code or name; a product
by its id, SKU or name; a service by its id or name; a customer group by its id or name; a customer by
its id, name, phone or email. Every input refuses a field it does not declare. An edit changes only
the fields it sends; on a field that may be empty (the group, a day…), sending ``null`` empties it.
"""

from . import (
    catalog as catalog,
    fields as fields,
    price_lists as price_lists,
    price_removed as price_removed,
    prices as prices,
    resolution as resolution,
    rules as rules,
)
