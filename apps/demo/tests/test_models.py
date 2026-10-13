"""Models of the demo app: UUIDv7 keys, lines ordered by position, client_line_id unique per item."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.demo.models import Item, ItemLine

pytestmark = pytest.mark.django_db


def make_item(name="Table 1", **fields):
    return Item.objects.create(name=name, **fields)


def add(item, position, client_line_id=None, text="Coffee", qty="1"):
    return ItemLine.objects.create(item=item, text=text, qty=Decimal(qty), position=position, client_line_id=client_line_id)


def test_keys_are_uuid7():
    item = make_item()
    line = add(item, 1)
    assert (item.pk.version, line.pk.version) == (7, 7)


def test_item_defaults():
    item = make_item()
    item.refresh_from_db()
    assert (item.status, item.note) == (Item.Status.OPEN, "")
    assert item.created_at is not None and item.updated_at is not None


def test_status_choices():
    assert Item.Status.values == ["open", "done"]


def test_saving_bumps_updated_at_only():
    item = make_item()
    created, updated = item.created_at, item.updated_at
    item.name = "Table 2"
    item.save()
    item.refresh_from_db()
    assert item.created_at == created
    assert item.updated_at > updated


def test_lines_are_ordered_by_position_then_id():
    item = make_item()
    third = add(item, 3, text="c")
    first = add(item, 1, text="a")
    second = add(item, 2, text="b")
    assert list(item.lines.all()) == [first, second, third]


def test_qty_keeps_three_decimals():
    line = add(make_item(), 1, qty="1.255")
    line.refresh_from_db()
    assert line.qty == Decimal("1.255")


def test_client_line_id_is_unique_per_item():
    item, other = make_item(), make_item("Table 2")
    key = ItemLine._meta.get_field("client_line_id").to_python("0199a6c0-0000-7000-8000-000000000001")
    add(item, 1, client_line_id=key)
    add(other, 1, client_line_id=key)  # another item may reuse it

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        add(item, 2, client_line_id=key)

    assert "demo_line_client_id_unique" in str(excinfo.value)


def test_lines_without_client_line_id_do_not_collide():
    item = make_item()
    add(item, 1)
    add(item, 2)
    assert item.lines.count() == 2


def test_deleting_an_item_deletes_its_lines():
    item = make_item()
    add(item, 1)
    item.delete()
    assert not ItemLine.objects.exists()
