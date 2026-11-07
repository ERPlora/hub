"""Every visible text of the tax app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.core.validators import RegexValidator
from django.utils import translation

from apps.tax import admin as tax_admin
from apps.tax import queries, schemas, services
from apps.tax.models import SYSTEM_CATEGORY_LABELS, WHOLE_COUNTRY, TaxAlias, TaxCategory, TaxRule, TaxSettings
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    operation_titles,
    untranslated,
)

LOCALE = Path(apps.get_app_config("tax").path) / "locale" / "es" / "LC_MESSAGES"
SCREENS = Path(apps.get_app_config("tax").path) / "frontend" / "locale" / "es.json"


MESSAGES = [
    queries.CATEGORY_NOT_FOUND,
    queries.RULE_NOT_FOUND,
    queries.NO_RATE,
    schemas.REGION_UNKNOWN,
    schemas.REGION_OF_ANOTHER_COUNTRY,
    schemas.REGION_NOT_AVAILABLE,
    WHOLE_COUNTRY,
    schemas.RATE_WITHOUT_TAX,
    schemas.RANGE_BACKWARDS,
    schemas.WHICH_RULE,
    *schemas.TAX_KIND_NAMES.values(),
    services.CATEGORY_EXISTS,
    services.ALIAS_EXISTS,
    services.RULE_OVERLAPS,
    services.RULE_INCOHERENT,
    services.RULE_END_INVALID,
    services.RULE_EXISTS,
    services.RULE_ALREADY_ACTIVE,
    services.RULE_ALREADY_INACTIVE,
    tax_admin.CHOOSE_A_HUB,
]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, errors) and the titles of
    its schemas."""
    config = apps.get_app_config("tax")
    lazies = [
        *config_texts(config),
        # The Home's step (FIX-TAX-SETUP-HOOKS).
        *(text for step in config.setup for text in (step.title, step.description)),
        *MESSAGES,
        *(v.message for v in TaxCategory._meta.get_field("key").validators if isinstance(v, RegexValidator)),
    ]
    for label in SYSTEM_CATEGORY_LABELS.values():
        lazies += [text for text in label if str(text)]
    lazies += model_texts((TaxCategory, TaxRule, TaxAlias, TaxSettings))
    lazies += [*TaxRule.TaxType.labels, *TaxRule.OperationClass.labels, *TaxAlias.Source.labels]
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("tax")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Impuestos by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=75, with_context=2) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_taxs_own_spanish():
    """A title tax shares with another app is said with the Spanish of the one that comes first in
    ``INSTALLED_APPS``, and the other's entry is dead text: they have to say the same, or the card's word would hang
    on the order of the apps."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("tax")
    assert "Category" in titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts():
    with translation.override("es"):
        assert str(TaxRule.OperationClass.SUBJECT_REVERSE.label) == "Inversión del sujeto pasivo"
        assert str(TaxRule.TaxType.IGIC.label) == "IGIC (Canarias)"
        assert str(TaxAlias.Source.SHIPPED.label) == "De fábrica"
        assert str(queries.NO_RATE) == "Ninguna regla fiscal se aplica a esta categoría en este país."
        assert str(services.RULE_ALREADY_ACTIVE) == "Esa regla ya está activa."
        assert str(apps.get_app_config("tax").verbose_name) == "Impuestos"


def test_each_model_says_active_and_when_in_its_own_gender():
    """A tax category and a tax rule are feminine — «activa», «creada el», «actualizada el» —, an alias masculine
    — «activo», «creado el», «actualizado el» —, as the screens' columns say them; not auth's «activo» for all
    three, which comes first in ``INSTALLED_APPS`` (hub#667)."""
    screens = json.loads(SCREENS.read_text(encoding="utf-8"))["tax"]
    with translation.override("es"):
        said = {
            model: [str(model._meta.get_field(name).verbose_name) for name in ("is_active", "created_at", "updated_at")]
            for model in (TaxCategory, TaxRule, TaxAlias)
        }
    assert said == {
        TaxCategory: ["activa", "creada el", "actualizada el"],
        TaxRule: ["activa", "creada el", "actualizada el"],
        TaxAlias: ["activo", "creado el", "actualizado el"],
    }
    columns = {screen: screens[screen]["columns"]["active"] for screen in ("categories", "rules", "aliases")}
    assert columns == {
        "categories": said[TaxCategory][0].capitalize(),
        "rules": said[TaxRule][0].capitalize(),
        "aliases": said[TaxAlias][0].capitalize(),
    }


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/tax/categories",
        json.dumps({"key": "restaurant.food", "name": "x"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert response.json()["error"]["fields"] == {"key": "Ya hay una categoría fiscal con esa clave."}
