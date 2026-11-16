"""Write operations of the demo app: one transaction each, with its event in the outbox.

The scope isolation of the notifications is observed from raw psycopg sessions in autocommit that
LISTEN on each scope's channel, outside Django, the way the live broker of another process sees it.
"""

import json
import uuid
from decimal import Decimal

import psycopg
import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.demo import events
from apps.demo.models import Item, ItemLine
from apps.demo.schemas import DeletedOut, ItemDetailOut, ItemIn, ItemPatchIn, ItemRefIn, LineIn
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.concurrency import in_a_thread

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, ctx_for

# How long a test waits for a notification that should arrive; one that must not arrive is
# awaited for QUIET seconds.
WAIT = 1.0
QUIET = 0.3


def run(name, data, role="hub_admin", scope=A):
    return get(name)(ctx_for(role, scope), data)


def create(name="Table 1", role="hub_admin", scope=A, **fields):
    return run("demo.item.create", ItemIn(name=name, **fields), role, scope)


def add_line(item_id, text="Coffee", qty="1", client_line_id=None, role="hub_admin", scope=A):
    data = LineIn(id=item_id, text=text, qty=qty, client_line_id=client_line_id)
    return run("demo.item.add_line", data, role, scope)


def outbox():
    return list(OutboxEvent.objects.values_list("name", "scope_key", "payload"))


# Declarations


@pytest.mark.parametrize(
    ("name", "input", "output"),
    [
        ("demo.item.create", ItemIn, ItemDetailOut),
        ("demo.item.update", ItemPatchIn, ItemDetailOut),
        ("demo.item.delete", ItemRefIn, DeletedOut),
        ("demo.item.add_line", LineIn, ItemDetailOut),
    ],
)
def test_declarations(name, input, output):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == ("command", "demo.manage", input, output)


# demo.item.create


@HUB_DB
def test_create_returns_the_detail_and_records_created():
    detail = create("Table 1", note="by the window")

    item = Item.objects.get()
    assert detail.model_dump() == {
        "id": item.id,
        "name": "Table 1",
        "status": "open",
        "note": "by the window",
        "line_count": 0,
        "updated_at": item.updated_at,
        "lines": [],
    }
    assert outbox() == [(events.ITEM_CREATED, A.key, {"id": str(item.id)})]
    assert OutboxEvent.objects.get().actor == "tester"


# demo.item.update


@HUB_DB
def test_update_changes_only_what_was_sent_and_records_updated():
    item_id = create("Table 1", note="keep me").id
    OutboxEvent.objects.all().delete()

    detail = run("demo.item.update", ItemPatchIn(id=item_id, name="Table 2", status="done"))

    assert (detail.name, detail.status, detail.note) == ("Table 2", "done", "keep me")
    item = Item.objects.get()
    assert (item.name, item.status, item.note) == ("Table 2", "done", "keep me")
    assert outbox() == [(events.ITEM_UPDATED, A.key, {"id": str(item_id)})]


@HUB_DB
def test_update_with_null_leaves_the_field_and_empty_note_clears_it():
    item_id = create("Table 1", note="old").id
    detail = run("demo.item.update", ItemPatchIn(id=item_id, name=None, note=""))
    assert (detail.name, detail.note) == ("Table 1", "")


@HUB_DB
def test_update_without_changes_records_nothing():
    item = create("Table 1")
    OutboxEvent.objects.all().delete()

    detail = run("demo.item.update", ItemPatchIn(id=item.id, name="Table 1"))

    assert detail == item
    assert outbox() == []


@HUB_DB
def test_update_of_a_missing_item_is_not_found():
    with pytest.raises(NotFound):
        run("demo.item.update", ItemPatchIn(id=uuid.uuid7(), name="x"))
    assert outbox() == []


# demo.item.delete


@HUB_DB
def test_delete_removes_the_item_and_its_lines_and_records_deleted():
    item_id = create().id
    add_line(item_id)
    OutboxEvent.objects.all().delete()

    assert run("demo.item.delete", ItemRefIn(id=item_id)) == DeletedOut(id=item_id)

    assert not Item.objects.exists() and not ItemLine.objects.exists()
    assert outbox() == [(events.ITEM_DELETED, A.key, {"id": str(item_id)})]


@HUB_DB
def test_delete_of_a_missing_item_is_not_found():
    with pytest.raises(NotFound):
        run("demo.item.delete", ItemRefIn(id=uuid.uuid7()))
    assert outbox() == []


# Each write on an item by its name (hub#1162), as the read finds it: ``tests/test_queries.py``.

#: Each write on one item, its input and the rest of what it needs.
ON_AN_ITEM = [
    ("demo.item.update", ItemPatchIn, {"status": "done"}),
    ("demo.item.delete", ItemRefIn, {}),
    ("demo.item.add_line", LineIn, {"text": "Screws", "qty": "3"}),
]


@HUB_DB
def test_update_by_its_name_changes_only_what_was_sent():
    item = create("Autumn trial", note="keep")
    create("Bar")
    OutboxEvent.objects.all().delete()

    detail = run("demo.item.update", ItemPatchIn(called="autumn trial", name="Winter trial", status="done"))

    assert (detail.id, detail.name, detail.status, detail.note) == (item.id, "Winter trial", "done", "keep")
    assert outbox() == [(events.ITEM_UPDATED, A.key, {"id": str(item.id)})]


@HUB_DB
def test_delete_by_its_name_says_and_records_the_id_of_the_item_it_deleted():
    item = create("Autumn trial")
    add_line(item.id)
    bar = create("Bar")
    OutboxEvent.objects.all().delete()

    assert run("demo.item.delete", ItemRefIn(called="Autumn trial")) == DeletedOut(id=item.id)

    assert list(Item.objects.values_list("id", flat=True)) == [bar.id]
    assert not ItemLine.objects.exists()
    assert outbox() == [(events.ITEM_DELETED, A.key, {"id": str(item.id)})]


@HUB_DB
def test_add_line_by_its_name():
    item = create("Autumn trial")
    create("Bar")

    detail = run("demo.item.add_line", LineIn(called="Autumn trial", text="Screws", qty="3"))

    assert (detail.id, [(line.text, line.qty) for line in detail.lines]) == (item.id, [("Screws", Decimal("3"))])


@HUB_DB
@pytest.mark.parametrize(("name", "schema", "rest"), ON_AN_ITEM)
def test_a_name_two_items_share_changes_nothing_and_records_nothing(name, schema, rest):
    first, second = create("Autumn trial"), create("Autumn trial")
    OutboxEvent.objects.all().delete()

    with pytest.raises(Conflict) as excinfo:
        run(name, schema(called="Autumn trial", **rest))

    assert excinfo.value.code == "demo.item_ambiguous"
    assert sorted(Item.objects.values_list("id", "status")) == sorted([(first.id, "open"), (second.id, "open")])
    assert not ItemLine.objects.exists()
    assert outbox() == []


@HUB_DB
@pytest.mark.parametrize(("name", "schema", "rest"), ON_AN_ITEM)
def test_each_write_locks_the_items_row_before_it_writes(name, schema, rest):
    """The module's promise (two writes on the same item never interleave): the item found, by its id or its name, is
    read again ``FOR UPDATE`` before anything is written."""
    item = create("Autumn trial")
    with CaptureQueriesContext(connections[current_alias()]) as queries:
        run(name, schema(called="Autumn trial", **rest))
    statements = [query["sql"] for query in queries.captured_queries]
    locked = next(at for at, sql in enumerate(statements) if "FOR UPDATE" in sql and str(item.id.hex) in sql.replace("-", ""))
    written = next(at for at, sql in enumerate(statements) if sql.lstrip().startswith(("UPDATE", "DELETE", "INSERT")))
    assert locked < written, statements


@HUB_DB
def test_a_write_on_a_name_no_item_has_is_not_found():
    create("Bar")
    with pytest.raises(NotFound):
        run("demo.item.delete", ItemRefIn(called="Autumn trial"))
    assert Item.objects.count() == 1


# demo.item.add_line


@HUB_DB
def test_add_line_appends_at_the_end_and_records_line_added():
    created = create()
    first = add_line(created.id, "Coffee", "1")
    OutboxEvent.objects.all().delete()

    detail = add_line(created.id, "Tea", "2.5")

    line = ItemLine.objects.get(text="Tea")
    assert [(entry.text, entry.qty, entry.position) for entry in detail.lines] == [
        ("Coffee", Decimal("1.000"), 1),
        ("Tea", Decimal("2.500"), 2),
    ]
    assert detail.line_count == 2
    assert detail.updated_at > first.updated_at > created.updated_at  # the item moves up the list
    assert outbox() == [(events.ITEM_LINE_ADDED, A.key, {"id": str(created.id), "line_id": str(line.id)})]


@HUB_DB
def test_position_follows_the_highest_one():
    item_id = create().id
    item = Item.objects.get()
    ItemLine.objects.create(item=item, text="old", qty=1, position=7)
    assert add_line(item_id).lines[-1].position == 8


@HUB_DB
def test_add_line_is_idempotent_by_client_line_id():
    item_id = create().id
    key = uuid.uuid7()
    OutboxEvent.objects.all().delete()

    first = add_line(item_id, "Coffee", "1", client_line_id=key)
    again = add_line(item_id, "Coffee", "1", client_line_id=key)

    assert again == first
    assert ItemLine.objects.count() == 1
    assert ItemLine.objects.get().client_line_id == key
    assert outbox() == [(events.ITEM_LINE_ADDED, A.key, {"id": str(item_id), "line_id": str(first.lines[0].id)})]


@HUB_DB
def test_the_first_line_wins_for_the_same_client_line_id():
    item_id = create().id
    key = uuid.uuid7()
    add_line(item_id, "Coffee", client_line_id=key)
    assert [line.text for line in add_line(item_id, "Tea", client_line_id=key).lines] == ["Coffee"]


@HUB_DB
def test_without_client_line_id_each_call_adds_a_line():
    item_id = create().id
    add_line(item_id)
    assert add_line(item_id).line_count == 2


@HUB_DB
def test_add_line_to_a_done_item_is_a_conflict():
    item_id = create(status="done").id
    OutboxEvent.objects.all().delete()

    with pytest.raises(Conflict) as excinfo:
        add_line(item_id, client_line_id=uuid.uuid7())

    assert (excinfo.value.status, excinfo.value.code) == (409, "demo.item_done")
    assert not ItemLine.objects.exists()
    assert outbox() == []


@HUB_DB
def test_a_repeated_line_is_accepted_after_the_item_was_closed():
    # The client must not roll back a line that the server already has.
    item_id = create().id
    key = uuid.uuid7()
    first = add_line(item_id, client_line_id=key)
    run("demo.item.update", ItemPatchIn(id=item_id, status="done"))

    again = add_line(item_id, client_line_id=key)

    assert [line.id for line in again.lines] == [line.id for line in first.lines]
    assert again.status == "done"


@HUB_DB
def test_add_line_to_a_missing_item_is_not_found():
    with pytest.raises(NotFound):
        add_line(uuid.uuid7())


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_two_lines_added_at_once_never_share_a_position():
    """A line added while another one is being saved waits for the item's row and goes after it."""
    item_id = create().id
    added = [None]

    # Another add_line in flight, in the business's own database: the item's row locked and its line written, not
    # committed yet.
    with psycopg.connect(**connections[current_alias()].get_connection_params()) as other:
        other.execute("SELECT id FROM demo_item WHERE id = %s FOR UPDATE", (item_id,))
        other.execute(
            "INSERT INTO demo_itemline (id, item_id, text, qty, position) VALUES (%s, %s, 'First', 1, 1)",
            (uuid.uuid7(), item_id),
        )
        thread = in_a_thread(lambda: add_line(item_id, text="Second"), added)
        thread.start()
        thread.join(QUIET)
        assert thread.is_alive(), "the second line did not wait for the item's row"
        other.commit()
    thread.join(WAIT * 5)

    assert not thread.is_alive()
    assert isinstance(added[0], ItemDetailOut), added[0]
    assert [(line.text, line.position) for line in ItemLine.objects.order_by("position", "text")] == [
        ("First", 1),
        ("Second", 2),
    ]


# Permissions


@HUB_DB
def test_an_employee_cannot_write():
    item_id = create().id
    OutboxEvent.objects.all().delete()
    attempts = [
        ("demo.item.create", ItemIn(name="x")),
        ("demo.item.update", ItemPatchIn(id=item_id, name="x")),
        ("demo.item.delete", ItemRefIn(id=item_id)),
        ("demo.item.add_line", LineIn(id=item_id, text="x", qty=1)),
    ]
    for name, data in attempts:
        with pytest.raises(PermissionDenied):
            run(name, data, role="hub_employee")

    assert Item.objects.get().name == "Table 1"
    assert not ItemLine.objects.exists()
    assert outbox() == []


# Notifications: after the COMMIT, on the channel of the command's scope only


def received(session, timeout=WAIT, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@HUB_DB_COMMITTED
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen, hub_b):
    in_a = create("Table 1").id  # before anybody listens
    on_a, on_b = listen(A), listen(B)

    with use_hub(hub_b):
        item_id = create("Table 1", scope=B).id

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.ITEM_CREATED]})]
    assert received(on_a, timeout=QUIET) == []
    # The channel is the command's scope; the rows of the outbox carry theirs, each in its business's database.
    with use_hub(hub_b):
        assert outbox() == [(events.ITEM_CREATED, B.key, {"id": str(item_id)})]
        assert set(OutboxEvent.objects.values_list("scope_kind", "scope_key")) == {(B.kind, B.key)}
    assert outbox() == [(events.ITEM_CREATED, A.key, {"id": str(in_a)})]

    # Positive control: the same listener of A does hear a command run in A.
    add_line(in_a, scope=A)

    assert received(on_a, stop_after=1) == [(channel_for(A), {"events": [events.ITEM_LINE_ADDED]})]
    assert received(on_b, timeout=QUIET) == []


@HUB_DB_COMMITTED
def test_a_rejected_command_notifies_nobody(listen, hub_b):
    with use_hub(hub_b):
        item_id = create("Table 1", status="done", scope=B).id
        on_b = listen(B)

        with pytest.raises(Conflict):
            add_line(item_id, scope=B)

    assert received(on_b, timeout=QUIET) == []
