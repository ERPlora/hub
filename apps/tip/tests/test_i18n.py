"""Every visible text of the tips app has its Spanish translation, compiled and current."""

from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps import tip
from apps.tip import queries, schemas, services
from apps.tip.models import Settings, Tip
from apps.tip.services import drawer
from apps.tip.services import tips as tip_services
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
)

LOCALE = Path(apps.get_app_config("tip").path) / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    """Every lazy text the app shows (store, permissions, admin, choices, error messages), by its catalogue key."""
    config = apps.get_app_config("tip")
    lazies = [
        *config_texts(config),
        *config.permissions.values(),
        *module_texts(queries, schemas, services),
        *model_texts((Settings, Tip)),
        *Tip.Status.labels,
    ]
    return {catalogue_key(text) for text in lazies} | operation_titles(tip.__name__.rsplit(".", 1)[-1])


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=40, with_context=2) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("tip").verbose_name) == "Propinas"
        assert str(Tip.Status.VOIDED.label) == "Anulada"
        assert str(drawer.CASH_REGISTER_CLOSED) == (
            "La caja está cerrada: abre una sesión de caja para anotar una propina en efectivo."
        )
        assert str(tip_services.SALE_VOIDED) == "Esa venta está anulada: no admite propina."
        assert str(schemas.SAY_REASON) == "Escribe el motivo."
        assert str(schemas.SAME_SUGGESTION) == "Esa sugerencia ya está."
