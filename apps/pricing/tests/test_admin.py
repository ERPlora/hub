"""Django admin of the pricing app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event and checks no business rule.
"""

import uuid

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.pricing.admin import DiscountRuleAdmin, PriceItemAdmin, PriceItemInline, PriceListAdmin
from apps.pricing.models import DiscountRule, PriceItem, PriceList

from .conftest import make_item, make_list, make_product, make_rule

MODELS = {PriceList: PriceListAdmin, PriceItem: PriceItemAdmin, DiscountRule: DiscountRuleAdmin}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_model_is_registered():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert PriceListAdmin.inlines == [PriceItemInline]


def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


@pytest.mark.django_db
def test_a_list_is_added_and_changed_from_the_admin(client, superuser):
    client.force_login(superuser)
    added = client.post(
        "/admin/pricing/pricelist/add/",
        {
            "code": "VIP",
            "name": "VIP",
            "currency": "EUR",
            "tax_included": "unknown",
            "customer_group_id": "",
            "is_active": "on",
            "items-TOTAL_FORMS": "0",
            "items-INITIAL_FORMS": "0",
        },
        HTTP_HOST="hubs.localhost",
    )
    assert added.status_code == 302, added.content[:800]
    price_list = PriceList.objects.get()
    group = uuid.uuid7()
    changed = client.post(
        f"/admin/pricing/pricelist/{price_list.pk}/change/",
        {
            "code": "VIP",
            "name": "VIP members",
            "currency": "EUR",
            "tax_included": "true",
            "customer_group_id": str(group),
            "items-TOTAL_FORMS": "0",
            "items-INITIAL_FORMS": "0",
        },
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302, changed.content[:800]
    price_list.refresh_from_db()
    assert (price_list.name, price_list.tax_included, price_list.customer_group_id, price_list.is_active) == (
        "VIP members",
        True,
        group,
        False,
    )


@pytest.mark.django_db
def test_the_pages_render_on_the_platform_host(client, superuser):
    price_list = make_list("VIP", "VIP members")
    item = make_item(price_list, make_product("Shampoo", "SH-1"), price=1234)
    rule = make_rule("TEN", name="Ten off")
    client.force_login(superuser)
    for url, text in (
        ("/admin/pricing/pricelist/", b"VIP members"),
        (f"/admin/pricing/pricelist/{price_list.pk}/change/", b"1234"),
        ("/admin/pricing/priceitem/", b"1234"),
        (f"/admin/pricing/priceitem/{item.pk}/change/", b"1234"),
        ("/admin/pricing/discountrule/", b"Ten off"),
        (f"/admin/pricing/discountrule/{rule.pk}/change/", b"Ten off"),
        ("/admin/pricing/discountrule/add/", b"code"),
    ):
        response = client.get(url, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, url
        assert text in response.content, url


def rule_form(**fields):
    data = {
        "code": "VOL",
        "name": "Volume",
        "rule_type": "tiered",
        "applies_to": "all",
        "tiers": '[{"min_quantity": "3", "percent": "10"}, {"min_quantity": "6", "percent": "15"}]',
        "service_name": "",
        "priority": "100",
        "is_active": "on",
    }
    data.update(fields)
    return data


@pytest.mark.django_db
def test_the_admin_checks_the_tiers_of_a_rule(client, superuser):
    client.force_login(superuser)
    for tiers, message in (
        ('[{"min_quantity": "6", "percent": "10"}, {"min_quantity": "3", "percent": "15"}]', b"higher quantity"),
        ('[{"min_quantity": "3", "percent": "150"}]', b"100"),
        ('[{"min_quantity": "3"}]', b"percent"),
        ('{"min_quantity": "3"}', b"list"),
    ):
        refused = client.post("/admin/pricing/discountrule/add/", rule_form(tiers=tiers), HTTP_HOST="hubs.localhost")
        assert refused.status_code == 200, tiers
        assert message in refused.content, tiers
    assert not DiscountRule.objects.exists()
    added = client.post("/admin/pricing/discountrule/add/", rule_form(), HTTP_HOST="hubs.localhost")
    assert added.status_code == 302, added.content[:800]
    assert DiscountRule.objects.get().tiers == [
        {"min_quantity": "3", "percent": "10"},
        {"min_quantity": "6", "percent": "15"},
    ]
