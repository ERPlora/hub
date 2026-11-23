"""The card of turning an app on or off from the assistant names, before the yes, the apps that go on or off with it
(BASE-F23, BASE-F24): what the change itself turns (``base.activation.enabling`` and ``disabling``), said as the Apps
screen's dialog says it, so a bar is never left without its floor plan by a card that only named Reservations.
"""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from base import activation
from base.models import Hub
from base.services import apps as app_services
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.po import catalogue_key, po_entries, untranslated
from base.tests.test_app_activation import rows, set_rows
from base.tests.test_services_assistant import answered, call, turn

__all__ = ["in_business_a"]

pytestmark = HUB_DB
ADMIN = {"base.view_home", "base.administer_hub"}
BASE = Path(apps.get_app_config("base").path)


def screen_says(key: str, count: int, language: str = "es", **values: str) -> str:
    """The Apps screen's words for ``key`` (``base/frontend/locale/<language>.json``), its «one | many» form for
    ``count`` as vue-i18n picks it."""
    text = json.loads((BASE / "frontend" / "locale" / f"{language}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        text = text[part]
    one, many = text.split(" | ")
    said = one if count == 1 else many
    for name, value in values.items():
        said = said.replace("{" + name + "}", value)
    return said


def the_rest_reservations_needs_chosen(**given: str) -> None:
    """Business A with what Reservations needs on and chosen, but those ``given`` (``on``, brought along; ``off``)."""
    needed = activation.needs(["reservation"], activation.module_graph()) - {"reservation"}
    set_rows(**({label: "on*" for label in needed} | given))


def card(operation: str, app: str) -> list[tuple[str, str]]:
    plan = turn(call(operation, {"app": app}), permissions=ADMIN)
    assert plan["executed"] == []
    return [(field["name"], field["value"]) for field in plan["confirm"]["fields"]]


def test_turning_reservations_off_names_the_apps_that_came_along_only_with_it():
    the_rest_reservations_needs_chosen(reservation="on*", table="on", schedule="on")
    along = screen_says("base.appsPage.confirmOff.along", 2, apps="Horarios y Mesas", app="Reservas")
    assert card("base.app.disable", "reservation") == [("app", "Reservas"), ("along", along)]


def test_one_app_along_is_said_as_one():
    the_rest_reservations_needs_chosen(reservation="on*", table="on", schedule="on*")
    along = screen_says("base.appsPage.confirmOff.along", 1, apps="Mesas", app="Reservas")
    assert card("base.app.disable", "reservation") == [("app", "Reservas"), ("along", along)]


def test_the_yes_turns_off_what_the_card_named_and_nothing_else():
    the_rest_reservations_needs_chosen(reservation="on*", table="on", schedule="on")
    yes = {"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"}
    plan = answered(call("base.app.disable", {"app": "reservation"}), decision=yes, permissions=ADMIN)
    assert plan["executed"][0]["outcome"] == "ok"
    still_on = activation.needs(["reservation"], activation.module_graph()) - {"reservation", "table", "schedule"}
    assert {label for label, row in rows().items() if row.on} == still_on


def test_an_app_the_business_chose_never_goes_off_with_it_and_the_card_only_names_the_app():
    the_rest_reservations_needs_chosen(reservation="on*", table="on*", schedule="on*")
    assert card("base.app.disable", "reservation") == [("app", "Reservas")]


def test_an_app_the_country_requires_stays_on_and_the_card_does_not_name_it():
    Hub.objects.filter(slug=A.key).update(country="ES")
    set_rows(sale="on*", customer="on", tax="on")
    along = screen_says("base.appsPage.confirmOff.along", 1, apps="Clientes", app="Ventas / TPV")
    assert card("base.app.disable", "sale") == [("app", "Ventas / TPV"), ("along", along)]


def test_an_app_another_one_on_needs_is_only_named_its_yes_says_which_goes_off_first():
    the_rest_reservations_needs_chosen(reservation="on*", table="on", schedule="on")
    assert card("base.app.disable", "table") == [("app", "Mesas")]


def test_turning_reservations_on_names_the_apps_it_needs_that_are_off():
    the_rest_reservations_needs_chosen(reservation="off", table="off", schedule="off")
    along = screen_says("base.appsPage.confirmOn.message", 2, app="Reservas", apps="Horarios y Mesas")
    assert card("base.app.enable", "reservation") == [("app", "Reservas"), ("along", along)]


def test_the_apps_that_come_along_are_named_in_the_order_of_their_names_as_the_screen_lists_them():
    set_rows()
    along = screen_says(
        "base.appsPage.confirmOn.message", 5, app="Reservas", apps="Clientes, Horarios, Impuestos, Mesas y Ventas / TPV"
    )
    assert card("base.app.enable", "reservation") == [("app", "Reservas"), ("along", along)]


def test_turning_on_an_app_the_country_requires_names_what_comes_along_and_then_that_it_never_goes_off():
    Hub.objects.filter(slug=A.key).update(country="ES")
    set_rows(tax="on*", sale="on*", customer="on*")
    fields = card("base.app.enable", "verifactu")
    along = screen_says("base.appsPage.confirmOn.message", 1, app="VeriFactu", apps="Facturación")
    assert [name for name, _ in fields] == ["app", "along", "mandatory"]
    assert fields[:2] == [("app", "VeriFactu"), ("along", along)]


def test_turning_on_an_app_whose_needs_are_on_only_names_it():
    the_rest_reservations_needs_chosen(reservation="off", table="on", schedule="on")
    assert card("base.app.enable", "reservation") == [("app", "Reservas")]


@pytest.mark.parametrize("operation", ["base.app.enable", "base.app.disable"])
def test_a_name_of_no_app_draws_no_card(operation):
    plan = turn(call(operation, {"app": "nothing-by-this-name"}), permissions=ADMIN)
    assert plan["confirm"] is None


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize(
    ("words", "key"),
    [("TURNS_ON_WITH", "base.appsPage.confirmOn.message"), ("TURNS_OFF_WITH", "base.appsPage.confirmOff.along")],
)
def test_the_card_says_what_goes_with_an_app_in_the_words_of_the_apps_screen(words, key, count, language):
    with translation.override(language):
        said = getattr(app_services, words) % {"count": count, "app": "Reservas", "apps": "Mesas"}
    assert said == screen_says(key, count, language, app="Reservas", apps="Mesas")


def test_the_cards_word_for_the_apps_along_has_its_spanish():
    po = BASE / "locale" / "es" / "LC_MESSAGES" / "django.po"
    key = catalogue_key(app_services.ALONG)
    assert key in po_entries(po)
    assert key not in untranslated(po)
