"""Every visible text of the table app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.table import queries, schemas, services
from apps.table.models import (
    Hold,
    SessionMove,
    Table,
    TableSession,
    TableSettings,
    Zone,
)
from base.tests.po import catalogue_key as source
from base.tests.po import (
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
)

LOCALE = Path(apps.get_app_config("table").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (TableSettings, Zone, Table, TableSession, SessionMove, Hold)


def visible_texts() -> set[str]:
    """How the catalog keys every lazy text the app shows (menu, Home, store, admin, choices, messages) and the titles
    of its schemas."""
    config = apps.get_app_config("table")
    lazies = [
        *config_texts(config),
        *(text for step in config.setup for text in (step.title, step.description)),
    ]
    lazies += module_texts(queries, services, schemas)
    lazies += model_texts(MODELS)
    for choices in (
        Zone.Color,
        Table.Shape,
        TableSession.Status,
        SessionMove.Reason,
        SessionMove.Release,
        Hold.Source,
        Hold.Status,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {source(text) for text in lazies} | {"Table %(number)s"} | operation_titles("table")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_a_text_with_a_context_is_looked_up_with_it():
    """``pgettext_lazy`` only finds the entry with its ``msgctxt``: the comparison with the catalog has to see the
    context, or a text that goes back to ``_()`` passes while the screen says another app's Spanish."""
    assert {
        "table\x04active",
        "table check\x04Open",
        "table hold\x04Held",
    } <= visible_texts()


def test_every_visible_text_is_in_the_catalog():
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=120, with_context=10) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_tables_own_spanish():
    """A title table shares with an app installed before it («Into check», «Lines to move» with Sales) is said with
    that app's Spanish, so table's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("table")
    assert {"Into check", "Lines to move"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("table")
        assert str(config.verbose_name) == "Mesas"
        assert [str(nav.label) for nav in config.navigation] == [
            "Plano de sala",
            "Zonas",
            "Mesas",
            "Sesiones",
        ]
        assert str(services.TABLE_HAS_OPEN_SESSION) == (
            "Esa mesa tiene una cuenta abierta. Ciérrala o trasládala antes de borrar la mesa."
        )
        assert (
            str(services.ZONE_HAS_TABLES)
            == "Esta zona todavía tiene mesas. Muévelas a otra zona o bórralas antes."
        )
        assert str(services.BILL_OPEN) == (
            "La cuenta de esta mesa sigue abierta en Ventas: cóbrala, pásala a otra mesa o elimínala desde el TPV."
        )
        assert (
            str(services.NUMBER_TAKEN) == "Ya hay una mesa con ese número en esta zona."
        )
        assert str(queries.TABLE_NOT_FOUND) == "Esa mesa no existe en este negocio."
        assert [str(label) for label in TableSession.Status.labels] == [
            "Abierta",
            "Cerrada",
            "Trasladada",
            "Fusionada",
            "Aparcada",
        ]
        assert [str(label) for label in Zone.Color.labels] == [
            "Azul",
            "Cian",
            "Morado",
            "Verde",
            "Ámbar",
            "Rojo",
            "Gris",
        ]


def test_a_tables_check_is_titled_in_spanish_for_a_spanish_waiter():
    with translation.override("es"):
        assert translation.gettext("Table %(number)s") % {"number": "4"} == "Mesa 4"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/table/zones/delete",
        json.dumps({"zone": "Nowhere"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa zona no existe en este negocio."
