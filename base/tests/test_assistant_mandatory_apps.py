"""What the assistant knows of an app the business's country requires (VeriFactu in Spain, Taxes everywhere): once on,
it never goes off (BASE-F25, VERIFACTU-F32). ``base.app.get`` says so (``mandatory``, as the Apps screen's list), the
card of turning one on says it with the reason the Apps screen gives, and the descriptions of turning apps on and off
point the model at that datum, so it warns before the yes instead of saying it can be turned off later.
"""

from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.assistant import description
from live.operations import get

from base import activation
from base.business import country_name
from base.models import Hub
from base.services.apps import ONCE_ON
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.po import catalogue_key, po_entries, untranslated
from base.tests.test_services_assistant import call, run, turn

__all__ = ["in_business_a"]

pytestmark = HUB_DB
ADMIN = {"base.view_home", "base.administer_hub"}


def in_country(code: str) -> None:
    Hub.objects.filter(slug=A.key).update(country=code)


def never_off(app: str, country: str) -> str:
    """The reason the Apps screen gives for an app the country requires, in Spanish (``activation.MANDATORY_OFF``)."""
    with translation.override("es"):
        return activation.MANDATORY_OFF % {"app": app, "country": country_name(country, "es")}


def card_of_turning_on(app: str) -> list[tuple[str, str]]:
    plan = turn(call("base.app.enable", {"app": app}), permissions=ADMIN)
    assert plan["executed"] == []
    return [(field["name"], field["value"]) for field in plan["confirm"]["fields"]]


def test_the_card_of_turning_on_an_app_the_country_requires_says_it_never_goes_off():
    in_country("ES")
    assert card_of_turning_on("verifactu") == [("app", "VeriFactu"), ("mandatory", never_off("VeriFactu", "ES"))]


def test_a_business_without_a_country_is_in_spain_and_its_card_says_it_too():
    in_country("")
    assert card_of_turning_on("verifactu") == [("app", "VeriFactu"), ("mandatory", never_off("VeriFactu", "ES"))]


@pytest.mark.parametrize(("country", "app", "name"), [("PT", "verifactu", "VeriFactu"), ("ES", "reservation", "Reservas")])
def test_the_card_of_an_app_the_country_does_not_require_only_names_it(country, app, name):
    in_country(country)
    assert card_of_turning_on(app) == [("app", name)]


@pytest.mark.parametrize(
    ("country", "app", "mandatory"), [("ES", "verifactu", True), ("PT", "verifactu", False), ("ES", "reservation", False)]
)
def test_reading_an_app_says_whether_the_country_requires_it(country, app, mandatory):
    in_country(country)
    assert run("base.app.get", ADMIN, app=app)["mandatory"] is mandatory


@pytest.mark.parametrize("name", ["base.app.enable", "base.app.disable", "base.app.get"])
def test_the_descriptions_of_apps_point_the_model_at_the_datum_that_says_an_app_never_goes_off(name):
    said = description(get(name))
    assert "mandatory" in said
    assert "base.app.get" in said or name == "base.app.get"


def test_the_cards_word_for_that_reason_has_its_spanish():
    po = Path(apps.get_app_config("base").path) / "locale" / "es" / "LC_MESSAGES" / "django.po"
    key = catalogue_key(ONCE_ON)
    assert key in po_entries(po)
    assert key not in untranslated(po)
