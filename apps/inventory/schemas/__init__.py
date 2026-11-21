"""Input and output schemas of the inventory app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in cents (integers, never negative); quantities as exact decimals with at most three places (the
finest step of any unit: a gram in a kilo); the step of each product's unit is checked by the
operations. A product or a category is named by its id or, as a person says it (assistant, voice),
by its SKU or name (``product``) or its name or slug (``category``).
"""

from . import (
    categories as categories,
    exports as exports,
    fields as fields,
    imports as imports,
    labels as labels,
    movements as movements,
    product_categories as product_categories,
    product_images as product_images,
    products as products,
    sale_reactions as sale_reactions,
    settings as settings,
    stock as stock,
    units as units,
)
