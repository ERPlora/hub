"""The reactions the platform runs on other apps' events; the events themselves are in test_events.py."""

import uuid

import pytest
from live.errors import PermissionDenied

from .conftest import HUB_DB, run
from .write_checks import actions, book

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def system(name: str, data: dict):
    """Runs ``name`` as the platform (the outbox relay's reactions)."""
    from live.context import system_context
    from live.operations import get

    from .conftest import A

    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


def test_a_sale_from_an_appointment_marks_it_charged_and_completes_it_once(salon):
    out = book(salon)
    sale = uuid.uuid7()
    payload = {"sale_id": str(sale), "appointment_id": str(out.id)}
    assert system("appointment.appointment.mark_charged", payload).changed == 1
    item = run("appointment.appointment.get", {"id": str(out.id)})
    assert (item.sale_id, item.status, item.charged_at is not None) == (
        sale,
        "completed",
        True,
    )
    assert system("appointment.appointment.mark_charged", payload).changed == 0
    assert actions(out.id) == ["created", "charged", "completed"]
    assert (
        system("appointment.appointment.unmark_charged", {"sale_id": str(sale)}).changed
        == 1
    )
    item = run("appointment.appointment.get", {"id": str(out.id)})
    assert (item.sale_id, item.status) == (None, "completed")
    assert actions(out.id)[-1] == "uncharged"


def test_the_reactions_are_the_platforms_alone(salon):
    with pytest.raises(PermissionDenied):
        run(
            "appointment.appointment.mark_charged",
            {"sale_id": str(uuid.uuid7()), "appointment_id": str(uuid.uuid7())},
        )
