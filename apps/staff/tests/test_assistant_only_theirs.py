"""An employee who asks the assistant what the rest of the team earned hears that she can only see her own line
(hub#2688).

Without the team's pay and the business's totals the commission report gives Ana only her line, as Commissions does.
Told nothing more, the model read it as the whole team and said nobody else had a commission."""

import json
from decimal import Decimal

from live.operations import get

from base import assistant
from base.assistant.only_theirs import ONLY_THEIRS

from .conftest import HUB_DB, ctx_for, make_member

pytestmark = HUB_DB

REPORT = "staff.commission.report"


def answered(ctx) -> dict:
    outcome = assistant.tools.run(ctx, get(REPORT), json.dumps({"period": "this_month"}))
    assert outcome.outcome == "ok", outcome.content
    return json.loads(outcome.content)


def test_ana_asking_what_the_others_earned_hears_the_answer_holds_only_her_own(make_user):
    # flow: STAFF-F21 (paso 2: el empleado ve solo su fila)
    account = make_user("ana", role="hub_employee")
    make_member("Ana", user=account.person, commission_rate=Decimal("15"))
    for name in ("Luis", "Carla", "Dora"):
        make_member(name, commission_rate=Decimal("10"))
    answer = answered(ctx_for("hub_employee", actor=account))
    assert [row["full_name"] for row in answer["rows"]] == ["Ana López"]
    assert answer[ONLY_THEIRS]


def test_whoever_sees_the_teams_pay_hears_nothing_of_the_kind():
    for name in ("Ana", "Luis"):
        make_member(name, commission_rate=Decimal("10"))
    answer = answered(ctx_for("hub_owner"))
    assert len(answer["rows"]) == 2
    assert ONLY_THEIRS not in answer
