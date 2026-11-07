"""Every visible text of the combo app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.combo import queries, schemas, services
from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from base.tests.po import catalogue_key, missing_from_catalogue, po_entries

LOCALE = Path(apps.get_app_config("combo").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Combo, ChoiceGroup, ChoiceOption)


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top (error and validation messages)."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("combo")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
        *Combo.SupplyKind.labels,
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles combo's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones combo wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "combo"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Combos by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=60, with_context=1) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_combos_own_spanish():
    """A title combo shares with an app installed before it («Products», «SKU» with Inventory) is said with that
    app's Spanish, so combo's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
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
