"""Tables in an automation (Automations, ``apps.flow``), end to end with the real apps (no mocks).

Seating a party, seating a parked check again, splitting a check and bringing an open check to a table are
done by the waiter with the party in front, and each opens or retitles the check in Sales with the waiter's
own session (``sale.add_sale``): an automation, which acts with nobody in front and only with the permission
of its step's operation, could never do them (each step fell with ``permission_denied``). They declare
``ai.in_person``: Automations neither offers nor grants them, and a step that slipped in is refused when it
runs (``flow.high_risk``), seating nobody and touching no check (TABLE-F10, TABLE-F12, TABLE-F17, TABLE-F24).
"""

import pytest
from live.errors import InvalidPayload

from apps.sale.models import Order
from apps.table.models import TableSession

from .conftest import add_line, make_session, make_table, open_check, run

pytestmark = pytest.mark.django_db

#: What is done at the table, with a step that names what it acts on by the run's input.
AT_THE_TABLE = {
    "table.session.open": {"table_id": "input.table_id"},
    "table.session.restore": {"id": "input.id", "table_id": "input.table_id"},
    "table.session.split": {"id": "input.id"},
    "table.session.link_order": {"id": "input.id", "order_id": "input.order_id"},
}


def step(operation: str, params: dict) -> dict:
    return {"id": "s1", "kind": "command", "operation": operation, "params": params}


def slipped_in(operation: str, params: dict):
    """An automation turned on whose one step runs ``operation`` with ``params``, written straight in the
    table with it granted, as an old row could leave it (saving or granting it now is refused)."""
    from apps.flow.models import Flow

    return Flow.objects.create(
        name=f"Only {operation}",
        trigger_kind=Flow.Trigger.MANUAL,
        steps=[step(operation, params)],
        grants=[operation],
        enabled=True,
    )


def run_once(flow, **data):
    """Runs ``flow`` now, by hand, with ``data`` as its input: the run's ``(status, error_code)``."""
    result = run("flow.flow.run", {"id": str(flow.id), "input": {k: str(v) for k, v in data.items()}})
    return result.status, result.error_code


@pytest.mark.parametrize("operation", AT_THE_TABLE)
def test_no_automation_is_offered_or_granted_what_is_done_at_the_table(operation):
    # Market: Toast, Square for Restaurants, Lightspeed Restaurant, TouchBistro, Odoo PoS, Revel, SpotOn and
    # Clover seat, split and move checks only from the server's till; their automations never do it.
    from apps.flow.models import Flow
    from apps.flow.queries import catalog_operations

    assert operation not in catalog_operations()
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", {"steps": [step(operation, AT_THE_TABLE[operation])]})
    assert refused.value.code == "flow.high_risk"
    empty = Flow.objects.create(name="Empty", trigger_kind=Flow.Trigger.MANUAL, steps=[], grants=[])
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.grant", {"id": str(empty.id), "operations": [operation]})
    assert refused.value.code == "flow.high_risk"


def test_a_seating_step_that_slipped_in_seats_nobody_and_opens_no_check():
    # The probe of the task: on a free table, the step fell with ``permission_denied`` («sale.add_sale»).
    four = make_table("4")
    flow = slipped_in("table.session.open", AT_THE_TABLE["table.session.open"])
    assert run_once(flow, table_id=four.id) == ("failed", "flow.high_risk")
    assert TableSession.objects.count() == 0
    assert Order.objects.count() == 0


def test_a_split_step_that_slipped_in_leaves_the_check_whole(product):
    check = open_check("Table 4")
    add_line(check.id, product())
    seated = make_session(make_table("4"), order_id=check.id)
    flow = slipped_in("table.session.split", AT_THE_TABLE["table.session.split"])
    assert run_once(flow, id=seated.id) == ("failed", "flow.high_risk")
    assert TableSession.objects.count() == 1
    assert Order.objects.count() == 1


def test_a_restore_step_that_slipped_in_leaves_the_check_parked():
    check = open_check("Bar")
    parked = make_session(None, order_id=check.id, status=TableSession.Status.PARKED)
    six = make_table("6")
    flow = slipped_in("table.session.restore", AT_THE_TABLE["table.session.restore"])
    assert run_once(flow, id=parked.id, table_id=six.id) == ("failed", "flow.high_risk")
    parked.refresh_from_db()
    assert (parked.status, parked.table_id) == (TableSession.Status.PARKED, None)
    assert Order.objects.get(pk=check.id).label == "Bar"


def test_a_link_step_that_slipped_in_leaves_the_bar_check_apart():
    seated = make_session(make_table("4"))
    bar = open_check("Bar")
    flow = slipped_in("table.session.link_order", AT_THE_TABLE["table.session.link_order"])
    assert run_once(flow, id=seated.id, order_id=bar.id) == ("failed", "flow.high_risk")
    seated.refresh_from_db()
    assert seated.order_id is None
    assert Order.objects.get(pk=bar.id).label == "Bar"

