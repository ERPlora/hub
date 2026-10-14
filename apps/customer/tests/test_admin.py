"""Django admin of the customer app: every table, with full CRUD for the platform's staff.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub admin, only on ``hubs.erplora.com``, has
full CRUD over a hub's tables. That supersedes the «read only» the demo app (and an earlier version
of this one) copied from round 9.
"""

import uuid

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.customer.admin import (
    ActivityAdmin,
    ConsentAdmin,
    ConsentInline,
    CustomerAdmin,
    CustomerGroupAdmin,
    CustomerTagAdmin,
    CustomFieldAdmin,
    CustomFieldValueInline,
    OrderLinkAdmin,
    PurchaseAdmin,
    PurchaseInline,
)
from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomField,
    CustomFieldValue,
    OrderLink,
    Purchase,
)

REGISTERED = {
    Customer: CustomerAdmin,
    CustomerGroup: CustomerGroupAdmin,
    CustomerTag: CustomerTagAdmin,
    CustomField: CustomFieldAdmin,
    Activity: ActivityAdmin,
    Purchase: PurchaseAdmin,
    Consent: ConsentAdmin,
    OrderLink: OrderLinkAdmin,
}
HOST = "hubs.localhost"  # the admin lives only on the platform host (PLAN §18.1.3)


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_table_is_registered():
    for model, model_admin in REGISTERED.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert CustomerAdmin.inlines == [
        CustomFieldValueInline,
        PurchaseInline,
        ConsentInline,
    ]


def test_the_staff_has_full_crud_on_every_table(superuser):
    # Round 12: no read-only mixin; what the staff may do is Django's own permissions.
    request = request_by(superuser)
    admins = [admin.site._registry[model] for model in REGISTERED]
    inlines = [inline(Customer, admin.site) for inline in CustomerAdmin.inlines]
    for model_admin in admins:
        assert model_admin.has_add_permission(request), model_admin
        assert model_admin.has_change_permission(request), model_admin
        assert model_admin.has_delete_permission(request), model_admin
    for inline in inlines:
        assert inline.has_add_permission(
            request, None
        ) and inline.has_change_permission(request)


@pytest.mark.django_db
def test_the_lists_and_a_card_render(client, superuser):
    ana = Customer.objects.create(name="Ana García", phone="+34600111222")
    field = CustomField.objects.create(name="Allergies")
    CustomFieldValue.objects.create(customer=ana, field=field, value="Latex")
    Purchase.objects.create(customer=ana, sale_id=uuid.uuid7(), amount=1250)
    Consent.objects.create(customer=ana, channel="email", state="granted")
    Activity.objects.create(customer=ana, kind="note_added", text="Prefers mornings")
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana)
    CustomerGroup.objects.create(name="VIP")
    CustomerTag.objects.create(name="Moroso")
    client.force_login(superuser)

    for model in REGISTERED:
        assert (
            client.get(
                f"/admin/customer/{model._meta.model_name}/", HTTP_HOST=HOST
            ).status_code
            == 200
        ), model
        assert (
            client.get(
                f"/admin/customer/{model._meta.model_name}/add/", HTTP_HOST=HOST
            ).status_code
            == 200
        ), model
    change = client.get(f"/admin/customer/customer/{ana.pk}/change/", HTTP_HOST=HOST)
    assert (
        change.status_code == 200
        and b"Latex" in change.content
        and b"+34600111222" in change.content
    )


@pytest.mark.django_db
def test_the_staff_creates_changes_and_deletes_from_the_admin(client, superuser):
    client.force_login(superuser)
    created = client.post(
        "/admin/customer/customergroup/add/",
        {
            "name": "VIP",
            "description": "",
            "color": "primary",
            "sort_order": 0,
            "is_active": "on",
        },
        HTTP_HOST=HOST,
    )
    assert created.status_code == 302
    group = CustomerGroup.objects.get()
    changed = client.post(
        f"/admin/customer/customergroup/{group.pk}/change/",
        {
            "name": "Gold",
            "description": "",
            "color": "primary",
            "sort_order": 1,
            "is_active": "on",
        },
        HTTP_HOST=HOST,
    )
    assert changed.status_code == 302
    group.refresh_from_db()
    assert (group.name, group.sort_order) == ("Gold", 1)
    deleted = client.post(
        f"/admin/customer/customergroup/{group.pk}/delete/",
        {"post": "yes"},
        HTTP_HOST=HOST,
    )
    assert deleted.status_code == 302 and not CustomerGroup.objects.exists()
