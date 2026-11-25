"""A card's groups and tags (CUSTOMER-F06)."""

import json
import uuid

import pytest
from live.errors import InvalidPayload

from apps.customer import events
from apps.customer.models import CustomerGroup, CustomerTag
from apps.customer.schemas.memberships import SetGroupsIn, SetTagsIn

from .conftest import HUB_DB, card, clear_outbox, outbox, run

pytestmark = HUB_DB


# customer.customer.set_groups / set_tags (CUSTOMER-F06)


def test_set_groups_replaces_the_selection_by_id_or_by_name():
    vip, wholesale = (
        CustomerGroup.objects.create(name="VIP"),
        CustomerGroup.objects.create(name="Wholesale"),
    )
    ana = card("Ana")
    detail = run(
        "customer.customer.set_groups",
        SetGroupsIn(id=ana.id, group_ids=[vip.id], groups=["wholesale"]),
    )
    assert set(detail.group_ids) == {vip.id, wholesale.id}
    assert outbox() == [(events.CUSTOMER_GROUPS_CHANGED, {"id": str(ana.id)})]
    clear_outbox()
    detail = run(
        "customer.customer.set_groups", SetGroupsIn(customer="Ana", groups=["VIP"])
    )
    assert detail.group_ids == [vip.id]
    run(
        "customer.customer.set_groups", SetGroupsIn(customer="Ana", group_ids=[vip.id])
    )  # the same: no notice
    assert outbox() == [(events.CUSTOMER_GROUPS_CHANGED, {"id": str(ana.id)})]
    run("customer.customer.set_groups", SetGroupsIn(id=ana.id))
    assert list(ana.groups.all()) == []


def test_a_group_that_no_longer_exists_saves_nothing():
    vip = CustomerGroup.objects.create(name="VIP")
    ana = card("Ana")
    ana.groups.add(vip)
    for sent in ({"group_ids": [uuid.uuid7()]}, {"groups": ["Nope"]}):
        with pytest.raises(InvalidPayload) as excinfo:
            run("customer.customer.set_groups", SetGroupsIn(id=ana.id, **sent))
        assert excinfo.value.code == "customer.group_unavailable"
    assert list(ana.groups.all()) == [vip]


def test_set_tags():
    moroso = CustomerTag.objects.create(name="Moroso")
    ana = card("Ana")
    assert run(
        "customer.customer.set_tags", SetTagsIn(id=ana.id, tags=["moroso"])
    ).tag_ids == [moroso.id]
    assert outbox() == [(events.CUSTOMER_TAGS_CHANGED, {"id": str(ana.id)})]
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.set_tags", SetTagsIn(id=ana.id, tag_ids=[uuid.uuid7()]))
    assert excinfo.value.code == "customer.tag_unavailable"


def test_the_refusal_names_the_groups_and_tags_sent_by_id_that_no_longer_exist():
    # Same code, message and field as before; besides, which of the ids sent are gone, so a client
    # (the card's editor, CUSTOMER-F06) takes exactly those off its selection. By name there is no id.
    vip = CustomerGroup.objects.create(name="VIP")
    loyal = CustomerTag.objects.create(name="Loyal")
    ana = card("Ana")
    gone_group, gone_tag = uuid.uuid7(), uuid.uuid7()
    with pytest.raises(InvalidPayload) as groups:
        run(
            "customer.customer.set_groups",
            SetGroupsIn(id=ana.id, group_ids=[vip.id, gone_group]),
        )
    with pytest.raises(InvalidPayload) as tags:
        run(
            "customer.customer.set_tags",
            SetTagsIn(id=ana.id, tag_ids=[gone_tag, loyal.id]),
        )
    with pytest.raises(InvalidPayload) as by_name:
        run("customer.customer.set_groups", SetGroupsIn(id=ana.id, groups=["Nope"]))
    sent = [json.loads(json.dumps(e.value.envelope(), default=str)) for e in (groups, tags, by_name)]
    assert sent == [
        {
            "error": {
                "code": "customer.group_unavailable",
                "message": "That group no longer exists.",
                "fields": {"groups": "That group no longer exists."},
                "unavailable_ids": [str(gone_group)],
            }
        },
        {
            "error": {
                "code": "customer.tag_unavailable",
                "message": "That tag no longer exists.",
                "fields": {"tags": "That tag no longer exists."},
                "unavailable_ids": [str(gone_tag)],
            }
        },
        {
            "error": {
                "code": "customer.group_unavailable",
                "message": "That group no longer exists.",
                "fields": {"groups": "That group no longer exists."},
            }
        },
    ]
    assert (list(ana.groups.all()), list(ana.tags.all())) == ([], [])
