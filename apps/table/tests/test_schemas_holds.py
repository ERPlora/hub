"""The inputs of the holds of a table: a window that ends after it starts, its moments with their zone, and the
reactions to the events of Reservations and Customers, which read only what they need from the payload."""

import datetime as dt

from apps.table.schemas.holds import CustomerErasedIn, HoldPlaceIn, ReservationStatusIn

from .test_schemas_fields import ID, bad


def test_a_hold_ends_after_it_starts_and_carries_its_zone():
    start = dt.datetime(2026, 10, 14, 21, 0, tzinfo=dt.UTC)
    assert bad(
        HoldPlaceIn, table="6", source_ref="pedro", held_from=start, held_until=start
    )
    assert bad(
        HoldPlaceIn,
        table="6",
        source_ref="pedro",
        held_from="2026-10-14T21:00:00",
        held_until="2026-10-14T23:00:00",
    )
    hold = HoldPlaceIn.model_validate(
        {
            "table": "6",
            "source_ref": "pedro",
            "held_from": start,
            "held_until": start + dt.timedelta(hours=2),
        }
    )
    assert (hold.party_size, hold.label) == (0, "")


def test_a_reaction_reads_only_what_it_needs_from_the_other_apps_payload():
    # The emitter's payload may carry more than the reaction needs: it is ignored, never refused.
    data = {"id": "r-1", "status": "confirmed", "table_id": str(ID), "extra": 1}
    assert ReservationStatusIn.model_validate(data).table_id == ID
    assert (
        CustomerErasedIn.model_validate({"id": str(ID), "erased_at": "now"}).id == ID
    )
