"""The fourteen allergens a food business must declare (Annex II of Regulation (EU) No 1169/2011), once for every app.

Inventory declares a product's, and Sales and Kitchen read them without requiring Inventory, so the list lives in the
platform. Each allergen has a stable code, the one the data keeps and the API speaks, and a name in the person's
language. The list is closed and its order is the regulation's: every screen, file and card says them in it.
"""

import unicodedata
from functools import cache
from typing import Annotated

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints, WithJsonSchema

ALLERGENS = (
    ("gluten", pgettext_lazy("allergen", "Gluten")),
    ("crustaceans", pgettext_lazy("allergen", "Crustaceans")),
    ("egg", pgettext_lazy("allergen", "Egg")),
    ("fish", pgettext_lazy("allergen", "Fish")),
    ("peanut", pgettext_lazy("allergen", "Peanut")),
    ("soy", pgettext_lazy("allergen", "Soy")),
    ("milk", pgettext_lazy("allergen", "Milk")),
    ("tree_nuts", pgettext_lazy("allergen", "Tree nuts")),
    ("celery", pgettext_lazy("allergen", "Celery")),
    ("mustard", pgettext_lazy("allergen", "Mustard")),
    ("sesame", pgettext_lazy("allergen", "Sesame")),
    ("sulphites", pgettext_lazy("allergen", "Sulphites")),
    ("lupin", pgettext_lazy("allergen", "Lupin")),
    ("molluscs", pgettext_lazy("allergen", "Molluscs")),
)
CODES = tuple(code for code, _name in ALLERGENS)
NAMES = dict(ALLERGENS)

NOT_ONE_OF_THE_FOURTEEN = _("That allergen is not one of the fourteen that must be declared.")
#: Why a row of a CSV fails when its allergens cell names something else.
NOT_RECOGNIZED = _("Allergen not recognized: %(text)s")


def names(codes: list[str]) -> str:
    """The allergens of ``codes`` by their names, in the order of the list («Gluten, Milk»); empty for none."""
    return ", ".join(str(name) for code, name in ALLERGENS if code in codes)


def in_order(codes: list[str]) -> list[str]:
    """``codes`` once each and in the order of the list; any code off the list refuses them all."""
    if not set(codes) <= set(CODES):
        raise ValueError(str(NOT_ONE_OF_THE_FOURTEEN))
    return [code for code in CODES if code in codes]


def found_in(allergy: list[str], allergens: list[str]) -> list[str]:
    """Those of a customer's ``allergy`` a dish of these ``allergens`` contains, in the order of the list."""
    return [code for code in CODES if code in allergy and code in allergens]


Code = Annotated[str, WithJsonSchema({"type": "string", "enum": list(CODES)})]
Allergens = Annotated[list[Code], AfterValidator(in_order)]


class AllergensIn(Schema):
    allergens: Allergens = Field(
        default_factory=list,
        max_length=len(CODES),
        description="The allergens it contains, by their codes, of the fourteen that must be declared (Regulation "
        "(EU) No 1169/2011, Annex II); none if it has none.",
    )


class AllergensPatchIn(Schema):
    allergens: Allergens | None = Field(
        None,
        max_length=len(CODES),
        description="Its allergens, all of them, by their codes: they replace the ones it had; an empty list leaves "
        "it with none.",
    )


class AllergensOut(Schema):
    allergens: list[Code] = Field(description="Its allergens, by their codes, in the order of the list.")


class AllergyInDishOut(AllergensOut):
    allergy_in_dish: list[Code] = Field(
        description="The allergens of the customer's allergy the dish contains, in the order of the list; none if it "
        "contains none of them or there is no allergy."
    )


class AllergyOut(AllergyInDishOut):
    allergy: list[Code] = Field(
        description="The customer's allergy: the allergens, by their codes and in the order of the list, the person "
        "it is for must not eat; none if no allergy was marked."
    )


class AllergensCellIn(Schema):
    allergens: Annotated[str, StringConstraints(max_length=500)] = Field(
        "", description="Allergens cell: their names separated by commas, in Spanish or English (Gluten, Leche)."
    )


def read_into(cell: str, fields: dict) -> dict | str:
    """``fields`` of a CSV row with the allergens its ``cell`` names, or why the row fails.

    The names are read in any language of the Hub, with or without accents and in any case, and by their codes too.
    """
    known = _by_name()
    written = [piece.strip() for piece in cell.split(",") if piece.strip()]
    unknown = next((piece for piece in written if _plain(piece) not in known), None)
    if unknown is not None:
        return str(NOT_RECOGNIZED) % {"text": unknown}
    return {**fields, "allergens": in_order([known[_plain(piece)] for piece in written])}


@cache
def _by_name() -> dict[str, str]:
    """Each code by itself and by its name in every language of the Hub, written plain."""
    known = {_plain(code): code for code in CODES}
    for language, _label in settings.LANGUAGES:
        with translation.override(language):
            known.update({_plain(str(name)): code for code, name in ALLERGENS})
    return known


def _plain(text: str) -> str:
    """Lowercase, without accents and with single spaces: «Crustáceos» and «crustaceos » are the same name."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).split())
