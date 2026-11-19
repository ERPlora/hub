"""The customer's allergy on a dish of the kitchen (KITCHEN-F32).

A dish keeps, frozen when its round is received, the allergy the waiter marked on its line in the till and those of it
the dish contains, by the codes of ``base.allergens``. On paper they are text the device's printer prints as it comes:
a mark in the sheet's header and, under the dish and before its options, one line each in capitals, so they stand out
without colour. Their names are in the business's language: the cooks read them, whoever sent the round.
"""

from django.utils import translation
from django.utils.translation import gettext_lazy as _

from base.allergens import found_in, names

MARK = _("!! ALLERGY !!")
ALLERGY = _("*** ALLERGY: %(names)s ***")
CONTAINS = _("*** CONTAINS: %(names)s ***")


def frozen(allergy: list[str], allergens: list[str]) -> dict:
    """What a dish keeps of its line: the customer's ``allergy`` and those of it its ``allergens`` contain."""
    return {"allergy": list(allergy), "allergy_in_dish": found_in(allergy, allergens)}


def on_paper(document: dict, dishes, language: str) -> dict:
    """The sheet ``document`` of ``dishes`` (its rows, in their order) with their allergy, written in ``language``."""
    with translation.override(language):
        items = [_with_lines(row, dish) for row, dish in zip(document["items"], dishes, strict=True)]
        mark = str(MARK) if any(dish.allergy for dish in dishes) else ""
    return {**document, "allergy": mark, "items": items}


def _with_lines(row: dict, dish) -> dict:
    if not dish.allergy:
        return row
    lines = [str(ALLERGY) % {"names": names(dish.allergy).upper()}]
    if dish.allergy_in_dish:
        lines.append(str(CONTAINS) % {"names": names(dish.allergy_in_dish).upper()})
    return {**row, "modifiers": [*lines, *row.get("modifiers", [])]}
