"""Every visible text of the payment app has its Spanish translation, compiled and current (the old
module's `every_string_has_its_translation` gate, for the server's texts; the pages' texts are
frontend/locale/locale.test.ts)."""

import gettext
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.payment import queries, schemas, services
from apps.payment.models import Payment, PaymentCounter, PaymentMethod
from base.tests.po import po_entries

LOCALE = Path(apps.get_app_config("payment").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (PaymentMethod, Payment, PaymentCounter)


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``."""
    return [
        value for value in vars(module).values() if type(value).__name__ == "__proxy__"
    ]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("payment")
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
    lazies += list(PaymentMethod.Type.labels) + list(Payment.Status.labels)
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
    assert (
        len(visible_texts()) > 50
    )  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    config = apps.get_app_config("payment")
    with translation.override("es"):
        assert str(config.verbose_name) == "Pagos"
        assert [str(nav.label) for nav in config.navigation] == ["Pagos", "Métodos"]
        assert [str(label) for label in Payment.Status.labels] == [
            "Borrador",
            "Aprobado",
            "Enviado",
            "Completado",
            "Cancelado",
        ]
        assert [str(label) for label in PaymentMethod.Type.labels] == [
            "Efectivo",
            "Transferencia",
            "Tarjeta",
            "SEPA",
            "Cheque",
            "Otro",
        ]
        assert str(services.NOT_CANCELLABLE) == "El pago ya no admite cancelación."
        assert str(services.METHOD_INACTIVE) == (
            "Ese método de pago está desactivado: elige uno activo."
        )
        assert str(services.METHOD_NAME_TAKEN) == (
            "Ya hay un método de pago con ese nombre. Elige otro nombre."
        )
        assert (
            str(queries.METHOD_NOT_FOUND)
            == "Ese método de pago no existe en este negocio."
        )
        assert str(queries.METHOD_AMBIGUOUS) % {
            "said": "Caja",
            "names": "Caja 1, Caja 2",
        } == ("“Caja” encaja con varios métodos de pago: Caja 1, Caja 2. Di cuál.")
