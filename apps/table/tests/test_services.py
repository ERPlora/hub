"""The table app's writes that draw the room: zones, tables, the settings and the holds.

Cases from the old module's tests: zones.postgres and write_gates.postgres (editing something that is not
there is an error; a refused write leaves no event), gate_constraints.postgres (each refusal under its own
code), settings.postgres (one row, upserted), reservation_handoff and the old canvas («Se numera sola»,
the first free spot, the number taken in the zone). Every command is one transaction with its event in
the outbox.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import (
    Conflict,
    InvalidPayload,
    NotFound,
    OperationError,
    PermissionDenied,
)
from live.models import OutboxEvent

from apps.table.models import Hold, Table, TableSettings, Zone

from .conftest import (
    ctx_for,
    make_hold,
    make_session,
    make_table,
    make_zone,
    open_check,
    run,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"
MANAGER = "hub_manager"


def names(prefix: str = "table.") -> list[str]:
    return list(
        OutboxEvent.objects.filter(name__startswith=prefix)
        .order_by("created_at", "id")
        .values_list("name", flat=True)
    )


def payloads(name: str) -> list[dict]:
    return list(
        OutboxEvent.objects.filter(name=name)
        .order_by("created_at", "id")
        .values_list("payload", flat=True)
    )


# ── Zones (TABLE-F01, F06) ───────────────────────────────────────────────────────────────────────


def test_a_new_zone_goes_last_and_says_so():
    make_zone("Dining room", sort_order=4)
    zone = run("table.zone.create", {"name": " Terrace ", "color": "success"})
    assert (
        zone.name,
        zone.color,
        zone.sort_order,
        zone.table_count,
        zone.available_count,
    ) == ("Terrace", "success", 5, 0, 0)
    assert Zone.objects.get(pk=zone.id).created_by == "tester"
    assert payloads("table.zone.created") == [{"id": str(zone.id)}]


def test_two_zones_cannot_share_a_name():
    make_zone("Terrace")
    with pytest.raises(Conflict) as refused:
        run("table.zone.create", {"name": "terrace"})
    assert refused.value.code == "table.zone_name_taken"
    assert names() == []


def test_a_zone_changes_only_what_is_sent():
    zone = make_zone("Terrace", description="Outside", color="warning")
    out = run(
        "table.zone.update", {"zone": "terrace", "name": "Patio", "is_active": False}
    )
    zone.refresh_from_db()
    assert (out.name, zone.name, zone.description, zone.color, zone.is_active) == (
        "Patio",
        "Patio",
        "Outside",
        "warning",
        False,
    )
    assert names() == ["table.zone.updated"]


def test_editing_a_zone_that_is_not_there_is_an_error_without_event():
    # write_gates.postgres: writing nothing is an error, and no phantom event reaches the bus.
    with pytest.raises(NotFound) as missing:
        run("table.zone.update", {"id": str(uuid.uuid7()), "name": "X"})
    assert missing.value.code == "table.zone_not_found"
    assert names() == []


def test_a_zone_with_tables_is_not_deleted_even_inactive_ones():
    zone = make_zone("Terrace")
    make_table("1", zone=zone, is_active=False)
    with pytest.raises(Conflict) as refused:
        run("table.zone.delete", {"zone": "Terrace"})
    assert refused.value.code == "table.zone_has_tables"
    assert Zone.objects.get(pk=zone.pk).is_deleted is False


def test_an_empty_zone_is_deleted_logically():
    zone = make_zone("Terrace")
    make_table("1", zone=zone, is_deleted=True, deleted_at=timezone.now())
    assert run("table.zone.delete", {"id": str(zone.id)}).id == zone.id
    zone.refresh_from_db()
    assert (zone.is_deleted, zone.deleted_at is not None) == (True, True)
    assert names() == ["table.zone.deleted"]


def test_only_the_owner_and_the_admin_delete_a_zone_and_a_waiter_does_not_draw():
    zone = make_zone()
    with pytest.raises(PermissionDenied):
        run("table.zone.delete", {"id": str(zone.id)}, ctx_for(MANAGER))
    with pytest.raises(PermissionDenied):
        run("table.zone.create", {"name": "Bar"}, ctx_for(EMPLOYEE))
    assert run("table.zone.create", {"name": "Bar"}, ctx_for(MANAGER)).name == "Bar"


# ── Tables (TABLE-F02 to F05, F07) ───────────────────────────────────────────────────────────────


def test_a_table_without_a_number_takes_the_first_free_one_of_its_zone():
    zone = make_zone()
    make_table("1", zone=zone)
    make_table("3", zone=zone)
    make_table("2", zone=make_zone("Terrace"))
    # Two tables, so 3 — which is taken: the next free one (the old canvas' rule, tables#83).
    assert run("table.table.create", {"zone_id": str(zone.id)}).number == "4"


def test_a_new_table_is_square_for_four_in_the_first_free_spot_of_its_zone():
    zone = make_zone()
    make_table("1", zone=zone, position_x=16, position_y=16)
    table = run("table.table.create", {"zone": zone.name, "number": "S2"})
    assert (table.shape, table.capacity, table.status, table.width, table.height) == (
        "square",
        4,
        "available",
        72,
        72,
    )
    assert (table.position_x, table.position_y) == (104, 16)
    assert Table.objects.get(pk=table.id).created_by == "tester"
    assert payloads("table.table.created") == [{"id": str(table.id)}]


def test_a_number_is_unique_in_its_zone_by_any_door():
    zone = make_zone()
    make_table("M1", zone=zone)
    with pytest.raises(Conflict) as refused:
        run("table.table.create", {"zone_id": str(zone.id), "number": " m1 "})
    assert refused.value.code == "table.number_taken"
    other = make_table("M2", zone=zone)
    with pytest.raises(Conflict):
        run("table.table.update", {"id": str(other.id), "number": "m1"})
    assert names() == []


def test_a_table_needs_a_live_zone():
    gone = make_zone("Old", is_deleted=True, deleted_at=timezone.now())
    with pytest.raises(NotFound) as missing:
        run("table.table.create", {"zone_id": str(gone.id)})
    assert missing.value.code == "table.zone_not_found"


def test_many_tables_are_made_at_once_with_their_prefix_seats_and_free_spots():
    zone = make_zone("Terrace")
    out = run(
        "table.table.bulk_create",
        {"zone": "Terrace", "count": 6, "prefix": "T", "capacity": 2, "shape": "round"},
    )
    rows = out.rows
    assert [row.number for row in rows] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert {(row.capacity, row.shape, row.zone_id) for row in rows} == {
        (2, "round", zone.id)
    }
    spots = {(row.position_x, row.position_y) for row in rows}
    assert len(spots) == 6
    assert payloads("table.table.created") == [{"ids": [str(row.id) for row in rows]}]


def test_many_tables_refuse_a_number_the_zone_already_has_and_make_none():
    zone = make_zone("Terrace")
    make_table("T2", zone=zone)
    with pytest.raises(Conflict) as refused:
        run(
            "table.table.bulk_create",
            {"zone_id": str(zone.id), "count": 3, "prefix": "T"},
        )
    assert refused.value.code == "table.number_taken"
    assert "T2" in refused.value.message
    assert Table.objects.count() == 1


def test_a_table_changes_only_what_is_sent_and_may_change_zone():
    room, terrace = make_zone("Dining room"), make_zone("Terrace")
    table = make_table("4", zone=room, name="Window", position_x=200, position_y=40)
    out = run(
        "table.table.update",
        {"table": "4", "capacity": 6, "shape": "rectangle", "move_to_zone": "terrace"},
    )
    table.refresh_from_db()
    assert (out.capacity, out.shape, out.zone_name, table.name) == (
        6,
        "rectangle",
        "Terrace",
        "Window",
    )
    # Moved to another zone, it keeps its spot on the plan.
    assert (table.position_x, table.position_y, table.zone_id) == (200, 40, terrace.id)


def test_blocking_a_table_takes_it_out_of_service_and_unblocking_brings_it_back():
    table = make_table("4", zone=make_zone())
    assert (
        run("table.table.update", {"id": str(table.id), "blocked": True}).status
        == "blocked"
    )
    assert (
        run("table.table.update", {"id": str(table.id), "blocked": False}).status
        == "available"
    )
    assert names() == ["table.table.updated", "table.table.updated"]


def test_a_table_moves_on_the_plan_keeping_its_box():
    table = make_table("4", width=120, height=72)
    out = run(
        "table.table.move", {"id": str(table.id), "position_x": 300, "position_y": 180}
    )
    assert (out.position_x, out.position_y, out.width, out.height) == (
        300,
        180,
        120,
        72,
    )
    out = run(
        "table.table.move",
        {"id": str(table.id), "position_x": 0, "position_y": 0, "width": 144},
    )
    assert (out.position_x, out.position_y, out.width) == (0, 0, 144)
    assert payloads("table.table.updated") == [{"id": str(table.id)}] * 2


def test_a_table_with_an_open_check_is_not_deleted():
    table = make_table("4", zone=make_zone())
    make_session(table)
    with pytest.raises(Conflict) as refused:
        run("table.table.delete", {"id": str(table.id)})
    assert refused.value.code == "table.table_has_open_session"


def test_a_deleted_table_leaves_the_plan_frees_its_number_and_keeps_its_history():
    zone = make_zone()
    table = make_table("4", zone=zone)
    order = open_check("Table 4")
    session = make_session(table, order_id=order.id)
    # Its check was charged in Sales (no relay in phase 1): the table is free, so it may go.
    from apps.sale.models import Order

    Order.objects.filter(pk=order.id).update(
        status="completed", closed_at=timezone.now()
    )
    run("table.table.delete", {"table": "4"})
    table.refresh_from_db()
    session.refresh_from_db()
    assert (table.is_deleted, table.is_active, session.table_id, session.status) == (
        True,
        False,
        table.id,
        "closed",
    )
    assert (
        run("table.table.create", {"zone_id": str(zone.id), "number": "4"}).number
        == "4"
    )


def test_a_waiter_neither_draws_nor_deletes_and_a_manager_draws_but_does_not_delete():
    table = make_table("4")
    with pytest.raises(PermissionDenied):
        run(
            "table.table.move",
            {"id": str(table.id), "position_x": 1, "position_y": 1},
            ctx_for(EMPLOYEE),
        )
    run(
        "table.table.move",
        {"id": str(table.id), "position_x": 1, "position_y": 1},
        ctx_for(MANAGER),
    )
    with pytest.raises(PermissionDenied):
        run("table.table.delete", {"id": str(table.id)}, ctx_for(MANAGER))


# ── Settings (TABLE-F08) ─────────────────────────────────────────────────────────────────────────


def test_the_settings_are_saved_by_field_in_one_row():
    run("table.settings.update", {"timer_warning_minutes": 45})
    out = run("table.settings.update", {"prompt_guests_on_seat": False})
    assert (
        out.prompt_guests_on_seat,
        out.timer_warning_minutes,
        out.timer_critical_minutes,
    ) == (False, 45, 90)
    assert TableSettings.objects.count() == 1
    assert payloads("table.settings.updated") == [
        {"fields": ["timer_warning_minutes"]},
        {"fields": ["prompt_guests_on_seat"]},
    ]


def test_red_cannot_come_before_amber():
    run("table.settings.update", {"timer_critical_minutes": 100})
    with pytest.raises(InvalidPayload) as refused:
        run("table.settings.update", {"timer_warning_minutes": 120})
    assert set(refused.value.fields) == {"timer_critical_minutes"}
    assert TableSettings.objects.get().timer_warning_minutes == 60


def test_only_the_owner_and_the_admin_change_the_settings():
    for role in (EMPLOYEE, MANAGER):
        with pytest.raises(PermissionDenied):
            run(
                "table.settings.update", {"prompt_guests_on_seat": False}, ctx_for(role)
            )


# ── Holds by hand (TABLE-F29, F30) ───────────────────────────────────────────────────────────────


def hold_data(
    table_ref: str = "6", ref: str = "pedro", starts_in: int = 30, **more
) -> dict:
    start = timezone.now() + dt.timedelta(minutes=starts_in)
    return {
        "table": table_ref,
        "source_ref": ref,
        "held_from": start.isoformat(),
        "held_until": (start + dt.timedelta(hours=2)).isoformat(),
        "party_size": 4,
        "label": "Pedro",
        **more,
    }


def test_a_table_held_by_hand_is_reserved_near_its_hour_and_asking_again_changes_the_same_hold():
    table = make_table("6", zone=make_zone())
    hold = run("table.hold.place", hold_data())
    assert (hold.source, hold.status, hold.label, hold.party_size) == (
        "manual",
        "held",
        "Pedro",
        4,
    )
    assert run("table.table.get", {"id": str(table.id)}).status == "reserved"
    run("table.hold.place", hold_data(label="Pedro M.", party_size=5))
    assert Hold.objects.get().label == "Pedro M."
    assert (
        payloads("table.table.held")
        == [{"table_id": str(table.id), "source": "manual", "source_ref": "pedro"}] * 2
    )


def test_a_hold_needs_a_table_in_service():
    make_table("6", is_active=False)
    with pytest.raises(Conflict) as refused:
        run("table.hold.place", hold_data())
    assert refused.value.code == "table.table_not_available"
    with pytest.raises(NotFound):
        run("table.hold.place", hold_data(table_ref="99"))


def test_releasing_a_hold_forgets_its_name_and_a_released_one_is_not_there():
    table = make_table("6", zone=make_zone())
    run("table.hold.place", hold_data())
    hold = run("table.hold.release", {"source_ref": "pedro"})
    assert (hold.status, hold.label) == ("released", "")
    assert run("table.table.get", {"id": str(table.id)}).status == "available"
    with pytest.raises(NotFound) as missing:
        run("table.hold.release", {"source_ref": "pedro"})
    assert missing.value.code == "table.hold_not_found"


def test_the_sweep_expires_the_holds_whose_window_passed_and_says_so_only_then():
    table = make_table("6")
    over = make_hold(table, starts_in=-180, lasts=60, ref="over", label="Ana")
    live = make_hold(table, starts_in=10, ref="live", label="Luis")
    system = ctx_for(permissions={"*"})
    assert run("table.hold.expire", {}, system).expired == 1
    over.refresh_from_db()
    live.refresh_from_db()
    assert (over.status, over.label, live.status) == ("expired", "", "held")
    assert names() == ["table.table.hold_released"]
    assert run("table.hold.expire", {}, system).expired == 0
    assert names() == ["table.table.hold_released"]


def test_the_platforms_writes_are_for_the_system_alone():
    for name, data in (
        ("table.hold.expire", {}),
        ("table.session.close_by_order", {"order_id": str(uuid.uuid7())}),
        ("table.hold.forget_customer", {"id": str(uuid.uuid7())}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data)


def test_a_refused_write_is_an_operation_error_never_a_database_one():
    zone = make_zone()
    make_table("1", zone=zone)
    with pytest.raises(OperationError):
        run("table.table.create", {"zone_id": str(zone.id), "number": "1"})
