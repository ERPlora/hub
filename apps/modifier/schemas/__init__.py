"""Input and output schemas of the modifier app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Supplements
travel in cents (integers, negative = a discount). A group is named by its id or its name («Sauces»),
an option by its id or its name and, when two groups have one with that name, its group; a product by
its id, SKU or name and a category by its id or name, as Inventory reads them. Inputs refuse a field
they do not have (an unknown filter is a 422); only a reaction takes Inventory's payload as it comes.
"""

from . import (
    fields as fields,
    groups as groups,
    links as links,
    options as options,
    till as till,
)
