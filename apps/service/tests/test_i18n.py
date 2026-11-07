"""Every visible text of the service app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.service import models, queries, schemas, services
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
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
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


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("service")
    lazies = [
        *config_texts(config),
        # The Home's step (FIX-SERVICE-SETUP-HOOKS).
        *(text for step in config.setup for text in (step.title, step.description)),
    ]
    lazies += module_texts(queries, services, schemas, models)
    lazies += model_texts(MODELS)
    for choices in (
        Service.PricingType,
        Package.DiscountType,
        Grant.Source,
        Redemption.Status,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("service")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Servicios by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=140, with_context=2) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_services_own_spanish():
    """A title service shares with an app installed before it («Tax category» with Inventory, «Duplicate customer» with
    Customers) is said with that app's Spanish, so service's own entry would be dead text: they have to say the same
    (hub#323)."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("service")
    assert {"Tax category", "Duplicate customer", "Services included"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


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
        assert (
            str(queries.SESSION_NOT_FOUND)
            == "Esa sesión del bono no existe en este negocio."
        )
        assert str(services.HOLD_LOST) % {"name": "Bono 5"} == (
            "La sesión reservada de «Bono 5» ya no está reservada (pasó su día o se soltó). Quita el bono "
            "de la línea y vuelve a aplicarlo."
        )


def test_spanish_says_services_own_words_not_an_earlier_apps():
    """The texts service shares in English with an app loaded before it come out in Spanish with service's words
    (hub#662): a voided voucher is «anulado por», as the voucher sold is masculine and its history says «Anulado por»,
    not Ventas' «anulada por»; a category is asked for and said ambiguous as its siblings (service, package,
    professional) are, «su id o su nombre» and «vale para varias», not Inventario's «su id, o su nombre» and «coincide
    con varias»; a session is «sesión del bono», as service's own titles and WORKBOOK say it, in the singular and in the
    plural."""
    texts = {
        "Grant.voided_by": Grant._meta.get_field("voided_by").verbose_name,
        "Redemption": Redemption._meta.verbose_name,
        "Redemption plural": Redemption._meta.verbose_name_plural,
        "SAY_WHICH_CATEGORY": schemas.SAY_WHICH_CATEGORY,
        "CATEGORY_AMBIGUOUS": queries.CATEGORY_AMBIGUOUS,
    }
    with translation.override("es"):
        said = {name: str(text) for name, text in texts.items()}
    said["CATEGORY_AMBIGUOUS"] %= {"said": "Pelo", "names": "Pelo corto, Pelo largo"}
    assert said == {
        "Grant.voided_by": "anulado por",
        "Redemption": "sesión del bono",
        "Redemption plural": "sesiones del bono",
        "SAY_WHICH_CATEGORY": "Di qué categoría: su id o su nombre.",
        "CATEGORY_AMBIGUOUS": "«Pelo» vale para varias categorías: Pelo corto, Pelo largo. Di cuál.",
    }


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
