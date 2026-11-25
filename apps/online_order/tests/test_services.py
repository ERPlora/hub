"""Regenerating a table's code: one write with its event in the outbox; the code before it stops working at once.

The scope isolation of the notification is observed from raw psycopg sessions in autocommit that LISTEN on each
scope's channel, outside Django, the way the live broker of another process sees it.
"""

import datetime as dt
import json
import re
import uuid

import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.errors import NotFound, PermissionDenied
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.online_order.models import TableCode
from base.tenancy.context import current_alias, use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, ctx_for, make_table, make_zone, run

REGENERATED = "online_order.qr_code.regenerated"
#: What ``secrets.token_urlsafe(16)`` draws: 22 characters of the URL-safe alphabet.
TOKEN = re.compile(r"[A-Za-z0-9_-]{22}")
# How long a test waits for a notification that should arrive; one that must not arrive is awaited for QUIET seconds.
WAIT = 1.0
QUIET = 0.3


def regenerate(data: dict, ctx=None):
    return run("online_order.qr_code.regenerate", data, ctx)


def outbox():
    return list(OutboxEvent.objects.values_list("name", "scope_key", "payload"))


def received(session, timeout=WAIT, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@HUB_DB
def test_a_table_gets_its_first_code_and_the_notice_names_only_the_table():
    table = make_table("4")
    out = regenerate({"id": str(table.id)})
    assert (out.table_id, out.number, out.table, out.zone_name) == (table.id, "4", "4 (no zone)", None)
    assert TOKEN.fullmatch(out.code)
    assert out.url.endswith(f"/p/{A.key}/order/{out.code}")
    assert TableCode.objects.get(table_id=table.id).code == out.code
    assert outbox() == [(REGENERATED, A.key, {"table_id": str(table.id)})]


@HUB_DB
def test_the_code_is_drawn_by_secrets(monkeypatch):
    monkeypatch.setattr("apps.online_order.services.secrets.token_urlsafe", lambda size: f"drawn-{size}")
    assert regenerate({"id": str(make_table("4").id)}).code == "drawn-16"


@HUB_DB
def test_regenerating_replaces_the_code_and_the_one_before_stops_working(monkeypatch):
    table = make_table("4")
    first = regenerate({"id": str(table.id)})
    later = timezone.now() + dt.timedelta(minutes=5)
    monkeypatch.setattr("django.utils.timezone.now", lambda: later)
    second = regenerate({"id": str(table.id)})
    assert TOKEN.fullmatch(second.code) and second.code != first.code
    assert second.issued_at == later > first.issued_at
    assert list(TableCode.objects.values_list("table_id", "code", "issued_at")) == [(table.id, second.code, later)]
    assert not TableCode.objects.filter(code=first.code).exists()
    assert [name for name, _key, _payload in outbox()] == [REGENERATED, REGENERATED]


@HUB_DB
def test_the_code_is_written_in_one_statement_that_replaces_the_row_of_its_table():
    """Two regenerations at once of a table without a code never collide: the row is written by one upsert."""
    table = make_table("4")
    with CaptureQueriesContext(connections[current_alias()]) as queries:
        regenerate({"id": str(table.id)})
    writes = [query["sql"] for query in queries if '"online_order_tablecode"' in query["sql"] and "INSERT" in query["sql"]]
    assert len(writes) == 1
    assert 'ON CONFLICT("table_id") DO UPDATE' in writes[0]


@HUB_DB
def test_a_table_by_its_number_and_its_zone():
    terrace, room = make_zone("Terrace"), make_zone("Room")
    make_table("4", room)
    on_terrace = make_table("4", terrace)
    out = regenerate({"table": "4", "zone": "Terrace"})
    assert (out.table_id, out.table, out.zone_name) == (on_terrace.id, "4 (Terrace)", "Terrace")
    assert list(TableCode.objects.values_list("table_id", flat=True)) == [on_terrace.id]


@HUB_DB
def test_an_unknown_or_deleted_table_writes_nothing():
    gone = make_table("9", is_deleted=True)
    for data in ({"id": str(uuid.uuid7())}, {"id": str(gone.id)}, {"table": "77"}):
        with pytest.raises(NotFound) as refused:
            regenerate(data)
        assert refused.value.code == "table.table_not_found", data
    assert (TableCode.objects.count(), outbox()) == (0, [])


@HUB_DB
def test_only_who_may_change_the_codes_and_see_the_tables_regenerates():
    table = make_table("4")
    for ctx in (ctx_for("hub_employee"), ctx_for(permissions={"online_order.change_qr_code"})):
        with pytest.raises(PermissionDenied):
            regenerate({"id": str(table.id)}, ctx)
    assert (TableCode.objects.count(), outbox()) == (0, [])
    assert regenerate({"id": str(table.id)}, ctx_for("hub_manager")).code


@HUB_DB_COMMITTED
def test_regenerating_in_b_notifies_b_only_and_leaves_a_s_code_as_it_is(listen, hub_b):
    in_a = make_table("1")
    code_a = regenerate({"id": str(in_a.id)}).code  # before anybody listens
    on_a, on_b = listen(A), listen(B)

    with use_hub(hub_b):
        in_b = make_table("1")
        regenerate({"id": str(in_b.id)}, ctx_for(scope=B))
        assert list(TableCode.objects.values_list("table_id", flat=True)) == [in_b.id]
        assert outbox() == [(REGENERATED, B.key, {"table_id": str(in_b.id)})]

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [REGENERATED]})]
    assert received(on_a, timeout=QUIET) == []
    assert list(TableCode.objects.values_list("table_id", "code")) == [(in_a.id, code_a)]

    # Positive control: the same listener of A does hear a regeneration run in A.
    regenerate({"id": str(in_a.id)})
    assert received(on_a, stop_after=1) == [(channel_for(A), {"events": [REGENERATED]})]
    assert received(on_b, timeout=QUIET) == []
