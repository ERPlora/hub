"""Django admin of the inventory app: full CRUD for support (round 12, PLAN §17).

Round 12 derogates the «read only» that demo copies: the Hub admin, on hubs.erplora.com and for the
staff only, adds, changes and deletes every table of a hub, the stock ledger included, so that support
can repair; it is a second write path that warns rather than prevents (PLAN §17.1, PLAN-DB §16).
"""

from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.inventory.admin import CategoryAdmin, ProductAdmin, ProductCategoryInline, SaleStockAdmin, SettingsAdmin, StockMovementAdmin
from apps.inventory.models import Category, Product, ProductCategory, SaleStock, Settings, StockMovement

MODELS = {
    Product: ProductAdmin,
    Category: CategoryAdmin,
    StockMovement: StockMovementAdmin,
    Settings: SettingsAdmin,
    SaleStock: SaleStockAdmin,
}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_model_is_registered_and_products_show_their_categories():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert ProductAdmin.inlines == [ProductCategoryInline]
    assert ProductCategoryInline.model is ProductCategory


def test_full_crud_for_a_superuser(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model
    inline = ProductCategoryInline(Product, admin.site)
    assert inline.has_add_permission(request, None) and inline.has_change_permission(request)


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser):
    product = Product.objects.create(name="Coffee", sku="CAF", price=150, stock=Decimal("3"))
    category = Category.objects.create(name="Drinks")
    ProductCategory.objects.create(product=product, category=category)
    movement = StockMovement.objects.create(product=product, movement_type="initial", qty=3, stock_after=3)
    client.force_login(superuser)

    # The admin lives only on the platform host (PLAN §18.1.3).
    for path, text in (
        ("/admin/inventory/product/", b"Coffee"),
        (f"/admin/inventory/product/{product.pk}/change/", b"Drinks"),
        ("/admin/inventory/category/", b"Drinks"),
        ("/admin/inventory/stockmovement/", b"CAF"),
        (f"/admin/inventory/stockmovement/{movement.pk}/change/", b"Coffee"),
        ("/admin/inventory/settings/", b"0"),
        ("/admin/inventory/salestock/", b"0"),
        ("/admin/inventory/product/add/", b"sku"),
        ("/admin/inventory/category/add/", b"slug"),
        ("/admin/inventory/stockmovement/add/", b"stock_after"),
        ("/admin/inventory/settings/add/", b"track_stock"),
        ("/admin/inventory/salestock/add/", b"sale_id"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path


@pytest.mark.django_db
def test_support_can_repair_a_row_through_the_admin(client, superuser):
    category = Category.objects.create(name="Drnks", slug="drnks")
    client.force_login(superuser)
    data = {
        "name": "Drinks",
        "slug": "drinks",
        "description": "",
        "icon": "ion:cube-outline",
        "color": "#3880ff",
        "order": "0",
        "tax_category": "",
        "is_deleted": "",
        "deleted_at_0": "",
        "deleted_at_1": "",
        "created_by": "",
        "updated_by": "",
    }

    response = client.post(f"/admin/inventory/category/{category.pk}/change/", data, HTTP_HOST="hubs.localhost")

    assert response.status_code == 302, response.content[:2000]
    category.refresh_from_db()
    assert (category.name, category.slug) == ("Drinks", "drinks")
