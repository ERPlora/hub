"""Input and output schemas of the combo app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

Every input refuses a field it does not declare. A menu is named by its id or its name («menu of the
day»); a course by its id, or by its name inside a menu («Starters»); a choice by its id, or by its
product inside a menu; a product by its id, its SKU or its name: the assistant is used by voice.
``queries.find_combo``, ``find_group`` and ``find_option`` turn the text into the row. Money is in
cents.
"""

from . import (
    choices as choices,
    courses as courses,
    dish_options as dish_options,
    fields as fields,
    images as images,
    menus as menus,
    on_sale as on_sale,
    references as references,
    till as till,
)
