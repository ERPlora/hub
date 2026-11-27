"""The inputs of a table check: seating, a transfer, a merge and restoring a parked one."""

from apps.table.schemas.sessions import SessionMergeIn, SessionOpenIn, SessionRestoreIn, SessionTransferIn

from .test_schemas_fields import ID, bad


def test_seating_needs_one_guest_at_least():
    assert bad(SessionOpenIn, table="4", guests_count=0)
    seat = SessionOpenIn.model_validate({"table": "4"})
    assert (seat.guests_count, seat.order_id, seat.customer_id, seat.notes) == (
        None,
        None,
        None,
        "",
    )


def test_a_transfer_and_a_merge_say_where_to():
    assert bad(SessionTransferIn, table="4")
    assert bad(SessionMergeIn, table="4")
    assert (
        SessionTransferIn.model_validate({"table": "4", "to_table": "6"}).to_table
        == "6"
    )
    assert (
        SessionMergeIn.model_validate(
            {"id": str(ID), "into_session_id": str(ID)}
        ).into_session_id
        == ID
    )


def test_restoring_names_the_parked_check_and_the_table():
    assert bad(SessionRestoreIn, id=str(ID))
    assert SessionRestoreIn.model_validate({"id": str(ID), "table": "4"}).table == "4"
