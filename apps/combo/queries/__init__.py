"""Read operations of the combo app (``READ ONLY``), and the finders and rows the writes (``services``) reuse.

A menu is named by its id or its name; a course by its id, or its name inside its menu; a choice by its
id, or by its product (SKU or name) inside its menu or course: exact first, else the only one that
contains the text; several → 409 ``*_ambiguous`` with the candidates. Inventory and Taxes are this
app's ``requires``: their products and categories are read straight from their models.

A choice is **offered** when it is available here, its product is active, not deleted and sold by
units in Inventory and, in a menu to take away, it has a rate to bill it at. A menu is **sellable** (the
till offers it) when it is on sale, has at least one choice on offer, every compulsory course has enough
of them (its minimum, or one when it may repeat) and, split per dish, some catalogue price to weigh.
``lines.resolve_line`` is the price and VAT authority of a menu line (COMBO-F08, F09): eaten in or to take
away is the menu's setting unless Ventas says how this line is sold (its order's ``channel``).
"""

# Not alphabetical: the ones that register operations go first, in the order they register in.
from . import (
    new_choices as new_choices,
    menus as menus,
    courses as courses,
    images as images,
    till as till,
    lines as lines,
    dish_options as dish_options,
    offers as offers,
    reads as reads,
    recovery as recovery,
    rows as rows,
)
