"""Putting a menu on sale or taking it off the till (COMBO-F03, hub#2216): the gesture of every day that another one
undoes, as the menu form's «On sale» switch. The assistant's card asks one tap for it, as for the other switches
(``inventory.product.set_sold_out``, ``staff.schedule.set_active``); typing the word stays for a change of the menu
itself, which may change how it is billed (BASE-F98)."""

import pytest
from live import assistant as shared
from live.errors import NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.combo.models import Combo
from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import TOP, offered_to, place_of_no_ask

from .conftest import HUB_DB, ctx_for, make_combo, run

pytestmark = HUB_DB

SET_ACTIVE = "combo.combo.set_active"
#: What the owner asked the assistant in the QA, word for word: both cards asked to type the word.
TONIGHT = ("Take the Menú del día off the till for tonight, we only do it at lunch.", "en")
TOMORROW = ("Vuelve a poner el menú del día a la venta, que mañana hay comidas.", "es")


def updated() -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name="combo.combo.updated").order_by("created_at", "id")]


def test_a_menu_goes_off_sale_and_back_and_nothing_else_of_it_changes():
    combo = make_combo("Menu of the day", price=1350, kitchen_name="MENU", sort_order=3)
    off = run(SET_ACTIVE, {"combo": "menu of the day", "is_active": False}, ctx_for(actor="ana"))
    combo.refresh_from_db()
    assert (off.is_active, combo.is_active, combo.updated_by) == (False, False, "ana")
    assert (combo.name, combo.price, combo.kitchen_name, combo.sort_order) == ("Menu of the day", 1350, "MENU", 3)
    assert run(SET_ACTIVE, {"id": str(combo.id), "is_active": True}).is_active is True
    assert updated() == [{"id": str(combo.id), "name": "Menu of the day"}] * 2


def test_saying_what_it_already_is_changes_nothing():
    make_combo("Menu of the day")
    run(SET_ACTIVE, {"combo": "Menu of the day", "is_active": True})
    assert updated() == []


def test_only_a_manager_puts_a_menu_on_sale_or_takes_it_off():
    make_combo("Menu of the day")
    with pytest.raises(PermissionDenied):
        run(SET_ACTIVE, {"combo": "Menu of the day", "is_active": False}, ctx_for("hub_employee"))
    assert Combo.objects.get().is_active is True


def test_a_menu_that_is_not_there_is_not_found():
    with pytest.raises(NotFound):
        run(SET_ACTIVE, {"combo": "brunch", "is_active": False})


# The assistant's card


def card_of(write: str, combo, language: str) -> dict:
    return assistant.cards.card(get(write), {"id": str(combo.id), "is_active": False}, language, ctx_for())


@pytest.mark.parametrize(("language", "menu", "on_sale"), [("en", "Menu", "On sale"), ("es", "Menú", "A la venta")])
def test_its_card_is_one_tap_saying_the_menu_and_that_it_goes_off_sale(language, menu, on_sale):
    combo = make_combo("Menú del día")
    card = card_of(SET_ACTIVE, combo, language)
    assert (card["risk"], card["confirm_word"], card["blocked"]) == ("normal", "", False)
    assert [(field["label"], field["value"]) for field in card["fields"]] == [(menu, "Menú del día"), (on_sale, False)]
    assert shared.confirmed(card, "")


@pytest.mark.parametrize(("language", "word"), [("en", "CONFIRM"), ("es", "CONFIRMAR")])
def test_a_change_of_the_menu_itself_still_asks_to_type_the_word(language, word):
    """Positive control: the same switch sent with the menu's change keeps its card, which may change how it is billed."""
    card = card_of("combo.combo.update", make_combo("Menú del día"), language)
    assert (card["risk"], card["confirm_word"]) == ("high", word)
    assert not shared.confirmed(card, "")


@pytest.mark.parametrize(("phrase", "language"), [TONIGHT, TOMORROW], ids=["en", "es"])
def test_the_owners_request_offers_the_switch_ahead_of_the_menus_change(catalog_of, phrase, language):
    tools = catalog_of(Membership.Role.OWNER, language)
    place = place_of_no_ask(tools, SET_ACTIVE, phrase, language)
    assert place is not None and place <= TOP, place
    assert "combo.combo.update" not in offered_to(tools, phrase, language)[: place - 1]
