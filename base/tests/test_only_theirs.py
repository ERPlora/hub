"""A read that the caller's role keeps to their own says so to the assistant (hub#2688).

An employee without «see everyone's» gets only her own rows, as her screens show. The model never sees that rule: an
answer without a colleague's rows reads to it as «she has none», and it says so. So whatever decides that a read
answers only the caller's own marks it (``base.only_theirs.only_theirs``), and the assistant's tool result
carries ``only_theirs``, which tells the model to say it can only see the person's own.
"""

import json

import pytest
from live.context import OperationContext
from live.errors import NotFound
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import Operation, get
from ninja import Schema

from base import assistant
from base.only_theirs import ONLY_THEIRS, only_theirs
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB


class Person:
    """A signed-in person of the team with no account in the business's database: no staff record of her own."""

    pk = None
    email = ""
    is_authenticated = True
    is_active = True

    def get_username(self) -> str:
        return "bea"


def ctx_for(role: str) -> OperationContext:
    return OperationContext(scope=A, actor=Person(), permissions=permissions_for_role(all_live_app_configs(), role))


class NothingIn(Schema):
    pass


class RowsOut(Schema):
    rows: list[str]


def operation(fn, kind: str = "query") -> Operation:
    return Operation(
        name="demo.item.list",
        kind=kind,
        permission=None,
        input=NothingIn,
        output=RowsOut,
        expose_api=False,
        ai={"description": "Lists the items."},
        fn=fn,
        database=False,
    )


def kept_to_theirs(ctx, data):
    only_theirs()
    return {"rows": ["mine"]}


def whole(ctx, data):
    return {"rows": ["mine", "hers"]}


def not_theirs(ctx, data):
    only_theirs()
    raise NotFound("That item does not exist in this business.")


def told(op: Operation) -> dict:
    return json.loads(assistant.tools.run(ctx_for("hub_employee"), op, "{}").content)


def test_a_read_kept_to_the_callers_own_says_so_beside_its_answer():
    answer = told(operation(kept_to_theirs))
    assert answer[ONLY_THEIRS]
    assert answer["rows"] == ["mine"]


def test_a_read_kept_to_the_callers_own_says_so_when_it_finds_nothing_of_theirs():
    answer = told(operation(not_theirs))
    assert answer[ONLY_THEIRS]
    assert answer["error"]["code"] == "not_found"


def test_a_read_of_everyones_says_nothing_of_the_kind():
    assert ONLY_THEIRS not in told(operation(whole))


def test_a_write_that_finds_its_record_among_the_callers_own_says_nothing_of_the_kind():
    assert ONLY_THEIRS not in told(operation(kept_to_theirs, kind="command"))


def test_the_mark_lasts_one_tool_and_reaches_no_other():
    told(operation(kept_to_theirs))
    assert ONLY_THEIRS not in told(operation(whole))


def test_marking_a_read_nobody_tells_does_nothing():
    only_theirs()


#: The reads that decide by hand, not through an ``Owned`` declaration, that a role sees only the caller's own, with
#: the arguments they need.
BY_HAND = {
    "appointment.agenda.lanes": {"date_from": "2026-11-26"},
    "attendance.record.list": {},
    "attendance.correction.list": {},
    "task.task.list": {},
    "task.project.list": {},
    "tip.tip.list": {},
}


@pytest.mark.parametrize("name", BY_HAND)
def test_a_read_that_keeps_an_employee_to_her_own_by_hand_says_so(name):
    outcome = assistant.tools.run(ctx_for("hub_employee"), get(name), json.dumps(BY_HAND[name]))
    assert outcome.outcome == "ok", outcome.content
    assert json.loads(outcome.content)[ONLY_THEIRS]


@pytest.mark.parametrize("name", BY_HAND)
def test_the_same_read_for_whoever_sees_everyones_says_nothing_of_the_kind(name):
    outcome = assistant.tools.run(ctx_for("hub_owner"), get(name), json.dumps(BY_HAND[name]))
    assert outcome.outcome == "ok", outcome.content
    assert ONLY_THEIRS not in json.loads(outcome.content)


def test_whoever_sees_everyones_and_asks_for_their_own_says_nothing_of_the_kind():
    outcome = assistant.tools.run(ctx_for("hub_owner"), get("attendance.record.list"), json.dumps({"mine": True}))
    assert outcome.outcome == "ok", outcome.content
    assert ONLY_THEIRS not in json.loads(outcome.content)
