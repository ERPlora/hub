"""«Only mine or all» in the commissions (STAFF-F21): a person reads only their own commission line, and the whole
team's only with «See pay» (``staff.view_compensation``) and the business's totals (``base.view_business_totals``), as
the owner, the administrator and the manager hold them. Their own line is everything they did, also on a sale someone
else charged and attributed to a colleague: the same line the manager reads for them.

Over HTTP as the screen and the API ask, on the live stream and through the assistant, with two employees and a manager
of the same business.
"""

import json
from decimal import Decimal

import pytest
from django.test import Client, RequestFactory
from live.assistant.running import run_tool
from live.errors import PermissionDenied
from live.executor import Stream, Subscription, executor
from live.operations import get

from base import assistant
from base.operations import HubContextBuilder

from .conftest import HOST, HUB_DB, charge, ctx_for, make_member

pytestmark = HUB_DB

REPORT = "staff.commission.report"
PAY = "staff.view_compensation"
TOTALS = "base.view_business_totals"

#: Ana's cut on the sale attributed to Bea, at 15 %; Bea's shampoo, at 10 %.
ANA = ("Ana López", 1800, "15.00", 270)
BEA = ("Bea López", 121, "10.00", 12)


@pytest.fixture
def team(make_user, catalog):
    """Ana and Bea, two stylists with their own accounts, and Marta, the manager. An administrator charged a sale
    attributed to Bea whose cut Ana did, and Bea's shampoo."""
    users = {
        name: make_user(name, role=role)
        for name, role in (("ana", "hub_employee"), ("bea", "hub_employee"), ("marta", "hub_manager"))
    }
    ana = make_member("Ana", user=users["ana"].person, commission_rate=Decimal("15"))
    bea = make_member("Bea", user=users["bea"].person, commission_rate=Decimal("10"))
    charge("own-line-0001", ("CUT", ana), staff=bea)
    charge("own-line-0002", ("SHP", None), staff=bea)
    return users


def lines(answer: dict) -> list[tuple]:
    return [(row["full_name"], row["sold"], row["commission_rate"], row["commission"]) for row in answer["rows"]]


def over_http(user) -> dict:
    client = Client()
    client.force_login(user)
    response = client.get("/api/staff/commissions/report", HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    return response.json()


def asked(permissions: set[str], actor) -> dict:
    op = get(REPORT)
    return op(ctx_for(permissions=permissions, actor=actor), op.input.model_validate({})).model_dump(mode="json")


def test_an_employee_reads_only_her_own_line_with_the_cut_she_did_on_a_colleagues_sale(team):
    # flow: STAFF-F21 (la línea propia de quien no ve la paga del equipo)
    body = over_http(team["ana"])
    assert lines(body) == [ANA]
    assert (body["sales_available"], body["total_sold"], body["total_commission"]) == (True, 1800, 270)
    assert lines(over_http(team["bea"])) == [BEA]


def test_the_manager_reads_the_whole_team_and_ana_the_same_line_the_manager_reads_for_her(team):
    body = over_http(team["marta"])
    assert lines(body) == [ANA, BEA]
    assert (body["total_sold"], body["total_commission"]) == (1921, 282)


@pytest.mark.parametrize(
    ("held", "seen"),
    [
        pytest.param(set(), [ANA], id="neither-the-pay-nor-the-totals"),
        pytest.param({PAY}, [ANA], id="the-pay-without-the-totals"),
        pytest.param({TOTALS}, [ANA], id="the-totals-without-the-pay"),
        pytest.param({PAY, TOTALS}, [ANA, BEA], id="both"),
    ],
)
def test_the_whole_team_takes_the_pay_and_the_business_totals_and_else_ones_own_line(team, held, seen):
    # No permission of Sales: what each one did is read as the platform, so a line is never short of a sale.
    answer = asked({"staff.view", *held}, team["ana"])
    assert lines(answer) == seen
    assert (answer["total_sold"], answer["total_commission"]) == (sum(s[1] for s in seen), sum(s[3] for s in seen))


def test_a_person_with_no_staff_record_reads_no_line(team, make_user):
    body = over_http(make_user("eva", role="hub_employee"))
    assert (body["sales_available"], body["rows"], body["total_sold"], body["total_commission"]) == (True, [], 0, 0)


def test_whoever_does_not_read_the_team_is_refused_even_holding_the_pay_and_the_totals(team):
    with pytest.raises(PermissionDenied):
        asked({PAY, TOTALS, "sale.view_sale"}, team["marta"])


def test_a_caller_that_is_not_a_person_reads_every_line_its_permission_opens(team):
    # An API key, an automation or the platform has no line of its own: «Staff» opens the team's.
    assert lines(asked({"staff.view"}, "flow:7")) == [ANA, BEA]


def test_the_live_report_gives_an_employee_her_line_and_the_manager_the_teams(team, monkeypatch):
    # The executor's own run of one subscription, as an open stream does it; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)

    def followed(user) -> list[tuple]:
        request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
        request.user, request.LANGUAGE_CODE = user, "en"
        stream = Stream(HubContextBuilder().from_request(request))
        op = get(REPORT)
        sub = Subscription(id="commissions", op=op, params=op.input.model_validate({}))
        frame = executor._run_one(stream, sub).decode()
        return lines(json.loads(frame.split("data: ", 1)[1])["data"])

    assert followed(team["ana"]) == [ANA]
    assert followed(team["marta"]) == [ANA, BEA]


def test_the_assistant_tells_an_employee_her_own_commission_and_the_manager_the_teams(team):
    def told(role: str, user) -> list[tuple]:
        ctx = ctx_for(role, actor=user)
        assert REPORT in assistant.tools.catalog(ctx)
        outcome = run_tool(ctx, get(REPORT), "{}")
        assert outcome.outcome == "ok", outcome.content
        return lines(json.loads(outcome.content))

    assert told("hub_employee", team["ana"]) == [ANA]
    assert told("hub_manager", team["marta"]) == [ANA, BEA]


def test_the_owner_the_administrator_and_the_manager_read_the_team_and_the_employee_her_own_line():
    assert get(REPORT).permission == "staff.view"
    held = {role: (ctx_for(role).has(PAY), ctx_for(role).has(TOTALS)) for role in ("hub_owner", "hub_admin", "hub_manager")}
    assert held == {"hub_owner": (True, True), "hub_admin": (True, True), "hub_manager": (True, True)}
    employee = ctx_for("hub_employee")
    assert (employee.has("staff.view"), employee.has(PAY), employee.has(TOTALS)) == (True, False, False)
