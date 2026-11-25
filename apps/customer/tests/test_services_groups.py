"""The groups of the business (CUSTOMER-F27), and who configures and deletes groups, tags and fields."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.customer import events
from apps.customer.models import CustomField, CustomerGroup, CustomerTag
from apps.customer.schemas.fields import DeletedOut, FieldRefIn as FieldRef, GroupRefIn, TagRefIn
from apps.customer.schemas.groups import GroupIn, GroupPatchIn

from .conftest import HUB_DB, card, invalid, outbox, run

pytestmark = HUB_DB


# Groups, tags and custom fields (CUSTOMER-F27..F29; group_name_unique.pg, tag_field_name_unique.pg)


def test_group_crud_with_its_notices():
    group = run(
        "customer.group.create",
        GroupIn(name=" VIP ", description="Best", sort_order=2),
        "hub_manager",
    )
    assert (
        group.name,
        group.description,
        group.color,
        group.sort_order,
        group.is_active,
        group.customer_count,
    ) == ("VIP", "Best", "primary", 2, True, 0)
    updated = run(
        "customer.group.update",
        GroupPatchIn(group="vip", name="Gold", is_active=False),
        "hub_manager",
    )
    assert (updated.name, updated.is_active, updated.description) == (
        "Gold",
        False,
        "Best",
    )
    ana = card("Ana")
    ana.groups.add(CustomerGroup.objects.get())
    assert run(
        "customer.group.delete", GroupRefIn(id=group.id), "hub_admin"
    ) == DeletedOut(id=group.id)
    assert ana.groups.count() == 0
    assert outbox() == [
        (events.GROUP_CREATED, {"id": str(group.id)}),
        (events.GROUP_UPDATED, {"id": str(group.id)}),
        (events.GROUP_DELETED, {"id": str(group.id)}),
    ]


def test_a_taken_group_name_is_refused_under_the_name_field():
    CustomerGroup.objects.create(name="VIP")
    for attempt in (lambda: run("customer.group.create", GroupIn(name=" vip ")),):
        with pytest.raises(Conflict) as excinfo:
            attempt()
        assert invalid(excinfo.value) == (
            409,
            "customer.group_name_taken",
            {"name": "There is already a group with that name. Choose another name."},
        )
    other = CustomerGroup.objects.create(name="Gold")
    with pytest.raises(Conflict):
        run("customer.group.update", GroupPatchIn(id=other.id, name="VIP"))
    # An inactive group frees its name, and taking it back while another holds it is refused.
    CustomerGroup.objects.filter(name="VIP").update(is_active=False)
    run("customer.group.update", GroupPatchIn(id=other.id, name="VIP"))
    with pytest.raises(Conflict):
        run(
            "customer.group.update",
            GroupPatchIn(
                id=CustomerGroup.objects.get(is_active=False).id, is_active=True
            ),
        )


def test_only_owner_and_admin_delete_groups_and_tags_but_the_manager_deletes_fields():
    group = CustomerGroup.objects.create(name="VIP")
    tag = CustomerTag.objects.create(name="Moroso")
    field = CustomField.objects.create(name="Allergies")
    with pytest.raises(PermissionDenied):
        run("customer.group.delete", GroupRefIn(id=group.id), "hub_manager")
    with pytest.raises(PermissionDenied):
        run("customer.tag.delete", TagRefIn(id=tag.id), "hub_manager")
    assert (
        run("customer.field.delete", FieldRef(field="allergies"), "hub_manager").id
        == field.id
    )
    with pytest.raises(NotFound) as excinfo:
        run("customer.group.delete", GroupRefIn(id=uuid.uuid7()))
    assert excinfo.value.code == "customer.group_unavailable"


def test_the_employee_does_not_configure():
    with pytest.raises(PermissionDenied):
        run("customer.group.create", GroupIn(name="VIP"), "hub_employee")
