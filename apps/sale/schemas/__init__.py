"""Input and output schemas of the sale app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels in
whole cents (never negative); quantities as exact decimals with at most three places; percentages with
two. What a person names aloud is accepted besides the id: a product by its SKU or name, a customer by
its name, phone or email, a sale by its number, a payment method by its name or type, a department or
a quick note by its name or text.
"""

from . import (
    checkout as checkout,
    fields as fields,
    figures as figures,
    line_allergy as line_allergy,
    lines as lines,
    orders as orders,
    reactions as reactions,
    records as records,
    refunds as refunds,
    sales as sales,
    settings as settings,
    vouchers as vouchers,
)
