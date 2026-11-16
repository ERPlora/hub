"""Every visible text of the combo app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.combo import queries, schemas, services
from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    po_entries,
    untranslated,
)

LOCALE = Path(apps.get_app_config("combo").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Combo, ChoiceGroup, ChoiceOption)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("combo")
    lazies = [
        *config_texts(config),
        *module_texts(queries, services, schemas),
        *Combo.SupplyKind.labels,
    ]
    lazies += model_texts(MODELS)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("combo")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Combos by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=60, with_context=1) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_combos_own_spanish():
    """A title combo shares with an app installed before it («Products», «SKU» with Inventory) is said with that
    app's Spanish, so combo's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("combo")
    assert {"Products", "SKU"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("combo")
        assert str(config.verbose_name) == "Menús y combos"
        assert [str(nav.label) for nav in config.navigation] == ["Menús"]
        assert [str(label) for label in Combo.SupplyKind.labels] == ["En el local", "Para llevar"]
        assert str(services.TAX_REQUIRED) == (
            "Un menú que se consume en el local necesita su propio tipo de IVA: sin él no se puede facturar."
        )
        assert str(schemas.CEILING_BELOW_FLOOR) % {"max": 1, "min": 2} == (
            "El máximo (1) queda por debajo del mínimo (2): nadie podría satisfacer nunca este plato."
        )
        assert str(queries.COMBO_NOT_FOUND) == "Ese menú no existe en este negocio."


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid
