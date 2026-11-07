"""Every visible text of the payment app has its Spanish translation, compiled and current (the old
module's `every_string_has_its_translation` gate, for the server's texts; the pages' texts are
frontend/locale/locale.test.ts)."""

from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.payment import queries, schemas, services
from apps.payment.models import Payment, PaymentCounter, PaymentMethod
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    untranslated,
)

LOCALE = Path(apps.get_app_config("payment").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (PaymentMethod, Payment, PaymentCounter)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("payment")
    lazies = [
        *config_texts(config),
    ]
    lazies += module_texts(queries, services, schemas)
    lazies += model_texts(MODELS)
    lazies += list(PaymentMethod.Type.labels) + list(Payment.Status.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Cobros by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=50, with_context=18) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


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
