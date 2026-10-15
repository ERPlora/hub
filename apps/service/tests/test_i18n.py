"""Every visible text of the service app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.service import queries, schemas, services
from apps.service.models import (
    Assignment,
    Category,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
)

LOCALE = Path(apps.get_app_config("service").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (
    ServiceSettings,
    Category,
    Service,
    Assignment,
    Package,
    PackageItem,
    Grant,
    GrantAdjustment,
    Redemption,
)
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
        if line.startswith("msgid ") or (line.startswith("#") and current == "msgstr"):
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


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``, alone, in a tuple or in a dict's values."""
    lazies = []
    for value in vars(module).values():
        items = (
            value.values()
            if isinstance(value, dict)
            else value
            if isinstance(value, tuple)
            else (value,)
        )
        for item in items:
            for leaf in item if isinstance(item, tuple) else (item,):
                if type(leaf).__name__ == "__proxy__":
                    lazies.append(leaf)
    return lazies


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("service")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    lazies += (
        lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    )
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    for choices in (
        Service.PricingType,
        Package.DiscountType,
        Grant.Source,
        Redemption.Status,
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


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        assert str(apps.get_app_config("service").verbose_name) == "Servicios"
        assert [
            str(nav.label) for nav in apps.get_app_config("service").navigation
        ] == [
            "Servicios",
            "Categorías",
            "Bonos y paquetes",
        ]
        assert (
            str(services.CATEGORY_NAME_TAKEN)
            == "Ya hay una categoría con ese nombre. Elige otro nombre."
        )
        assert (
            str(services.TAX_REQUIRED)
            == "Elige una categoría fiscal: sin ella el servicio no se puede cobrar."
        )
        assert (
            str(services.GRANT_IN_USE) == "Ese bono ya se ha usado: no se puede anular."
        )
        assert str(services.REDEEM_REFUSALS["expired"][1]) == "Este bono ha caducado."
        assert (
            str(queries.SERVICE_NOT_FOUND) == "Ese servicio no existe en este negocio."
        )
        assert str(schemas.SAY_WHICH_CUSTOMER) == (
            "Elige el cliente al que pertenece el bono: un bono sin dueño no lo puede canjear nadie."
        )
        assert [str(label) for label in Service.PricingType.labels] == [
            "Precio fijo",
            "Por hora",
            "Desde",
            "Variable",
            "Gratis",
        ]
        # The steps of a session in Movements (WORKBOOK «Pantallas»).
        assert [str(label) for label in Redemption.Status.labels] == [
            "Reservada",
            "Entregada",
            "Liberada",
            "Caducada",
            "Devuelta",
        ]
        assert str(services.SESSION_SETTLED) == (
            "Esa sesión del bono ya no se puede soltar: la venta está cobrada. Devolverla es una devolución."
        )
        assert str(services.HOLD_LOST) % {"name": "Bono 5"} == (
            "La sesión reservada de «Bono 5» ya no está reservada (pasó su día o se soltó). Quita el bono "
            "de la línea y vuelve a aplicarlo."
        )


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/service/categories/delete",
        json.dumps({"category": "Nothing"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "Esa categoría no existe en este negocio."
    )
