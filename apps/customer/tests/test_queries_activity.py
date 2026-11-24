"""A card's timeline: newest first, searchable, saying whether a person or the platform wrote each entry, and not
found for a card that is gone."""

from datetime import timedelta

import pytest
from live.errors import NotFound

from apps.customer.models import Activity
from apps.customer.schemas.activity import ActivityListIn, NoteIn

from base.tests.actors import who_did_it

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def test_the_activity_is_newest_first_and_searchable():
    ana = card("Ana")
    Activity.objects.create(
        customer=ana,
        kind="note_added",
        text="Prefers mornings",
        created_at=NOW - timedelta(hours=1),
    )
    Activity.objects.create(
        customer=ana, kind="purchase_recorded", related_id="s-1", created_at=NOW
    )
    Activity.objects.create(
        customer=card("Bea"), kind="note_added", text="Someone else"
    )
    page = run("customer.activity.list", ActivityListIn(customer_id=ana.id))
    assert [row.kind for row in page.rows] == ["purchase_recorded", "note_added"]
    assert [
        row.text
        for row in run(
            "customer.activity.list", ActivityListIn(customer="Ana", search="morning")
        ).rows
    ] == ["Prefers mornings"]


@pytest.mark.parametrize("caller, who, by_platform", who_did_it("tester", "tester"))
def test_the_activity_says_whether_a_person_or_the_platform_did_it(caller, who, by_platform):
    """A person and an API key are named; the platform's own marks are kept, and the entry says the platform did it."""
    ana = card("Ana")
    run("customer.note.add", NoteIn(customer_id=ana.id, content="Prefers mornings"), actor=caller)

    page = run("customer.activity.list", ActivityListIn(customer_id=ana.id))

    assert [(row.kind, row.actor, row.by_platform) for row in page.rows] == [("note_added", who, by_platform)]


def test_the_timeline_of_a_card_that_is_gone_is_not_found():
    with pytest.raises(NotFound):
        run(
            "customer.activity.list",
            ActivityListIn(customer_id=card("Gone", deleted_at=NOW).id),
        )
