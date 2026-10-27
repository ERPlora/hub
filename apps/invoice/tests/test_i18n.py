"""Every visible text of the invoice app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.core.validators import RegexValidator
from django.utils import translation
from live.operations import registry

from apps.invoice import platform, queries, schemas, services
from apps.invoice.models import (
    FACTORY_SERIES_NAMES,
    Invoice,
    InvoiceLine,
    InvoiceSeries,
    InvoiceType,
    Issuer,
)

APP = Path(apps.get_app_config("invoice").path)
LOCALE = APP / "locale" / "es" / "LC_MESSAGES"
TEMPLATE = APP / "templates" / "invoice" / "invoice.html"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped); an entry with a
    context is keyed as gettext keeps it compiled, ``context\x04msgid``."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        context = _unescape("".join(parts["msgctxt"]))
        if msgid:
            key = f"{context}\x04{msgid}" if context else msgid
            entries[key] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = line.startswith("msgctxt ") or (
            line.startswith("msgid ") and current != "msgctxt"
        ) or (line.startswith("#") and current == "msgstr")
        if starts_entry:
            flush()
            parts, fuzzy, current = {"msgctxt": [], "msgid": [], "msgstr": []}, False, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def messages_of(module) -> list:
    """Every lazy text a module keeps at its top level (its error messages, its labels)."""
    lazies = [
        value
        for name, value in vars(module).items()
        if name.isupper() and type(value).__name__ == "__proxy__"
    ]
    for name, value in vars(module).items():
        if name.isupper() and isinstance(value, dict):
            lazies += [
                item for item in value.values() if type(item).__name__ == "__proxy__"
            ]
    return lazies


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, errors, paper)."""
    config = apps.get_app_config("invoice")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *messages_of(queries),
        *messages_of(schemas),
        *messages_of(services),
        *messages_of(platform),
        *(label for _english, label in FACTORY_SERIES_NAMES.values()),
        *(
            v.message
            for v in InvoiceSeries._meta.get_field("code").validators
            if isinstance(v, RegexValidator)
        ),
        *InvoiceType.labels,
        *Invoice.Status.labels,
        *Invoice.Source.labels,
        *Invoice.RectificationKind.labels,
        *Issuer.Source.labels,
    ]
    for model in (InvoiceSeries, Issuer, Invoice, InvoiceLine):
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    template = TEMPLATE.read_text(encoding="utf-8")
    with translation.override("en"):
        return (
            {str(text) for text in lazies}
            | set(re.findall(r'{% translate "([^"]+)" %}', template))
            | schema_titles()
        )


def schema_titles() -> set[str]:
    """The titles invoice's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. A title pydantic makes up from the field is not one."""
    titles = set()
    for op in registry.values():
        if op.app_label == "invoice":
            for name, prop in op.input.model_json_schema().get("properties", {}).items():
                title = prop.get("title")
                if title and title != name.title().replace("_", " "):
                    titles.add(title)
    return titles


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ] == []


def test_every_visible_text_is_in_the_catalog():
    # A text with its own context (the invoice's statuses) counts by its English source.
    catalog = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - catalog == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("invoice").verbose_name) == "Facturación"
        assert (
            str(queries.CANNOT_RECTIFY_RECTIFICATION)
            == "Una rectificativa no se puede rectificar."
        )
        assert str(queries.ALREADY_CANCELLED) == "La factura ya está cancelada."
        assert str(Invoice.Status.ISSUED.label) == "Emitida"
        assert str(queries.DOC_SIMPLIFIED) == "Factura simplificada"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/invoice/invoices",
        json.dumps(
            {
                "lines": [
                    {
                        "description": "x",
                        "quantity": "1",
                        "unit_price": 1,
                        "tax_rate": "21",
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert response.json()["error"]["message"].startswith("Configura el emisor")
