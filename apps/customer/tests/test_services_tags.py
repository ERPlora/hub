"""The tags of the business (CUSTOMER-F28)."""

import pytest
from live.errors import Conflict

from apps.customer import events
from apps.customer.models import CustomerTag
from apps.customer.schemas.fields import TagRefIn
from apps.customer.schemas.tags import TagIn, TagPatchIn

from .conftest import HUB_DB, outbox, run

pytestmark = HUB_DB


def test_tag_crud_and_its_taken_name():
    tag = run("customer.tag.create", TagIn(name="Moroso", color="danger"))
    assert (tag.name, tag.color, tag.is_active) == ("Moroso", "danger", True)
    with pytest.raises(Conflict) as excinfo:
        run("customer.tag.create", TagIn(name="MOROSO"))
    assert excinfo.value.code == "customer.tag_name_taken"
    assert (
        run("customer.tag.update", TagPatchIn(tag="Moroso", color="warning")).color
        == "warning"
    )
    run("customer.tag.delete", TagRefIn(tag="moroso"))
    assert not CustomerTag.objects.exists()
    assert [name for name, _ in outbox()] == [
        events.TAG_CREATED,
        events.TAG_UPDATED,
        events.TAG_DELETED,
    ]
