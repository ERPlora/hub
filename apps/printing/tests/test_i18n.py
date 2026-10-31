"""Every visible text of the printing app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.printing import documents, models, queries, schemas, services
from apps.printing.tests.conftest import RECEIPT

LOCALE = Path(apps.get_app_config("printing").path) / "locale" / "es" / "LC_MESSAGES"
TEMPLATE = Path(apps.get_app_config("printing").path) / "templates" / "printing" / "test_page.html"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped); an entry with a context
    (``pgettext``) is keyed as gettext compiles it, ``<context>\x04<msgid>``."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            context = _unescape("".join(parts["msgctxt"]))
            entries[f"{context}\x04{msgid}" if context else msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts = line.startswith("msgctxt ") or (line.startswith("msgid ") and current != "msgctxt")
        if starts or (line.startswith("#") and current == "msgstr"):
            flush()
            parts, fuzzy, current = {"msgctxt": [], "msgid": [], "msgstr": []}, fuzzy and current is None, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, admin, choices, messages and the titles
    of its schemas."""
    config = apps.get_app_config("printing")
    lazies = [config.verbose_name, config.summary, config.description, *(nav.label for nav in config.navigation)]
    for module in (queries, services, schemas, models, documents):
        lazies += [value for value in vars(module).values() if isinstance(value, Promise)]
    for model in config.get_models():
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
            and isinstance(field.verbose_name, Promise)
        ]
    lazies += [
        *models.Usage.labels,
        *models.Printer.Kind.labels,
        *models.Printer.Paper.labels,
        *models.PrintJob.Kind.labels,
        *models.PrintJob.Format.labels,
        *models.PrintJob.Status.labels,
    ]
    with translation.override("en"):
        texts = {source(text) for text in lazies}
    texts |= set(re.findall(r'{% translate "([^"]+)" %}', TEMPLATE.read_text()))
    return texts | schema_titles()


def source(text) -> str:
    """How the catalog keys a lazy text: its English, or ``context\x04English`` for a ``pgettext_lazy`` (a text that
    goes back to ``_()`` while its entry keeps the context is missing from the catalog: it would say another app's
    Spanish)."""
    args = getattr(text, "_args", ())
    return f"{args[0]}\x04{args[1]}" if len(args) == 2 else str(text)


def schema_titles() -> set[str]:
    """The titles printing's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones printing wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "printing"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy] == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("printing").verbose_name) == "Impresión"
        assert str(models.PrintJob.Status.FAILED.label) == "Fallido"
        assert str(services.PRINTER_EXISTS) == "Ya hay una impresora con ese nombre."


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/printing/printers",
        json.dumps({"name": "Caja", "kind": "network", "address": "no es una ip", "usage": "receipt"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "address": "Escribe una IP o un nombre de red válidos (por ejemplo 192.168.1.100)."
    }


def test_a_printer_and_a_job_say_their_own_words_in_spanish():
    """A printer is «activa» and a job «Cancelado», «cancelado el»: printing's words, never the ones of an earlier
    app that says the same English (auth's «activo», appointment's «Cancelada» and «cancelada el»), as the admin
    shows them (FIX-HUB-PRINTING-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP)."""
    with translation.override("es"):
        said = {
            "is_active": str(models.Printer._meta.get_field("is_active").verbose_name),
            "cancelled_at": str(models.PrintJob._meta.get_field("cancelled_at").verbose_name),
            "cancelled": str(dict(models.PrintJob._meta.get_field("status").choices)["cancelled"]),
        }
    assert said == {"is_active": "activa", "cancelled_at": "cancelado el", "cancelled": "Cancelado"}


@pytest.mark.django_db
def test_a_job_cancelled_meanwhile_is_refused_in_printing_s_words(client, make_user):
    """Cancelling or sending back a job someone already cancelled says it is «cancelado» (a job), not appointment's
    «cancelada»: the queue's cancel window and its notice show the server's refusal as it came
    (FIX-HUB-PRINTING-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP)."""
    client.force_login(make_user("boss", host="a", role="hub_admin"))

    def post(path: str, data: dict):
        return client.post(
            f"/api/printing/{path}",
            json.dumps(data),
            content_type="application/json",
            HTTP_HOST="a.localhost",
            HTTP_ACCEPT_LANGUAGE="es",
        )

    created = post("jobs", {"document_type": "receipt", "document": RECEIPT})
    assert created.status_code == 201
    job = {"job_id": created.json()["job"]["id"]}
    assert post("jobs/cancel", job).status_code == 200
    cancelled, retried = post("jobs/cancel", job), post("jobs/retry", job)
    assert (cancelled.status_code, retried.status_code) == (409, 409)
    assert cancelled.json()["error"]["message"] == (
        "Un trabajo que se está imprimiendo o ya se imprimió no se cancela; este está cancelado."
    )
    assert retried.json()["error"]["message"] == (
        "Solo vuelve a la cola un trabajo pendiente o fallido, o uno enviado que no contestó; este está cancelado."
    )
