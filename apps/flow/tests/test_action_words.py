"""Every action and read the automation editor offers has its own words in English and in Spanish (FLOW-F11).

The editor, the History and the «Ask me first» question name an action by ``flow.actions.<app>__<entity>__<verb>``
of ``frontend/locale/{en,es}.json`` (``actionLabel`` of ``frontend/lib/phrasing.ts``, ``queries.reasons.action_label``).
Without them the name is composed from the internal one, in English on a Spanish screen («set sold out · Inventory
(product)»), so this walks everything the editor can offer, the cancellations only «Ask me first» may use included.
"""

import json
from pathlib import Path

from django.apps import apps

from apps.flow import queries

from .conftest import A, HUB_DB

pytestmark = HUB_DB

LOCALE = Path(apps.get_app_config("flow").path) / "frontend" / "locale"


def actions(language: str) -> dict[str, str]:
    return json.loads((LOCALE / f"{language}.json").read_text(encoding="utf-8"))["flow"]["actions"]


def test_every_action_the_editor_offers_has_its_words_in_both_languages():
    en, es = actions("en"), actions("es")
    without_words = [
        name
        for name in sorted(queries.catalog.ask_first_catalog(A))
        if not (en.get(key := name.replace(".", "__"), "").strip() and es.get(key, "").strip())
    ]
    assert without_words == []
