"""Django admin of the cart_checkout app: carts with their lines, orders and the counter of the day, with
full CRUD.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com, for the
platform's staff, and has full CRUD over every table. The database still refuses what no door may save:
an unknown status, negative totals, a repeated live session code or order number.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from apps.cart_checkout.admin import CartAdmin, CartItemInline, OrderAdmin, OrderCounterAdmin
from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter

from base.admin import ADMIN_HUB_SESSION_KEY

from .conftest import make_cart, make_item, make_order


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_the_models_are_registered_and_the_lines_go_with_their_cart():
    assert isinstance(admin.site._registry[Cart], CartAdmin)
    assert isinstance(admin.site._registry[Order], OrderAdmin)
    assert isinstance(admin.site._registry[OrderCounter], OrderCounterAdmin)
    assert CartItemInline in CartAdmin.inlines
    assert CartItemInline.model is CartItem
    # The erasure of a customer's personal data, from carts and from orders.
    assert "erase_customer_data" in CartAdmin.actions
    assert "erase_customer_data" in OrderAdmin.actions


def test_full_crud_for_the_staff(superuser):
    request = request_by(superuser)
    for model in (Cart, Order, OrderCounter):
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert model_admin.has_add_permission(request)
        assert model_admin.has_change_permission(request)
        assert model_admin.has_delete_permission(request)


@pytest.mark.django_db
def test_the_pages_render(client, superuser):
    cart = make_cart("sess_admin", customer_email="ana@example.com")
    make_item(cart, product_name="Champú de prueba")
    order = make_order(cart, order_number="OS-20261014-0007")
    counter = OrderCounter.objects.create(day="2026-10-14", last=7)
    client.force_login(superuser)
    # The admin lives only on the platform host (PLAN §18.1.3).
    pages = {
        "/admin/cart_checkout/cart/": b"sess_admin",
        f"/admin/cart_checkout/cart/{cart.pk}/change/": b"Champ\xc3\xba de prueba",
        "/admin/cart_checkout/cart/add/": b"session_token",
        "/admin/cart_checkout/cart/?q=ana": b"sess_admin",
        "/admin/cart_checkout/order/": b"OS-20261014-0007",
        f"/admin/cart_checkout/order/{order.pk}/change/": b"failure_reason",
        "/admin/cart_checkout/order/?q=0007": b"OS-20261014-0007",
        "/admin/cart_checkout/ordercounter/": b"2026",
        f"/admin/cart_checkout/ordercounter/{counter.pk}/change/": b"last",
    }
    for path, content in pages.items():
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, path
        assert content in response.content, path


@pytest.mark.django_db
def test_the_staff_changes_a_cart(client, superuser):
    cart = make_cart("sess_admin")
    client.force_login(superuser)
    changed = client.post(
        f"/admin/cart_checkout/cart/{cart.pk}/change/",
        {
            "session_token": "sess_admin",
            "customer_email": "",
            "customer_name": "Ana",
            "status": "abandoned",
            "total_items": "0",
            "total_amount": "0",
            "currency": "EUR",
            "notes": "",
            "abandon_reason": "Staff",
            "created_by": "",
            "updated_by": "",
            "items-TOTAL_FORMS": "0",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
        },
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302
    cart.refresh_from_db()
    assert (cart.customer_name, cart.status) == ("Ana", "abandoned")


def staff_request(user, hub: str | None = "a"):
    request = RequestFactory().post("/admin/cart_checkout/cart/")
    request.user = user
    request.session = SessionStore()
    if hub:
        request.session[ADMIN_HUB_SESSION_KEY] = hub
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
def test_the_staff_erases_the_personal_data_of_the_selected_carts_customers(superuser):
    # CART_CHECKOUT-F14 from the admin: the same operation, once per customer email of the selection.
    ana = make_cart("sess_ana", customer_email="ana@example.com", customer_name="Ana")
    make_cart("sess_ana_2", customer_email="ana@example.com", customer_name="Ana")
    nameless = make_cart("sess_anon")
    order = make_order(make_cart("sess_x"), customer_email="ana@example.com", notes="door")
    request = staff_request(superuser)
    assert "erase_customer_data" in CartAdmin(Cart, admin.site).get_actions(request)
    CartAdmin(Cart, admin.site).erase_customer_data(request, Cart.objects.filter(pk__in=[ana.pk, nameless.pk]))
    assert list(Cart.objects.filter(customer_email="ana@example.com")) == []
    assert Order.objects.get(pk=order.pk).notes == ""
    said = [str(message) for message in request._messages]
    assert said == ["ana@example.com: personal data erased from 2 cart(s) and 1 order(s)."]


@pytest.mark.django_db
def test_without_a_chosen_hub_the_erasure_does_nothing(superuser):
    ana = make_cart("sess_ana", customer_email="ana@example.com")
    request = staff_request(superuser, hub=None)
    CartAdmin(Cart, admin.site).erase_customer_data(request, Cart.objects.all())
    assert Cart.objects.get(pk=ana.pk).customer_email == "ana@example.com"
    assert any("Choose a hub" in str(message) for message in request._messages)
