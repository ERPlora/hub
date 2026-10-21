"""Django admin of the demo app: full CRUD on items and their lines, for the platform's staff.

Round 12 (PLAN §17, PLAN-HUB §3.2, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a
hub's tables but the fiscal ones. A raw admin write records no event, as in every other app's admin.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from live.models import OutboxEvent

from apps.demo.admin import ItemAdmin, ItemLineInline
from apps.demo.models import Item, ItemLine

HOST = {"HTTP_HOST": "hubs.localhost"}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def on_a_hub(client, user):
    """The staff member signed in on the platform host, with hub ``a`` chosen as the SaaS admin's link does."""
    client.force_login(user)
    client.get("/admin/hub/a/", **HOST)
    return client


def lines_form(*lines: dict, initial: int = 0) -> dict:
    """The inline formset of an item's lines (prefix ``lines``, its ``related_name``) with ``lines``."""
    data = {
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": str(initial),
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for n, line in enumerate(lines):
        data.update({f"lines-{n}-{field}": value for field, value in line.items()})
    return data


def test_item_is_registered_with_its_lines_inline():
    model_admin = admin.site._registry[Item]
    assert isinstance(model_admin, ItemAdmin)
    assert model_admin.inlines == [ItemLineInline]
    assert ItemLineInline.model is ItemLine


def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    item_admin, line_inline = admin.site._registry[Item], ItemLineInline(Item, admin.site)
    assert item_admin.has_add_permission(request) and line_inline.has_add_permission(request, None)
    for model_admin in (item_admin, line_inline):
        assert model_admin.has_view_permission(request), model_admin
        assert model_admin.has_change_permission(request), model_admin
        assert model_admin.has_delete_permission(request), model_admin


@pytest.mark.django_db
def test_an_item_and_its_lines_are_added_changed_and_deleted_from_the_admin(client, superuser):
    on_a_hub(client, superuser)
    coffee = lines_form({"position": "1", "text": "Coffee", "qty": "2"})
    added = client.post("/admin/demo/item/add/", {"name": "Table 4", "status": "open", "note": "", **coffee}, **HOST)
    assert added.status_code == 302, added.content[:800]
    item = Item.objects.get()
    line = item.lines.get()
    assert (item.name, line.text, line.qty, line.position) == ("Table 4", "Coffee", 2, 1)

    tea = lines_form({"id": str(line.pk), "item": str(item.pk), "position": "1", "text": "Tea", "qty": "1"}, initial=1)
    changed = client.post(
        f"/admin/demo/item/{item.pk}/change/", {"name": "Table 4", "status": "done", "note": "Paid", **tea}, **HOST
    )
    assert changed.status_code == 302, changed.content[:800]
    item.refresh_from_db()
    line.refresh_from_db()
    assert (item.status, item.note, line.text, line.qty) == ("done", "Paid", "Tea", 1)

    deleted = client.post(f"/admin/demo/item/{item.pk}/delete/", {"post": "yes"}, **HOST)
    assert deleted.status_code == 302
    assert not Item.objects.exists() and not ItemLine.objects.exists()
    # A raw admin write records no event (the convention of the Hub admin; the screens follow the operations).
    assert not OutboxEvent.objects.filter(name__startswith="demo.").exists()


@pytest.mark.django_db
def test_changelist_and_change_page_render(client, superuser):
    item = Item.objects.create(name="Table 1")
    ItemLine.objects.create(item=item, text="Coffee", qty=1, position=1)
    on_a_hub(client, superuser)

    # The admin lives only on the platform host (PLAN §18.1.3).
    changelist = client.get("/admin/demo/item/", **HOST)
    change = client.get(f"/admin/demo/item/{item.pk}/change/", **HOST)
    add = client.get("/admin/demo/item/add/", **HOST)

    assert changelist.status_code == 200 and b"Table 1" in changelist.content
    assert change.status_code == 200 and b"Coffee" in change.content
    assert add.status_code == 200 and b"Hub: a" in add.content
