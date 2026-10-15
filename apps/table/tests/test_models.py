"""The models of the table app and the rules the database itself keeps (the last net under a race)."""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from .conftest import make_hold, make_session, make_table, make_zone

pytestmark = pytest.mark.django_db


def refused(build) -> bool:
    try:
        with transaction.atomic():
            build()
    except IntegrityError:
        return True
    return False


def test_every_key_is_a_uuid7():
    zone = make_zone()
    table = make_table(zone=zone)
    session = make_session(table)
    for row in (zone, table, session):
        assert isinstance(row.pk, uuid.UUID) and row.pk.version == 7


def test_a_new_zone_is_blue_active_and_first():
    zone = make_zone("Terrace")
    assert (
        zone.color,
        zone.sort_order,
        zone.is_active,
        zone.is_deleted,
        zone.description,
    ) == (
        "primary",
        0,
        True,
        False,
        "",
    )
    assert str(zone) == "Terrace"


def test_a_new_table_is_square_for_four_free_and_in_use():
    table = make_table("7", zone=make_zone())
    assert (
        table.capacity,
        table.shape,
        table.width,
        table.height,
        table.blocked,
        table.is_active,
    ) == (
        4,
        "square",
        72,
        72,
        False,
        True,
    )
    assert str(table) == "7"


def test_a_number_is_unique_in_its_zone_without_case_or_spaces():
    zone = make_zone()
    make_table("T1", zone=zone)
    assert refused(lambda: make_table(" t1 ", zone=zone))
    # Another zone may have its own T1.
    assert not refused(lambda: make_table("T1", zone=make_zone("Terrace")))


def test_a_deleted_table_frees_its_number():
    zone = make_zone()
    make_table("5", zone=zone, is_deleted=True, deleted_at=timezone.now())
    assert not refused(lambda: make_table("5", zone=zone))


def test_two_tables_without_a_zone_cannot_share_a_number():
    make_table("9")
    assert refused(lambda: make_table("9"))


def test_a_zone_name_is_unique_among_the_live_ones():
    make_zone("Terrace")
    assert refused(lambda: make_zone("terrace"))
    make_zone("Bar", is_deleted=True, deleted_at=timezone.now())
    assert not refused(lambda: make_zone("Bar"))


@pytest.mark.parametrize(
    "field,value", [("capacity", 0), ("width", 10), ("height", 10)]
)
def test_a_table_seats_one_at_least_and_paints_a_real_box(field, value):
    assert refused(lambda: make_table("1", **{field: value}))


def test_a_check_seats_one_guest_at_least():
    table = make_table()
    assert refused(lambda: make_session(table, guests_count=0))


def test_a_parked_check_sits_at_no_table_and_a_seated_one_at_one():
    from apps.table.models import TableSession

    table = make_table()
    assert refused(lambda: TableSession.objects.create(table=table, status="parked"))
    assert refused(lambda: TableSession.objects.create(table=None, status="open"))
    assert not refused(lambda: TableSession.objects.create(table=None, status="parked"))


def test_a_check_that_ended_parked_keeps_no_table():
    # Sales charged or voided a parked check: it is closed, and it never sat at a table again.
    from apps.table.models import TableSession

    assert not refused(lambda: TableSession.objects.create(table=None, status="closed"))


def test_a_sales_check_is_in_one_live_table_check_at_most():
    from apps.table.models import TableSession

    order_id = uuid.uuid7()
    make_session(make_table("1"), order_id=order_id)
    assert refused(lambda: make_session(make_table("2"), order_id=order_id))
    assert refused(
        lambda: TableSession.objects.create(order_id=order_id, status="parked")
    )
    # A closed one keeps its order: the history may repeat it.
    assert not refused(
        lambda: make_session(make_table("3"), order_id=order_id, status="closed")
    )


def test_a_check_has_one_live_segment_at_most():
    from apps.table.models import SessionMove

    table = make_table()
    session = make_session(table)
    assert refused(
        lambda: SessionMove.objects.create(
            session=session,
            table=table,
            assigned_at=timezone.now(),
            assignment_reason="opened",
        )
    )


def test_a_hold_is_unique_by_its_source_and_ends_after_it_starts():
    from apps.table.models import Hold

    table = make_table()
    make_hold(table, ref="r-1")
    assert refused(lambda: make_hold(table, ref="r-1"))
    now = timezone.now()
    assert refused(
        lambda: Hold.objects.create(
            table=table,
            source="manual",
            source_ref="r-2",
            held_from=now,
            held_until=now - dt.timedelta(minutes=1),
        )
    )


def test_the_settings_are_one_row_with_their_factory_values_and_their_range():
    from apps.table.models import TableSettings

    settings = TableSettings.objects.create()
    assert (
        settings.prompt_guests_on_seat,
        settings.timer_warning_minutes,
        settings.timer_critical_minutes,
    ) == (
        True,
        60,
        90,
    )
    assert refused(lambda: TableSettings.objects.create())
    settings.delete()
    assert refused(lambda: TableSettings.objects.create(timer_warning_minutes=0))
    assert refused(lambda: TableSettings.objects.create(timer_critical_minutes=601))
