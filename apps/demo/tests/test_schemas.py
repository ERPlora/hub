"""Input and output schemas of the demo app: what the API, the live stream and the assistant accept."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pydantic
import pytest

from apps.demo.schemas import (
    ByIdIn,
    DeletedOut,
    ItemDetailOut,
    ItemIn,
    ItemListIn,
    ItemOut,
    ItemPage,
    ItemPatchIn,
    ItemStatsIn,
    ItemStatsOut,
    LineIn,
    LineOut,
    Page,
    PageIn,
)

ID = uuid.uuid7()


def invalid_fields(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    return {".".join(str(part) for part in error["loc"]) for error in excinfo.value.errors()}


# Pages


def test_page_defaults():
    assert PageIn().model_dump() == {"limit": 50, "offset": 0}


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_is_between_1_and_100(limit):
    assert invalid_fields(PageIn, limit=limit) == {"limit"}


def test_limit_100_is_allowed():
    assert PageIn(limit=100).limit == 100


def test_offset_is_not_negative():
    assert invalid_fields(PageIn, offset=-1) == {"offset"}


def test_list_filters():
    assert ItemListIn().model_dump() == {"limit": 50, "offset": 0, "search": None, "status": None}
    assert ItemListIn(search="tab", status="done").status == "done"
    assert invalid_fields(ItemListIn, status="closed") == {"status"}
    assert invalid_fields(ItemListIn, limit=101) == {"limit"}


def test_item_page_is_the_generic_page_of_items():
    assert ItemPage is Page[ItemOut]
    assert list(ItemPage.model_fields) == ["rows", "total", "limit", "offset"]


# Inputs


def test_item_in_defaults():
    assert ItemIn(name="Table 1").model_dump() == {"name": "Table 1", "status": "open", "note": ""}


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_item_name_is_1_to_120_characters(name):
    assert invalid_fields(ItemIn, name=name) == {"name"}


def test_item_name_is_stripped():
    assert ItemIn(name="  Table 1 ").name == "Table 1"


def test_item_status_is_open_or_done():
    assert invalid_fields(ItemIn, name="x", status="closed") == {"status"}


def test_patch_only_carries_what_was_sent():
    patch = ItemPatchIn(id=ID, note="")
    assert patch.model_dump(exclude_unset=True) == {"id": ID, "note": ""}
    assert invalid_fields(ItemPatchIn, id=ID, name="") == {"name"}
    assert invalid_fields(ItemPatchIn) == {"id"}


def test_by_id_needs_a_uuid():
    assert ByIdIn(id=str(ID)).id == ID
    assert invalid_fields(ByIdIn, id="nope") == {"id"}


def test_line_in():
    line = LineIn(id=ID, text=" Coffee ", qty="1.5")
    assert (line.text, line.qty, line.client_line_id) == ("Coffee", Decimal("1.5"), None)


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"text": "", "qty": 1}, "text"),
        ({"text": "x" * 201, "qty": 1}, "text"),
        ({"text": "x", "qty": 0}, "qty"),
        ({"text": "x", "qty": -1}, "qty"),
        ({"text": "x", "qty": "1.2345"}, "qty"),  # more than 3 decimals
        ({"text": "x", "qty": "12345678"}, "qty"),  # more than 7 integer digits
        ({"text": "x", "qty": 1, "client_line_id": "nope"}, "client_line_id"),
    ],
)
def test_line_in_rejects(data, field):
    assert invalid_fields(LineIn, id=ID, **data) == {field}


def test_stats_take_no_input():
    assert ItemStatsIn.model_fields == {}


# Outputs


def test_item_detail_extends_item_with_its_lines():
    now = datetime(2026, 10, 13, tzinfo=UTC)
    line_id = uuid.uuid7()
    detail = ItemDetailOut(
        id=ID, name="Table 1", status="open", note="", line_count=1, updated_at=now,
        lines=[{"id": line_id, "text": "Coffee", "qty": Decimal("1.500"), "position": 1, "client_line_id": None}],
    )
    assert issubclass(ItemDetailOut, ItemOut)
    assert detail.model_dump(mode="json") == {
        "id": str(ID),
        "name": "Table 1",
        "status": "open",
        "note": "",
        "line_count": 1,
        "updated_at": "2026-10-13T00:00:00Z",
        "lines": [{"id": str(line_id), "text": "Coffee", "qty": "1.500", "position": 1, "client_line_id": None}],
    }
    assert list(LineOut.model_fields) == ["id", "text", "qty", "position", "client_line_id"]


def test_stats_and_deleted():
    assert list(ItemStatsOut.model_fields) == ["total", "open", "done", "lines"]
    assert DeletedOut(id=ID).model_dump() == {"id": ID}
