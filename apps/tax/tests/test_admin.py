"""Django admin of the tax app: categories, rules (with their components) and aliases, with full CRUD.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com, for
the platform's staff, and has full CRUD over every table, fiscal ones included. It replaces the «read
only» this app first copied from apps/demo. The database still refuses what no door may save: a rate
outside 0–100, a rate on a class that charges no tax, a backwards range and a root's twin.
"""

from dataclasses import replace
from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from live.models import OutboxEvent

from apps.tax import admin as tax_admin
from apps.tax.admin import (
    CHOOSE_A_HUB,
    ComponentInline,
    TaxAliasAdmin,
    TaxCategoryAdmin,
    TaxRuleAdmin,
    TaxSettingsAdmin,
)
from apps.tax.models import TaxAlias, TaxCategory, TaxRule, TaxSettings
from apps.tax.schemas import TAX_REGIONS


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
        # TAX-F11: the region is chosen from the business's country's tax territories, as on the screen.
        "/admin/tax/taxsettings/add/": '<option value="ES-CN">ES-CN · IGIC (Canary Islands)</option>'.encode(),
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


def test_the_business_tax_settings_are_in_the_admin(superuser):
    # TAX-F11: the staff sees and fixes the region a business keeps, as every other table of the app.
    registered = admin.site._registry[TaxSettings]
    assert isinstance(registered, TaxSettingsAdmin)
    request = request_by(superuser)
    assert all(
        check(request)
        for check in (
            registered.has_view_permission,
            registered.has_add_permission,
            registered.has_change_permission,
        )
    )
    # Never deleted: the row is the business's jurisdiction, and «Whole country» goes through the operation
    # (its event re-prices the open tills); deleting it would move the business in silence.
    assert registered.has_delete_permission(request) is False
    assert "region_code" in registered.list_display


@pytest.mark.django_db
def test_the_settings_row_cannot_be_deleted_from_the_admin(client, superuser):
    settings = TaxSettings.objects.create(region_code="ES-CN")
    on_a_hub(client, superuser)
    response = client.post(f"/admin/tax/taxsettings/{settings.pk}/delete/", {"post": "yes"}, HTTP_HOST="hubs.localhost")
    assert response.status_code == 403
    assert TaxSettings.objects.filter(pk=settings.pk, region_code="ES-CN").exists()


def test_the_staff_cannot_add_a_second_settings_row(superuser):
    # TAX-F11: one row at most (`tax_settings_single_row`); once it exists, «Add» disappears instead of
    # ending in the database's refusal.
    registered = admin.site._registry[TaxSettings]
    request = request_by(superuser)
    assert registered.has_add_permission(request) is True
    TaxSettings.objects.create(region_code="ES-CN")
    assert registered.has_add_permission(request) is False


SETTINGS_ADD = "/admin/tax/taxsettings/add/"


def settings_change(settings: TaxSettings) -> str:
    return f"/admin/tax/taxsettings/{settings.pk}/change/"


def on_a_hub(client, user):
    """The staff member signed in on the platform host, with hub ``a`` chosen as the SaaS admin's link does."""
    client.force_login(user)
    client.get("/admin/hub/a/", HTTP_HOST="hubs.localhost")
    return client


def test_the_region_is_one_of_the_territories_of_the_business_country(superuser):
    # TAX-F11: the same list the screen offers (the business's country's tax territories), plus none.
    form = admin.site._registry[TaxSettings].get_form(request_by(superuser))()
    assert [value for value, _label in form.fields["region_code"].choices] == ["", *TAX_REGIONS["ES"]]


@pytest.mark.django_db
@pytest.mark.parametrize("region", ["XX-99", "PT-20", "ES-MD"])
def test_a_region_the_business_country_has_not_is_the_fields_error(client, superuser, region):
    # TAX-F11: a region that does not exist, of another country or without taxes of its own would leave the
    # business charging the national VAT without warning: the admin refuses it and keeps nothing.
    settings = TaxSettings.objects.create(region_code="ES-CE")
    on_a_hub(client, superuser)
    changed = client.post(settings_change(settings), {"region_code": region}, HTTP_HOST="hubs.localhost")
    assert changed.status_code == 200
    assert "region_code" in changed.context["adminform"].form.errors
    settings.refresh_from_db()
    assert settings.region_code == "ES-CE"
    settings.delete()
    added = client.post(SETTINGS_ADD, {"region_code": region}, HTTP_HOST="hubs.localhost")
    assert added.status_code == 200
    assert "region_code" in added.context["adminform"].form.errors
    assert not TaxSettings.objects.exists()
    assert not OutboxEvent.objects.filter(name="tax.settings.updated").exists()


@pytest.mark.django_db
def test_a_territory_is_kept_through_its_operation(client, superuser):
    # TAX-F11: the admin keeps the region as the screen does (``tax.settings.update``): its actor and its event.
    on_a_hub(client, superuser)
    added = client.post(SETTINGS_ADD, {"region_code": "ES-CN", "_continue": "1"}, HTTP_HOST="hubs.localhost")
    assert added.status_code == 302
    settings = TaxSettings.objects.get()
    # The admin's log and its «Save and continue» point at the row the operation kept.
    assert added["Location"] == settings_change(settings)
    assert LogEntry.objects.get().object_id == str(settings.pk)
    assert (settings.region_code, settings.updated_by) == ("ES-CN", "root")
    changed = client.post(settings_change(settings), {"region_code": ""}, HTTP_HOST="hubs.localhost")
    assert changed.status_code == 302
    settings.refresh_from_db()
    assert settings.region_code == ""
    kept = OutboxEvent.objects.filter(name="tax.settings.updated").values_list("payload", flat=True)
    assert [payload["region_code"] for payload in kept] == ["ES-CN", None]


@pytest.mark.django_db
def test_without_a_chosen_hub_the_region_is_not_kept(client, superuser):
    settings = TaxSettings.objects.create(region_code="ES-CE")
    client.force_login(superuser)
    changed = client.post(settings_change(settings), {"region_code": "ES-CN"}, HTTP_HOST="hubs.localhost")
    assert changed.status_code == 200
    assert changed.context["adminform"].form.non_field_errors() == [str(CHOOSE_A_HUB)]
    settings.refresh_from_db()
    assert settings.region_code == "ES-CE"


@pytest.mark.django_db
def test_a_refusal_of_the_operation_is_the_forms_error(client, superuser, monkeypatch):
    # Any refusal of ``tax.settings.update`` (a permission, an inactive app) is told on the form, never a 500.
    staff_context = tax_admin._staff_context
    monkeypatch.setattr(
        tax_admin, "_staff_context", lambda request: replace(staff_context(request), permissions=frozenset())
    )
    settings = TaxSettings.objects.create(region_code="ES-CE")
    on_a_hub(client, superuser)
    changed = client.post(settings_change(settings), {"region_code": "ES-CN"}, HTTP_HOST="hubs.localhost")
    assert changed.status_code == 200
    assert "tax.manage" in changed.context["adminform"].form.errors["region_code"][0]
    settings.refresh_from_db()
    assert settings.region_code == "ES-CE"
