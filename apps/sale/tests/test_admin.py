"""Django admin of the sale app: every table with full CRUD for the platform's staff (round 12, PLAN §17).

Ids and timestamps are shown, never typed; the database still refuses what no door may save (a negative
amount, a line that does not square, a change that is not tendered − amount).
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.sale import admin as sale_admin
from apps.sale.models import (
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    QuickNote,
    Refund,
    RefundLine,
    RefundPayment,
    Sale,
    SaleCounter,
    SaleLine,
    SalePayment,
    Settings,
)

MODELS = [
    PaymentMethod,
    Settings,
    Department,
    QuickNote,
    Order,
    OrderLine,
    Sale,
    SaleLine,
    SalePayment,
    SaleCounter,
    Refund,
    RefundPayment,
    RefundLine,
]


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_model_is_registered():
    for model in MODELS:
        assert model in admin.site._registry, model.__name__


def test_full_crud_for_the_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model.__name__
        assert model_admin.has_add_permission(request), model.__name__
        assert model_admin.has_change_permission(request), model.__name__
        assert model_admin.has_delete_permission(request), model.__name__


def test_ids_and_timestamps_are_read_only():
    for model in MODELS:
        readonly = set(admin.site._registry[model].readonly_fields)
        assert "id" in readonly, model.__name__
        for field in ("created_at", "updated_at"):
            if any(f.name == field for f in model._meta.get_fields()):
                assert field in readonly, (model.__name__, field)


def test_a_sale_shows_its_lines_and_payments_and_an_order_its_lines():
    assert admin.site._registry[Sale].inlines == [
        sale_admin.SaleLineInline,
        sale_admin.SalePaymentInline,
    ]
    assert admin.site._registry[Order].inlines == [sale_admin.OrderLineInline]
    assert admin.site._registry[Refund].inlines == [
        sale_admin.RefundPaymentInline,
        sale_admin.RefundLineInline,
    ]


def test_support_sees_and_repairs_the_service_and_the_voucher_of_a_line(superuser):
    request = request_by(superuser)
    voucher = {"service_id", "voucher_session_id", "voucher_grant_id", "voucher_name"}
    for model in (OrderLine, SaleLine):
        fields = set(admin.site._registry[model].get_fields(request))
        assert voucher <= fields, model.__name__
    assert {"voucher_remaining", "voucher_hold_until"} <= set(
        admin.site._registry[OrderLine].get_fields(request)
    )
