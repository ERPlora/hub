"""Every visible text of the demo app has its Spanish translation, compiled and current."""

import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.demo import queries, services
from apps.demo.models import Item, ItemLine
from base.tests.po import compiled_differences, config_texts, missing_from_catalogue, model_texts, untranslated

LOCALE = Path(apps.get_app_config("demo").path) / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, admin, choices, error messages)."""
    config = apps.get_app_config("demo")
    lazies = [
        # The public store's texts (round 16): register_apps writes them in en and es.
        *config_texts(config),
        queries.ITEM_NOT_FOUND,
        services.ITEM_DONE,
    ]
    lazies += model_texts((Item, ItemLine))
    lazies += list(Item.Status.labels)
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Demo by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=15, with_context=0) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(Item.Status.DONE.label) == "Hecho"
        assert str(services.ITEM_DONE) == "Este elemento está cerrado: ábrelo para añadir líneas."
        assert str(queries.ITEM_NOT_FOUND) == "Este elemento ya no existe."


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/demo/items/update",
        json.dumps({"id": str(uuid.uuid7()), "name": "x"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Este elemento ya no existe."
