"""Django admin of the tax app: categories, rules (with their components) and aliases, with full CRUD.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com, for
the platform's staff, and has full CRUD over every table, fiscal ones included. It replaces the «read
only» this app first copied from apps/demo. The database still refuses what no door may save: a rate
outside 0–100, a rate on a class that charges no tax, a backwards range and a root's twin.
"""

from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.tax.admin import ComponentInline, TaxAliasAdmin, TaxCategoryAdmin, TaxRuleAdmin
from apps.tax.models import TaxAlias, TaxCategory, TaxRule


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_the_three_models_are_registered():
    assert isinstance(admin.site._registry[TaxCategory], TaxCategoryAdmin)
    assert isinstance(admin.site._registry[TaxRule], TaxRuleAdmin)
    assert isinstance(admin.site._registry[TaxAlias], TaxAliasAdmin)
    assert admin.site._registry[TaxRule].inlines == [ComponentInline]


def test_full_crud_for_the_staff(superuser):
    request = request_by(superuser)
    for model in (TaxCategory, TaxRule, TaxAlias):
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert model_admin.has_add_permission(request)
        assert model_admin.has_change_permission(request)
        assert model_admin.has_delete_permission(request)
    inline = ComponentInline(TaxRule, admin.site)
    assert inline.has_add_permission(request, None)
    assert inline.has_change_permission(request) and inline.has_delete_permission(request)


@pytest.mark.django_db
def test_the_pages_render(client, superuser):
    generic = TaxCategory.objects.get(key="product.generic")
    root = TaxRule.objects.get(category=generic, country_code="ES")
    TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("5.2"), parent=root, component_label="Recargo"
    )
    beer = TaxAlias.objects.get(alias="beer")
    client.force_login(superuser)

    # The admin lives only on the platform host (PLAN §18.1.3).
    pages = {
        "/admin/tax/taxcategory/": b"product.generic",
        "/admin/tax/taxrule/": b"product.generic",
        "/admin/tax/taxalias/": b"beer",
        f"/admin/tax/taxrule/{root.pk}/change/": b"Recargo",
        f"/admin/tax/taxcategory/{generic.pk}/change/": b"Product",
        f"/admin/tax/taxalias/{beer.pk}/change/": b"beer",
        "/admin/tax/taxcategory/add/": b"key",
        "/admin/tax/taxrule/add/": b"rate_pct",
        "/admin/tax/taxalias/add/": b"alias",
    }
    for path, content in pages.items():
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, path
        assert content in response.content, path


@pytest.mark.django_db
def test_the_staff_creates_and_changes_a_category(client, superuser):
    client.force_login(superuser)
    created = client.post(
        "/admin/tax/taxcategory/add/",
        {"key": "product.books", "name": "Books", "description": "", "is_active": "on"},
        HTTP_HOST="hubs.localhost",
    )
    assert created.status_code == 302
    books = TaxCategory.objects.get(key="product.books")
    changed = client.post(
        f"/admin/tax/taxcategory/{books.pk}/change/",
        {"key": "product.books", "name": "Libros", "description": "", "is_active": "on"},
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302
    books.refresh_from_db()
    assert books.name == "Libros"
