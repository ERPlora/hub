"""The card of a write of Payments that names its payment method in the person's words says the method that the write
will use, as the same search finds it, never the words said (PAYMENT-F08, BASE-F97).

With «Cuenta BBVA 4821» as the business's method, «al método del BBVA cámbiale el nombre» drew «Change in Payments:
BBVA · BBVA QA proveedores», and the person could not see which method would change (hub#2290). Words that fit several
methods, or none, draw no card: the model hears why and asks.
"""

import dataclasses
import datetime as dt

import pytest

from apps.payment.models import Payment, PaymentMethod
from apps.payment.tests.conftest import HUB_DB, ctx_for, make_method
from base.tests.test_assistant_yes_for_its_card import (
    no_card_but_the_model_hears,
    said,
    the_model_hears,
    turn_as,
    yes_to,
)
from base.tests.test_services_assistant import call

pytestmark = HUB_DB

A_PAYMENT = {
    "payment_date": dt.date(2026, 11, 23).isoformat(),
    "amount": 120_00,
    "beneficiary_name": "Makro",
}
#: Each write the assistant offers that takes its method in the person's words, with the rest of its data right.
ON_A_METHOD_SAID = {
    "payment.method.update": {"method": "BBVA", "name": "BBVA QA proveedores"},
    "payment.method.deactivate": {"method": "BBVA"},
    "payment.payment.create": {"method": "BBVA", **A_PAYMENT},
}


@pytest.fixture
def bbva():
    """The business of the issue: its one method is «Cuenta BBVA 4821»."""
    return make_method("Cuenta BBVA 4821", bank_account_ref="ES12 **** 4821")


def owner(language: str = "es"):
    return dataclasses.replace(ctx_for("hub_admin"), language=language)


def turn(write: str, arguments: dict, language: str = "es") -> dict:
    return turn_as(owner(language), call(write, arguments))


def test_the_card_of_a_method_renamed_by_the_persons_words_names_the_method_the_search_finds(bbva):
    """The case of the issue: «BBVA» is «Cuenta BBVA 4821», and the new name comes after it."""
    for language in ("es", "en"):
        plan = turn("payment.method.update", ON_A_METHOD_SAID["payment.method.update"], language)
        assert said(plan)[:2] == [("method", "Cuenta BBVA 4821"), ("name", "BBVA QA proveedores")]


def test_the_yes_to_that_card_renames_the_method_it_named(bbva):
    plan = turn("payment.method.update", ON_A_METHOD_SAID["payment.method.update"])
    yes_to(plan, turn_of=lambda *calls, decision: turn_as(owner(), *calls, decision=decision))
    bbva.refresh_from_db()
    assert bbva.name == "BBVA QA proveedores"


def test_an_inactive_method_turned_on_by_the_persons_words_is_named_on_its_card(bbva):
    PaymentMethod.objects.filter(pk=bbva.pk).update(is_active=False)
    assert dict(said(turn("payment.method.activate", {"method": "BBVA"})))["method"] == "Cuenta BBVA 4821"


@pytest.mark.parametrize("write", ON_A_METHOD_SAID)
def test_every_write_that_takes_a_method_in_words_names_the_one_it_finds(bbva, write):
    assert dict(said(turn(write, ON_A_METHOD_SAID[write])))["method"] == "Cuenta BBVA 4821"


@pytest.mark.parametrize("write", [*ON_A_METHOD_SAID, "payment.method.activate"])
def test_words_that_fit_two_methods_draw_no_card_and_the_model_hears_which(bbva, write):
    make_method("BBVA empresa")
    arguments = ON_A_METHOD_SAID.get(write, {"method": "BBVA"})
    plan = turn(write, arguments)
    no_card_but_the_model_hears(plan, "payment.method_ambiguous")
    heard = the_model_hears(plan)["message"]
    assert "Cuenta BBVA 4821" in heard and "BBVA empresa" in heard


@pytest.mark.parametrize("write", [*ON_A_METHOD_SAID, "payment.method.activate"])
def test_words_that_fit_no_method_draw_no_card(bbva, write):
    arguments = {**ON_A_METHOD_SAID.get(write, {}), "method": "Sabadell"}
    no_card_but_the_model_hears(turn(write, arguments), "payment.method_not_found")


def test_a_payment_from_a_method_that_is_off_draws_no_card(bbva):
    PaymentMethod.objects.filter(pk=bbva.pk).update(is_active=False)
    plan = turn("payment.payment.create", ON_A_METHOD_SAID["payment.payment.create"])
    no_card_but_the_model_hears(plan, "payment.method_inactive")
    assert not Payment.objects.exists()


def test_words_beside_the_methods_id_are_neither_read_nor_shown(bbva):
    """The write takes the method by its id then: the card names that one, never the one the words would find."""
    make_method("BBVA empresa")
    shown = dict(said(turn("payment.method.update", {"id": str(bbva.id), "method": "BBVA empresa", "name": "Otra"})))
    assert (shown["id"], "method" in shown) == ("Cuenta BBVA 4821", False)
