"""Django admin of the demo app: items with their lines, read only (every write is an operation)."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.demo.admin import ItemAdmin, ItemLineInline
from apps.demo.models import Item, ItemLine


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_item_is_registered_with_its_lines_inline():
    model_admin = admin.site._registry[Item]
    assert isinstance(model_admin, ItemAdmin)
    assert model_admin.inlines == [ItemLineInline]
    assert ItemLineInline.model is ItemLine


def test_read_only_even_for_a_superuser(superuser):
    request = request_by(superuser)
    item_admin, line_inline = admin.site._registry[Item], ItemLineInline(Item, admin.site)

    assert item_admin.has_view_permission(request) and line_inline.has_view_permission(request)
    assert not item_admin.has_add_permission(request)
    assert not line_inline.has_add_permission(request, None)
    for model_admin in (item_admin, line_inline):
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


@pytest.mark.django_db
def test_changelist_and_change_page_render(client, superuser):
    item = Item.objects.create(name="Table 1")
    ItemLine.objects.create(item=item, text="Coffee", qty=1, position=1)
    client.force_login(superuser)

    # The admin lives only on the platform host (PLAN §18.1.3).
    changelist = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost")
    change = client.get(f"/admin/demo/item/{item.pk}/change/", HTTP_HOST="hubs.localhost")

    assert changelist.status_code == 200 and b"Table 1" in changelist.content
    assert change.status_code == 200 and b"Coffee" in change.content
