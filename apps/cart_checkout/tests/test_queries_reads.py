"""What the reads share: a cart's status now, how a list pages, and how a person names a cart (by its id, its
session code or its customer, asked which one when several match)."""

import pytest
from live.errors import Conflict, NotFound

from apps.cart_checkout.models import Cart

from .conftest import HUB_DB, make_cart, run, tokens

pytestmark = [HUB_DB, pytest.mark.usefixtures("clock")]


def test_an_active_cart_past_its_expiry_reads_as_expired(shop):
    rows = {row.session_token: row.status for row in run("cart_checkout.cart.list").rows}
    assert rows == {"anon_2": "active", "anon_1": "expired", "sess_bea": "abandoned", "sess_ana": "active"}
    assert tokens(run("cart_checkout.cart.list", {"status": "expired"})) == ["anon_1"]
    assert tokens(run("cart_checkout.cart.list", {"status": "active"})) == ["anon_2", "sess_ana"]


def test_pages_never_overlap(shop):
    first = run("cart_checkout.cart.list", {"limit": 2})
    second = run("cart_checkout.cart.list", {"limit": 2, "offset": 2})
    assert tokens(first) + tokens(second) == ["anon_2", "anon_1", "sess_bea", "sess_ana"]
    assert first.total == second.total == 4


def test_a_cart_by_its_customer_or_its_id(shop):
    assert run("cart_checkout.cart.get", {"customer": "Bea@Example.com"}).id == shop["bea"].id
    assert run("cart_checkout.cart.get", {"cart_id": str(shop["old"].id)}).status == "expired"


def test_a_customer_with_several_carts_is_asked_which_one(shop):
    make_cart("sess_ana_2", customer_name="Ana Pérez")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.get", {"customer": "ana"})
    assert caught.value.code == "cart_checkout.cart_ambiguous"


def test_a_customer_with_old_carts_and_one_active_gets_the_active_one(shop):
    # «The cart of Ana» while Ana has a converted cart from last week: the assistant means the live one.
    make_cart("sess_ana_old", customer_email="ana@example.com", status="converted")
    assert run("cart_checkout.cart.get", {"customer": "ana@example.com"}).id == shop["ana"].id


def test_different_customers_matched_by_a_piece_of_the_name_are_asked_which_one(shop):
    # Review (ALTO): «ana» is a piece of «Mariana»; that only one of the two carts is active does not
    # make them the same person, so the active one is never picked for her (a delete, a line or an
    # order would go to someone else).
    Cart.objects.all().delete()
    make_cart("sess_ana", customer_name="Ana García", status="converted")
    make_cart("sess_mariana", customer_name="Mariana Ruiz")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.get", {"customer": "ana"})
    assert caught.value.code == "cart_checkout.cart_ambiguous"
    assert caught.value.message == "“ana” matches several carts: sess_ana, sess_mariana. Say which one."


def test_one_customer_by_name_with_an_old_cart_and_an_active_one_gets_the_active_one(shop):
    # The same full name (whatever the case and the spaces) is one customer: the live cart is meant.
    Cart.objects.all().delete()
    make_cart("sess_old", customer_name="ana  garcía", status="converted")
    active = make_cart("sess_new", customer_name="Ana García")
    assert run("cart_checkout.cart.get", {"customer": "garcía"}).id == active.id


def test_a_deleted_or_unknown_cart_is_not_found(shop):
    for said in ({"session_token": "sess_gone"}, {"session_token": "nope"}):
        with pytest.raises(NotFound) as caught:
            run("cart_checkout.cart.get", said)
        assert caught.value.code == "cart_checkout.cart_not_found"
