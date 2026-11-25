"""Notes and other apps' entries in a card's timeline (CUSTOMER-F05)."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.customer import events
from apps.customer.models import Activity
from apps.customer.schemas.activity import ActivityIn, NoteIn

from .conftest import HUB_DB, NOW, card, outbox, run

pytestmark = HUB_DB


# customer.note.add and customer.activity.add (CUSTOMER-F05; note_add_projects_activity.pg)


def test_a_note_is_its_own_timeline_entry():
    ana = card("Ana")
    note = run(
        "customer.note.add",
        NoteIn(customer_id=ana.id, content="Prefers mornings", author_name="Clara"),
        "hub_employee",
        actor="clara",
    )
    entry = Activity.objects.get()
    assert (note.id, note.kind, note.text, note.actor, note.title) == (
        entry.id,
        "note_added",
        "Prefers mornings",
        "clara",
        "",
    )
    assert entry.data == {"author_name": "Clara"}
    assert outbox() == [
        (events.NOTE_ADDED, {"id": str(entry.id), "customer_id": str(ana.id)})
    ]


def test_a_note_on_a_card_that_is_gone_writes_nothing():
    with pytest.raises(NotFound):
        run(
            "customer.note.add",
            NoteIn(customer_id=card("Gone", deleted_at=NOW).id, content="x"),
        )
    assert not Activity.objects.exists() and outbox() == []


def test_another_app_writes_its_own_entry_in_the_timeline():
    ana = card("Ana")
    entry = run(
        "customer.activity.add",
        ActivityIn(
            customer="Ana",
            kind="appointment.visit",
            title="Visit",
            text="Cut and colour",
            data={"minutes": 90},
            related_id="apt-1",
            related_type="appointment",
        ),
        "hub_manager",
    )
    assert (entry.kind, entry.title, entry.data, entry.related_type) == (
        "appointment.visit",
        "Visit",
        {"minutes": 90},
        "appointment",
    )
    assert outbox() == [
        (events.ACTIVITY_RECORDED, {"id": str(entry.id), "customer_id": str(ana.id)})
    ]
    with pytest.raises(PermissionDenied):
        run(
            "customer.activity.add",
            ActivityIn(customer_id=ana.id, kind="x.y", title="t"),
            "hub_employee",
        )
