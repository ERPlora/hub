"""What the card of a write says of a group, a tag or a custom field: the read finds it as its write does, by its id
whatever name comes beside it, else by its name, the active one first."""

import pytest
from live.errors import NotFound

from .conftest import HUB_DB
from .test_assistant_card_records import MODELS, read, two


@HUB_DB
@pytest.mark.parametrize("kind", ["group", "tag", "field"])
def test_the_reads_find_a_group_a_tag_or_a_field_by_its_name_as_their_writes_do(kind):
    """In any case, the active one before one no longer active, as ``find_group`` and its neighbours find it (hub#1280);
    a name that fits none is not found."""
    MODELS[kind].objects.create(name="VIP", is_active=False)
    active = MODELS[kind].objects.create(name="vip")
    assert read(f"customer.{kind}.detail", {kind: "Vip"}).id == active.id
    with pytest.raises(NotFound):
        read(f"customer.{kind}.detail", {kind: "Nobody"})


@HUB_DB
@pytest.mark.parametrize("kind", ["group", "tag", "field"])
def test_the_reads_take_a_group_a_tag_or_a_field_by_its_id_whatever_name_comes_beside_it(kind):
    """The id wins, as in their writes (``_find_named``)."""
    own, other = two(kind)
    assert read(f"customer.{kind}.detail", {"id": str(own.id), kind: other.name}).id == own.id
