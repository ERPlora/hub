"""Write operations of the demo app: one transaction each, with its event in the outbox.

The scope isolation of the notifications is observed from raw psycopg sessions in autocommit that
LISTEN on each scope's channel, outside Django, the way the live broker of another process sees it.
"""

import json
import threading
import uuid
from decimal import Decimal

import psycopg
import pytest
from django.db import connection
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.demo import events
from apps.demo.models import Item, ItemLine
from apps.demo.schemas import ByIdIn, DeletedOut, ItemDetailOut, ItemIn, ItemPatchIn, LineIn

from .conftest import A, B, ctx_for

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
        ("demo.item.delete", ByIdIn, DeletedOut),
        ("demo.item.add_line", LineIn, ItemDetailOut),
    ],
)
def test_declarations(name, input, output):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == ("command", "demo.manage", input, output)


# demo.item.create


@pytest.mark.django_db
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
    assert outbox() == [(events.ITEM_CREATED, "a", {"id": str(item.id)})]
    assert OutboxEvent.objects.get().actor == "tester"


# demo.item.update


@pytest.mark.django_db
def test_update_changes_only_what_was_sent_and_records_updated():
    item_id = create("Table 1", note="keep me").id
    OutboxEvent.objects.all().delete()

    detail = run("demo.item.update", ItemPatchIn(id=item_id, name="Table 2", status="done"))

    assert (detail.name, detail.status, detail.note) == ("Table 2", "done", "keep me")
    item = Item.objects.get()
    assert (item.name, item.status, item.note) == ("Table 2", "done", "keep me")
    assert outbox() == [(events.ITEM_UPDATED, "a", {"id": str(item_id)})]


@pytest.mark.django_db
def test_update_with_null_leaves_the_field_and_empty_note_clears_it():
    item_id = create("Table 1", note="old").id
    detail = run("demo.item.update", ItemPatchIn(id=item_id, name=None, note=""))
    assert (detail.name, detail.note) == ("Table 1", "")


@pytest.mark.django_db
def test_update_without_changes_records_nothing():
    item = create("Table 1")
    OutboxEvent.objects.all().delete()

    detail = run("demo.item.update", ItemPatchIn(id=item.id, name="Table 1"))

    assert detail == item
    assert outbox() == []


@pytest.mark.django_db
def test_update_of_a_missing_item_is_not_found():
    with pytest.raises(NotFound):
        run("demo.item.update", ItemPatchIn(id=uuid.uuid7(), name="x"))
    assert outbox() == []


# demo.item.delete


@pytest.mark.django_db
def test_delete_removes_the_item_and_its_lines_and_records_deleted():
    item_id = create().id
    add_line(item_id)
    OutboxEvent.objects.all().delete()

    assert run("demo.item.delete", ByIdIn(id=item_id)) == DeletedOut(id=item_id)

    assert not Item.objects.exists() and not ItemLine.objects.exists()
    assert outbox() == [(events.ITEM_DELETED, "a", {"id": str(item_id)})]


@pytest.mark.django_db
def test_delete_of_a_missing_item_is_not_found():
    with pytest.raises(NotFound):
        run("demo.item.delete", ByIdIn(id=uuid.uuid7()))
    assert outbox() == []


# demo.item.add_line


@pytest.mark.django_db
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
    assert outbox() == [(events.ITEM_LINE_ADDED, "a", {"id": str(created.id), "line_id": str(line.id)})]


@pytest.mark.django_db
def test_position_follows_the_highest_one():
    item_id = create().id
    item = Item.objects.get()
    ItemLine.objects.create(item=item, text="old", qty=1, position=7)
    assert add_line(item_id).lines[-1].position == 8


@pytest.mark.django_db
def test_add_line_is_idempotent_by_client_line_id():
    item_id = create().id
    key = uuid.uuid7()
    OutboxEvent.objects.all().delete()

    first = add_line(item_id, "Coffee", "1", client_line_id=key)
    again = add_line(item_id, "Coffee", "1", client_line_id=key)

    assert again == first
    assert ItemLine.objects.count() == 1
    assert ItemLine.objects.get().client_line_id == key
    assert outbox() == [(events.ITEM_LINE_ADDED, "a", {"id": str(item_id), "line_id": str(first.lines[0].id)})]


@pytest.mark.django_db
def test_the_first_line_wins_for_the_same_client_line_id():
    item_id = create().id
    key = uuid.uuid7()
    add_line(item_id, "Coffee", client_line_id=key)
    assert [line.text for line in add_line(item_id, "Tea", client_line_id=key).lines] == ["Coffee"]


@pytest.mark.django_db
def test_without_client_line_id_each_call_adds_a_line():
    item_id = create().id
    add_line(item_id)
    assert add_line(item_id).line_count == 2


@pytest.mark.django_db
def test_add_line_to_a_done_item_is_a_conflict():
    item_id = create(status="done").id
    OutboxEvent.objects.all().delete()

    with pytest.raises(Conflict) as excinfo:
        add_line(item_id, client_line_id=uuid.uuid7())

    assert (excinfo.value.status, excinfo.value.code) == (409, "demo.item_done")
    assert not ItemLine.objects.exists()
    assert outbox() == []


@pytest.mark.django_db
def test_a_repeated_line_is_accepted_after_the_item_was_closed():
    # The client must not roll back a line that the server already has.
    item_id = create().id
    key = uuid.uuid7()
    first = add_line(item_id, client_line_id=key)
    run("demo.item.update", ItemPatchIn(id=item_id, status="done"))

    again = add_line(item_id, client_line_id=key)

    assert [line.id for line in again.lines] == [line.id for line in first.lines]
    assert again.status == "done"


@pytest.mark.django_db
def test_add_line_to_a_missing_item_is_not_found():
    with pytest.raises(NotFound):
        add_line(uuid.uuid7())


@pytest.mark.django_db(transaction=True)
def test_two_lines_added_at_once_never_share_a_position(db_dsn):
    """A line added while another one is being saved waits for the item's row and goes after it."""
    item_id = create().id
    added = {}

    def second_line():
        try:
            added["detail"] = add_line(item_id, text="Second")
        finally:
            connection.close()

    # Another add_line in flight: the item's row locked and its line written, not committed yet.
    with psycopg.connect(db_dsn) as other:
        other.execute("SELECT id FROM demo_item WHERE id = %s FOR UPDATE", (item_id,))
        other.execute(
            "INSERT INTO demo_itemline (id, item_id, text, qty, position) VALUES (%s, %s, 'First', 1, 1)",
            (uuid.uuid7(), item_id),
        )
        thread = threading.Thread(target=second_line)
        thread.start()
        thread.join(QUIET)
        assert thread.is_alive(), "the second line did not wait for the item's row"
        other.commit()
    thread.join(WAIT * 5)

    assert not thread.is_alive()
    assert [(line.text, line.position) for line in ItemLine.objects.order_by("position", "text")] == [
        ("First", 1),
        ("Second", 2),
    ]


# Permissions


@pytest.mark.django_db
def test_an_employee_cannot_write():
    item_id = create().id
    OutboxEvent.objects.all().delete()
    attempts = [
        ("demo.item.create", ItemIn(name="x")),
        ("demo.item.update", ItemPatchIn(id=item_id, name="x")),
        ("demo.item.delete", ByIdIn(id=item_id)),
        ("demo.item.add_line", LineIn(id=item_id, text="x", qty=1)),
    ]
    for name, data in attempts:
        with pytest.raises(PermissionDenied):
            run(name, data, role="hub_employee")

    assert Item.objects.get().name == "Table 1"
    assert not ItemLine.objects.exists()
    assert outbox() == []


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    """Open raw autocommit sessions that LISTEN on a scope's channel; closed after the test."""
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen):
    on_a, on_b = listen(A), listen(B)

    item_id = create("Table 1", scope=B).id

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.ITEM_CREATED]})]
    assert received(on_a, timeout=QUIET) == []
    assert outbox() == [(events.ITEM_CREATED, "b", {"id": str(item_id)})]

    # Positive control: the same listener of A does hear a command run in A.
    add_line(item_id, scope=A)

    assert received(on_a, stop_after=1) == [(channel_for(A), {"events": [events.ITEM_LINE_ADDED]})]
    assert received(on_b, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_rejected_command_notifies_nobody(listen):
    item_id = create("Table 1", status="done", scope=B).id
    on_b = listen(B)

    with pytest.raises(Conflict):
        add_line(item_id, scope=B)

    assert received(on_b, timeout=QUIET) == []
