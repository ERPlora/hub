"""Django admin of the payment app: methods, payments and the counter of the day, with full CRUD.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com, for
the platform's staff, and has full CRUD over every table. The database still refuses what no door may
save: an amount of 0 or less, an unknown status, a repeated reference or method name.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.payment.admin import PaymentAdmin, PaymentCounterAdmin, PaymentMethodAdmin
from apps.payment.models import Payment, PaymentCounter, PaymentMethod

from .conftest import make_method, make_payment


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_the_three_models_are_registered():
    assert isinstance(admin.site._registry[PaymentMethod], PaymentMethodAdmin)
    assert isinstance(admin.site._registry[Payment], PaymentAdmin)
    assert isinstance(admin.site._registry[PaymentCounter], PaymentCounterAdmin)


def test_full_crud_for_the_staff(superuser):
    request = request_by(superuser)
    for model in (PaymentMethod, Payment, PaymentCounter):
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert model_admin.has_add_permission(request)
        assert model_admin.has_change_permission(request)
        assert model_admin.has_delete_permission(request)


@pytest.mark.django_db
def test_the_pages_render(client, superuser):
    payment = make_payment(
        make_method("BBVA account"), beneficiary_name="Proveedor Norte SL"
    )
    counter = PaymentCounter.objects.create(day=payment.payment_date, last=1)
    client.force_login(superuser)
    # The admin lives only on the platform host (PLAN §18.1.3).
    pages = {
        "/admin/payment/paymentmethod/": b"BBVA account",
        "/admin/payment/payment/": b"PAY-20261014-0001",
        "/admin/payment/paymentcounter/": b"2026",
        f"/admin/payment/paymentmethod/{payment.method_id}/change/": b"BBVA account",
        f"/admin/payment/payment/{payment.pk}/change/": b"Proveedor Norte SL",
        f"/admin/payment/paymentcounter/{counter.pk}/change/": b"last",
        "/admin/payment/paymentmethod/add/": b"bank_account_ref",
        "/admin/payment/payment/add/": b"beneficiary_name",
        f"/admin/payment/payment/{payment.pk}/change/?trail": b"approved_by",
        "/admin/payment/payment/?q=norte": b"PAY-20261014-0001",
    }
    for path, content in pages.items():
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, path
        assert content in response.content, path


@pytest.mark.django_db
def test_the_staff_creates_and_changes_a_method(client, superuser):
    client.force_login(superuser)
    created = client.post(
        "/admin/payment/paymentmethod/add/",
        {
            "name": "Cash drawer",
            "method_type": "cash",
            "bank_account_ref": "",
            "is_active": "on",
        },
        HTTP_HOST="hubs.localhost",
    )
    assert created.status_code == 302
    method = PaymentMethod.objects.get(name="Cash drawer")
    changed = client.post(
        f"/admin/payment/paymentmethod/{method.pk}/change/",
        {"name": "Till cash", "method_type": "cash", "bank_account_ref": ""},
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302
    method.refresh_from_db()
    assert (method.name, method.is_active) == ("Till cash", False)
