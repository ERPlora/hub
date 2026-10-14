"""Every visible text of the tax app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.core.validators import RegexValidator
from django.utils import translation

from apps.tax import queries, schemas, services
from apps.tax.models import SYSTEM_CATEGORY_LABELS, TaxAlias, TaxCategory, TaxRule

LOCALE = Path(apps.get_app_config("tax").path) / "locale" / "es" / "LC_MESSAGES"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals or contexts (the header is skipped).

    Line based: an entry starts at its ``#`` comments or its ``msgid``, so a header that is not
    followed by a blank line is not merged with the first entry.
    """
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            entries[msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = line.startswith("msgid ") or (line.startswith("#") and current == "msgstr")
        if starts_entry:
            flush()
            parts, fuzzy, current = {"msgid": [], "msgstr": []}, False, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


MESSAGES = [
    queries.CATEGORY_NOT_FOUND,
    queries.RULE_NOT_FOUND,
    queries.NO_RATE,
    schemas.REGION_UNKNOWN,
    schemas.REGION_OF_ANOTHER_COUNTRY,
    schemas.RATE_WITHOUT_TAX,
    schemas.RANGE_BACKWARDS,
    schemas.WHICH_RULE,
    services.CATEGORY_EXISTS,
    services.ALIAS_EXISTS,
    services.RULE_OVERLAPS,
    services.RULE_INCOHERENT,
    services.RULE_END_INVALID,
    services.RULE_EXISTS,
    services.RULE_ALREADY_ACTIVE,
    services.RULE_ALREADY_INACTIVE,
]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, errors)."""
    config = apps.get_app_config("tax")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *MESSAGES,
        *(v.message for v in TaxCategory._meta.get_field("key").validators if isinstance(v, RegexValidator)),
    ]
    for label in SYSTEM_CATEGORY_LABELS.values():
        lazies += [text for text in label if str(text)]
    for model in (TaxCategory, TaxRule, TaxAlias):
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        # The primary key comes from live.models.UUIDModel: its name is Django's, not a text of this app.
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    lazies += [*TaxRule.TaxType.labels, *TaxRule.OperationClass.labels, *TaxAlias.Source.labels]
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with translation.override("es"):
        assert str(TaxRule.OperationClass.SUBJECT_REVERSE.label) == "Inversión del sujeto pasivo"
        assert str(TaxRule.TaxType.IGIC.label) == "IGIC (Canarias)"
        assert str(TaxAlias.Source.SHIPPED.label) == "De fábrica"
        assert str(queries.NO_RATE) == "Ninguna regla fiscal se aplica a esta categoría en este país."
        assert str(services.RULE_ALREADY_ACTIVE) == "Esa regla ya está activa."
        assert str(apps.get_app_config("tax").verbose_name) == "Impuestos"


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
