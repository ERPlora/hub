"""Services with the real Staff app: the professionals who perform a service are staff.Member records.

Staff's own operations create, deactivate and terminate the records; the event Staff records when
someone leaves is handed to ``events.react`` as the outbox relay does, from the outbox itself
(``test_relay.py`` runs the relay itself).
"""

import pytest
from live.models import OutboxEvent
from live.operations import get

from apps.service import events
from apps.service.models import Assignment

from .conftest import A, ctx_for, make_service, make_tax

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin"):
    op = get(name)
    return op(ctx_for(role), op.input.model_validate(data))


def relay(name: str) -> None:
    """Hands the last ``name`` event of the outbox to the service app's reactions."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    events.react(A, event.name, event.payload)


@pytest.fixture
def cut():
    return make_service("Cut", tax=make_tax(), price=2000, duration_minutes=30)


def test_a_professional_created_in_staff_is_assigned_by_name_and_may_perform_the_service(
    cut,
):
    run(
        "staff.member.create",
        {"first_name": "Ana", "last_name": "López", "color": "#AA3300"},
    )
    run(
        "service.assignment.assign",
        {"service": "Cut", "member": "Ana López", "custom_price": 2500},
    )
    [row] = run("service.assignment.eligible", {"service": "Cut"}).rows
    assert (row.full_name, row.color, row.price, row.duration) == (
        "Ana López",
        "#AA3300",
        2500,
        30,
    )


def test_a_professional_who_is_not_bookable_or_is_deactivated_is_not_eligible(cut):
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    bea = run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    for name in ("Ana López", "Bea Ruiz"):
        run("service.assignment.assign", {"service": "Cut", "member": name})
    run("staff.member.update", {"id": str(ana.id), "is_bookable": False})
    assert [
        row.full_name
        for row in run("service.assignment.eligible", {"service": "Cut"}).rows
    ] == ["Bea Ruiz"]
    run("staff.member.deactivate", {"id": str(bea.id)})
    assert run("service.assignment.eligible", {"service": "Cut"}).rows == []
    # Still listed as performing it: the diary decides what an empty eligible list means.
    assert run("service.assignment.list", {"service": "Cut"}).total == 2


def test_terminating_a_professional_in_staff_takes_them_off_every_service(cut):
    colour = make_service("Colour", tax=make_tax("test.colour", "Colour"))
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    for service, member in (
        ("Cut", "Ana López"),
        ("Colour", "Ana López"),
        ("Cut", "Bea Ruiz"),
    ):
        run("service.assignment.assign", {"service": service, "member": member})

    run("staff.member.terminate", {"id": str(ana.id), "reason": "moved away"})
    # Until the relay delivers the event, a terminated record is already out of every list.
    assert [
        row.member_name
        for row in run("service.assignment.list", {"service": "Cut"}).rows
    ] == ["Bea Ruiz"]
    relay("staff.member.terminated")

    assert not Assignment.objects.filter(member_id=ana.id).exists()
    assert Assignment.objects.filter(service=colour).count() == 0
    assert OutboxEvent.objects.filter(name="service.assignment.removed").count() == 2
