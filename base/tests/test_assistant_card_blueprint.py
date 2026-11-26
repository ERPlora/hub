"""The card of loading a template from the assistant (``base.blueprint.import``): the template by its name and its
language, as Settings › Data › Import shows them, and the apps it loads by their names — never «restaurant.en»."""

import pytest
from live.operations import get

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.card_values import ctx

__all__ = ["in_business_a"]

IMPORT = "base.blueprint.import"

#: The apps the restaurant template loads, in its order, as each language names them.
RESTAURANT_APPS = {
    "en": [
        "Time clock",
        "Cash register",
        "Menus and combos",
        "Customers",
        "Automations",
        "Inventory",
        "Invoicing",
        "Kitchen",
        "Modifiers",
        "Price Lists",
        "Printing",
        "Reservations",
        "Sales & POS",
        "Schedules",
        "Staff",
        "Tables",
        "Tasks",
        "Taxes",
        "Tips",
        "Website",
        "WhatsApp inbox",
    ],
    "es": [
        "Control horario",
        "Caja",
        "Menús y combos",
        "Clientes",
        "Automatizaciones",
        "Inventario",
        "Facturación",
        "Cocina",
        "Suplementos",
        "Tarifas",
        "Impresión",
        "Reservas",
        "Ventas / TPV",
        "Horarios",
        "Personal",
        "Mesas",
        "Tareas",
        "Impuestos",
        "Propinas",
        "Página web",
        "Bandeja de WhatsApp",
    ],
}
LABELS = {"en": ("Template", "Apps to load"), "es": ("Plantilla", "Apps que se cargan")}


def fields(arguments: dict, language: str) -> list[dict]:
    card = assistant.cards.card(get(IMPORT), arguments, language, ctx({"*"}, language=language))
    return card["fields"]


@HUB_DB
@pytest.mark.parametrize(
    ("language", "template", "name"),
    [
        ("en", "restaurant.en", "Restaurant (English)"),
        ("es", "restaurant.es", "Restaurante (español)"),
        ("es", "restaurant.en", "Restaurant (inglés)"),
        ("en", "restaurant.es", "Restaurante (Spanish)"),
    ],
)
def test_the_template_is_said_by_its_name_and_language_with_every_app_it_loads(language, template, name):
    """hub#2173: «Template: restaurant.en» told nobody what they were accepting; the card says the template as the
    Import screen does and, with no apps chosen, the ones it loads."""
    template_label, apps_label = LABELS[language]
    assert fields({"template": template}, language) == [
        {"name": "template", "label": template_label, "kind": "text", "value": name},
        {
            "name": "apps",
            "label": apps_label,
            "kind": "list",
            "value": RESTAURANT_APPS[language],
            "titled": True,
            "named": True,
        },
    ]


@HUB_DB
def test_an_empty_list_of_apps_loads_them_all_and_the_card_lists_them_all():
    """The load takes no app chosen as every app of the template: so does its card."""
    shown = fields({"template": "restaurant.en", "apps": []}, "en")
    assert shown == fields({"template": "restaurant.en"}, "en")
    assert [field["name"] for field in shown] == ["template", "apps"]
    assert shown[1]["value"] == RESTAURANT_APPS["en"]


@HUB_DB
@pytest.mark.parametrize(
    ("language", "name", "apps"),
    [("en", "Restaurante (Spanish)", ["Sales & POS", "Tables"]), ("es", "Restaurante (español)", ["Ventas / TPV", "Mesas"])],
)
def test_the_apps_chosen_are_the_ones_the_card_lists(language, name, apps):
    """Only some of its apps: the card lists those, by their names, beside the template's."""
    shown = {field["name"]: field for field in fields({"template": "restaurant.es", "apps": ["sale", "table"]}, language)}
    assert shown["template"]["value"] == name
    assert (shown["apps"]["kind"], shown["apps"]["value"], shown["apps"].get("named")) == ("list", apps, True)
    assert list(shown) == ["template", "apps"]
