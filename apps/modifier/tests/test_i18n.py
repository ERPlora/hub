"""Every visible text of the modifier app has its Spanish translation, compiled and current."""

from pathlib import Path

from django.apps import apps
from django.utils import translation
from live.operations import registry

from apps.modifier import queries, schemas, services
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from base.tests.po import catalogue_key, compiled_differences, model_texts, po_entries, untranslated

LOCALE = Path(apps.get_app_config("modifier").path) / "locale" / "es" / "LC_MESSAGES"


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``."""
    return [
        value for value in vars(module).values() if type(value).__name__ == "__proxy__"
    ]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, messages) and the titles of its
    schemas."""
    config = apps.get_app_config("modifier")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    lazies += (
        lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    )
    lazies += model_texts((ModifierGroup, ModifierOption, ModifierLink))
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles modifier's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones modifier wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "modifier"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("modifier")
        assert str(config.verbose_name) == "Suplementos"
        assert str(config.navigation[0].label) == "Suplementos"
        assert str(queries.GROUP_NOT_FOUND) == "Este grupo no existe."
        assert (
            str(queries.OPTION_NOT_OFFERED)
            == "Esta opción no se ofrece con este producto."
        )
        assert (
            str(queries.CHOICE_BELOW_MIN) % {"min": 1, "group": "Punto"}
            == "Elige al menos 1 en «Punto»."
        )
        assert (
            str(queries.CHOICE_ABOVE_MAX) % {"max": 2, "group": "Salsas"}
            == "Elige como mucho 2 en «Salsas»."
        )
        assert (
            str(queries.OPTION_REPEATED) % {"option": "Queso"}
            == "«Queso» no se puede repetir."
        )
        assert str(queries.PRICE_BELOW_ZERO) % {"product": "Tostada"} == (
            "Estas opciones dejan el precio de «Tostada» por debajo de cero."
        )
        assert str(queries.PRICED_BY_MEASURE) % {"product": "Jamón"} == (
            "«Jamón» se vende a peso o por medida: no admite una opción con suplemento."
        )
        assert str(services.GROUP_NAME_TAKEN) == "Ya hay un grupo con ese nombre."
        assert (
            str(services.TOO_MANY_DEFAULTS)
            == "Este grupo tiene más opciones por defecto que su máximo."
        )
        assert str(services.LINK_EXISTS) == "Este grupo ya se aplica ahí."
        assert str(services.OWN_LINE_NOT_POSITIVE) == (
            "Una opción con su propia categoría fiscal se cobra en una línea aparte: su suplemento tiene que ser "
            "mayor que cero."
        )
        assert (
            str(schemas.MAX_BELOW_MIN)
            == "El máximo no puede ser menor que el mínimo (0 = sin techo)."
        )


def test_spanish_says_modifiers_own_words_not_an_earlier_apps():
    """The texts modifier shares in English with an app loaded before it come out in Spanish with modifier's words
    (hub#663): the kitchen name of a group and of an option is «nombre en la comanda», as the group and option forms
    say it, not Menús' «nombre de cocina»; a tax category Taxes does not have is «Esa categoría fiscal…», said as
    Inventario says it next to the same tax category field, the sense and the gender being the same."""
    texts = {
        "ModifierGroup.kitchen_name": ModifierGroup._meta.get_field(
            "kitchen_name"
        ).verbose_name,
        "ModifierOption.kitchen_name": ModifierOption._meta.get_field(
            "kitchen_name"
        ).verbose_name,
        "TAX_CATEGORY_UNKNOWN": services.TAX_CATEGORY_UNKNOWN,
    }
    with translation.override("es"):
        said = {name: str(text) for name, text in texts.items()}
    assert said == {
        "ModifierGroup.kitchen_name": "nombre en la comanda",
        "ModifierOption.kitchen_name": "nombre en la comanda",
        "TAX_CATEGORY_UNKNOWN": "Esa categoría fiscal no existe en Impuestos.",
    }
