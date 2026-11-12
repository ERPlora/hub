"""Every visible text of the pricing app has its Spanish translation, compiled and current."""

import re
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.pricing import queries, schemas, services
from apps.pricing.models import DiscountRule, PriceItem, PriceList
from base.tests.po import catalogue_key as source
from base.tests.po import (
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    po_entries,
    untranslated,
)

LOCALE = Path(apps.get_app_config("pricing").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (PriceList, PriceItem, DiscountRule)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("pricing")
    lazies = [
        *config_texts(config),
        *module_texts(queries, services, schemas),
    ]
    lazies += model_texts(MODELS)
    for choices in (DiscountRule.Type, DiscountRule.Scope):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {source(text) for text in lazies} | operation_titles("pricing")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=60, with_context=7) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("pricing")
        assert str(config.verbose_name) == "Tarifas"
        assert [str(nav.label) for nav in config.navigation] == ["Tarifas"]
        assert [str(label) for label in DiscountRule.Type.labels] == [
            "Porcentaje",
            "Importe por unidad",
            "Compra X, llévate Y",
            "Por tramos",
        ]
        assert str(services.DUPLICATE_LIST_CODE) == "Ya existe una tarifa con ese código. Elige otro."
        assert str(services.LIST_NOT_FOR_PRICES) == (
            "Esa tarifa no está disponible: no existe en este negocio o está desactivada."
        )


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid


def test_the_data_of_a_list_a_price_and_a_rule_are_said_as_pricing_says_them():
    """A list and a rule are «activa» (both feminine), in a «divisa» as the screens say it, «desde» and «hasta» a day as
    their forms, and «cambiado el» or «por» whom: pricing's own words, never the earlier app's that also says them
    («activo», «moneda», «vigente desde», «actualizado el»), in the admin and on the assistant's card."""
    fields = {
        PriceList: ("currency", "valid_from", "valid_until", "is_active", "updated_at", "updated_by"),
        PriceItem: ("updated_at", "updated_by"),
        DiscountRule: ("valid_from", "valid_until", "is_active", "updated_at", "updated_by"),
    }
    words = {
        "currency": "divisa",
        "valid_from": "desde",
        "valid_until": "hasta",
        "is_active": "activa",
        "updated_at": "cambiado el",
        "updated_by": "cambiado por",
    }
    with translation.override("es"):
        said = {(model.__name__, name): str(model._meta.get_field(name).verbose_name) for model, names in fields.items() for name in names}
    assert said == {(model.__name__, name): words[name] for model, names in fields.items() for name in names}
