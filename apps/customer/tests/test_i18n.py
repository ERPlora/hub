"""Every visible text of the customer app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.errors import InvalidPayload

from apps.customer import models, queries, schemas, services

from .conftest import run

LOCALE = Path(apps.get_app_config("customer").path) / "locale" / "es" / "LC_MESSAGES"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals or contexts (the header is skipped)."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            entries[msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = line.startswith("msgid ") or (
            line.startswith("#") and current == "msgstr"
        )
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


def lazy_texts_of(module) -> list[Promise]:
    """Every module-level lazy text: the messages an operation can send."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("customer")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *lazy_texts_of(schemas),
        *lazy_texts_of(queries),
        *lazy_texts_of(services),
    ]
    for model in config.get_models():
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        # The primary key comes from live.models.UUIDModel: its name is Django's default.
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    for choices in (
        models.Customer.Stage,
        models.Customer.Source,
        models.Customer.PreferredChannel,
        models.CustomField.FieldType,
        models.Activity.Kind,
        models.Purchase.Status,
        models.Consent.Channel,
        models.Consent.State,
        models.Consent.Source,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("customer").verbose_name) == "Clientes"
        assert str(models.Customer.Stage.LEAD.label) == "Contacto"
        assert str(models.Customer.Source.WALK_IN.label) == "En el local"
        assert (
            str(queries.CUSTOMER_UNAVAILABLE) == "Este cliente ya no está disponible."
        )
        assert str(services.PHONE_INVALID) == (
            "No es un teléfono válido de su país: revisa las cifras o escríbelo con su prefijo "
            "internacional (+44…)."
        )
        assert (
            str(services.GROUP_NAME_TAKEN)
            == "Ya hay un grupo con ese nombre. Elige otro nombre."
        )
        assert (
            str(services.HEALTH_CONSENT_REQUIRED)
            == "Registra antes su permiso para guardar datos de salud."
        )
        assert str(models.HealthRecord.TestResult.NEGATIVE.label) == "Negativa"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/customer/customers",
        json.dumps({"name": "Ana", "phone": "600111"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"]["phone"].startswith(
        "No es un teléfono válido de su país"
    )


def compiled(path: Path) -> dict[str, str]:
    """The singular entries of a compiled catalogue, as Django reads them (the header left out)."""
    with path.open("rb") as catalogue:
        entries = gettext.GNUTranslations(catalogue)._catalog
    return {key: text for key, text in entries.items() if isinstance(key, str) and key}


def test_what_an_earlier_app_also_translates_says_the_same_here():
    """Django joins every catalogue of a language in one, and the first app in ``INSTALLED_APPS`` wins a message
    two translate without context: ``live`` goes first, so the app's own wording never reached the user (a custom
    number field refused with live's «Introduce un número.», never with the app's); ``auth``'s «Correo
    electrónico» named the channel «Email» in the admin. What an app before this one says, this one says too."""
    configs = list(apps.get_app_configs())
    earlier = configs[: configs.index(apps.get_app_config("customer"))]
    ours = compiled(LOCALE / "django.mo")
    assert sorted(
        f"{message!r}: {config.label} «{text}», customer «{ours[message]}»"
        for config in earlier
        if (path := Path(config.path) / "locale" / "es" / "LC_MESSAGES" / "django.mo").exists()
        for message, text in compiled(path).items()
        if "\x04" not in message and message in ours and ours[message] != text
    ) == []


@pytest.mark.django_db
def test_a_custom_value_of_the_wrong_type_is_refused_in_spanish_under_its_field():
    """CUSTOMER-F04 «Si falla»: what the person reads in Spanish under each field."""
    visits = models.CustomField.objects.create(name="Visits", field_type="number")
    since = models.CustomField.objects.create(name="Since", field_type="date")
    ana = models.Customer.objects.create(name="Ana")
    sent = [
        {"field_id": visits.id, "value": "three"},
        {"field_id": since.id, "value": "2026-02-31"},
    ]
    with translation.override("es"):
        with pytest.raises(InvalidPayload) as refused:
            run("customer.customer.update", schemas.CustomerPatchIn(id=ana.id, field_values=sent))
        fields = {key: str(text) for key, text in refused.value.fields.items()}
    assert fields == {
        f"field_values.{visits.id}": "Introduce un número.",
        f"field_values.{since.id}": "Introduce una fecha válida.",
    }
    assert not models.CustomFieldValue.objects.filter(customer=ana).exists()


@pytest.mark.parametrize(
    ("key", "message"),
    [("invalidNumber", services.FIELD_INVALID_NUMBER), ("invalidDate", services.FIELD_INVALID_DATE)],
)
def test_what_the_card_cannot_read_is_worded_as_the_server_refuses_it(key, message):
    """A number or a date the browser cannot read is told by the form itself (it never reaches the server): in
    each language it says what the server says for the same value."""
    frontend = Path(apps.get_app_config("customer").path) / "frontend" / "locale"
    for language in ("en", "es"):
        texts = json.loads((frontend / f"{language}.json").read_text(encoding="utf-8"))
        with translation.override(language):
            assert texts["customer"]["form"][key] == str(message), language
