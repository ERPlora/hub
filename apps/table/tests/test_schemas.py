"""The table app's input schemas: what a screen, the assistant or an integration may send.

Every input refuses a field it does not declare; a record is named by its id or as a person says it
(«table 4», «the terrace»); lists page at 100 at most.
"""

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from apps.table import schemas as s

ID = uuid.uuid7()


def bad(schema, **data) -> bool:
    try:
        schema.model_validate(data)
    except ValidationError:
        return True
    return False


def test_an_input_refuses_a_field_it_does_not_declare():
    assert bad(s.ZoneListIn, colour="red")
    assert bad(s.TableListIn, hub_id="x")


def test_a_list_pages_at_a_hundred_at_most():
    assert bad(s.TableListIn, limit=101)
    assert bad(s.SessionListIn, limit=0)
    assert s.ZoneListIn.model_validate({}).limit == 50


@pytest.mark.parametrize("schema", [s.ZoneRefIn, s.TableRefIn, s.SessionRefIn])
def test_a_reference_says_which_one(schema):
    assert bad(schema)


def test_a_table_is_named_by_its_number_and_its_zone_when_said_aloud():
    ref = s.TableRefIn.model_validate({"table": " 4 ", "zone": "Terrace"})
    assert (ref.id, ref.table, ref.zone) == (None, "4", "Terrace")


def test_a_zone_needs_a_name_and_a_known_colour():
    assert bad(s.ZoneIn, name="")
    assert bad(s.ZoneIn, name="Bar", color="pink")
    zone = s.ZoneIn.model_validate({"name": " Bar "})
    assert (zone.name, zone.color, zone.sort_order, zone.description) == (
        "Bar",
        "primary",
        None,
        "",
    )


def test_a_new_table_takes_the_factory_values_and_its_number_may_be_left_out():
    table = s.TableIn.model_validate({"zone_id": str(ID)})
    assert (
        table.number,
        table.capacity,
        table.shape,
        table.position_x,
        table.width,
    ) == (
        None,
        4,
        "square",
        None,
        None,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("capacity", 0),
        ("capacity", 101),
        ("shape", "oval"),
        ("number", "x" * 21),
        ("width", 10),
    ],
)
def test_a_table_seats_one_to_a_hundred_with_a_known_shape_and_a_real_box(field, value):
    assert bad(s.TableIn, zone_id=str(ID), **{field: value})


def test_many_tables_are_one_to_a_hundred():
    assert bad(s.TableBulkIn, zone_id=str(ID), count=0)
    assert bad(s.TableBulkIn, zone_id=str(ID), count=101)
    bulk = s.TableBulkIn.model_validate({"zone": "Terrace", "count": 12, "prefix": "T"})
    assert (bulk.start_number, bulk.capacity, bulk.shape) == (1, 4, "square")


def test_a_move_stays_on_the_plan():
    assert bad(s.TableMoveIn, id=str(ID), position_x=-1, position_y=0)
    assert bad(s.TableMoveIn, id=str(ID), position_x=0, position_y=10_001)


def test_seating_needs_one_guest_at_least():
    assert bad(s.SessionOpenIn, table="4", guests_count=0)
    seat = s.SessionOpenIn.model_validate({"table": "4"})
    assert (seat.guests_count, seat.order_id, seat.customer_id, seat.notes) == (
        None,
        None,
        None,
        "",
    )


def test_a_transfer_and_a_merge_say_where_to():
    assert bad(s.SessionTransferIn, table="4")
    assert bad(s.SessionMergeIn, table="4")
    assert (
        s.SessionTransferIn.model_validate({"table": "4", "to_table": "6"}).to_table
        == "6"
    )
    assert (
        s.SessionMergeIn.model_validate(
            {"id": str(ID), "into_session_id": str(ID)}
        ).into_session_id
        == ID
    )


def test_restoring_names_the_parked_check_and_the_table():
    assert bad(s.SessionRestoreIn, id=str(ID))
    assert s.SessionRestoreIn.model_validate({"id": str(ID), "table": "4"}).table == "4"


def test_a_hold_ends_after_it_starts_and_carries_its_zone():
    start = dt.datetime(2026, 10, 14, 21, 0, tzinfo=dt.UTC)
    assert bad(
        s.HoldPlaceIn, table="6", source_ref="pedro", held_from=start, held_until=start
    )
    assert bad(
        s.HoldPlaceIn,
        table="6",
        source_ref="pedro",
        held_from="2026-10-14T21:00:00",
        held_until="2026-10-14T23:00:00",
    )
    hold = s.HoldPlaceIn.model_validate(
        {
            "table": "6",
            "source_ref": "pedro",
            "held_from": start,
            "held_until": start + dt.timedelta(hours=2),
        }
    )
    assert (hold.party_size, hold.label) == (0, "")


@pytest.mark.parametrize("field", ["timer_warning_minutes", "timer_critical_minutes"])
def test_the_timers_are_one_to_six_hundred_minutes(field):
    assert bad(s.SettingsIn, **{field: 0})
    assert bad(s.SettingsIn, **{field: 601})


def test_a_reaction_reads_only_what_it_needs_from_the_other_apps_payload():
    # The emitter's payload may carry more than the reaction needs: it is ignored, never refused.
    data = {"id": "r-1", "status": "confirmed", "table_id": str(ID), "extra": 1}
    assert s.ReservationStatusIn.model_validate(data).table_id == ID
    assert (
        s.CustomerErasedIn.model_validate({"id": str(ID), "erased_at": "now"}).id == ID
    )
