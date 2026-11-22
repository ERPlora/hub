"""«Only mine or all» in Cash register (CASH_REGISTER-F11, F12 and F16): a person without «See all register sessions»
(``cash_register.view_all_sessions``) reads only the shifts they opened or closed, and the shift open now, which is the
drawer everyone at the till charges, counts and closes; the owner, the administrator and the manager reach every shift,
as Square's and Toast's «own drawer / all drawers». A shift a person does not see does not exist for them: the same 404
as an unknown one, never a 403 that tells it is there.

What a shift adds up stays the whole drawer's: the cash a colleague charged while it was open counts in its expected
cash, whoever looks. What its comps cost reaches only whoever sees the costs (``base.view_costs``), on the screen and on
the paper.

Over HTTP, as the screens, the assistant and the API ask, with two employees and a manager of the same business.
"""

import datetime as dt
import json

import pytest
from django.test import Client
from django.utils import timezone
from live.context import system_context
from live.meta import all_live_app_configs, permissions_for_role

from apps.cash_register.models import Session
from apps.cash_register.queries.ownership import SESSIONS
from apps.cash_register.tests.conftest import HOST, HUB_DB, A, ctx_for, run
from apps.printing.models import PrintJob

pytestmark = HUB_DB

NOT_FOUND = "cash_register.session_not_found"
CASH = [{"method": "cash"}]


def get(client, path, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=HOST)


def post(client, path, data):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST)


def missing(response) -> bool:
    """A 404 that says the shift does not exist."""
    return response.status_code == 404 and response.json()["error"]["code"] == NOT_FOUND


@pytest.fixture
def people(make_user):
    """Ana and Bea, two employees, and Marta, the manager, each signed in on their own device. Their names are not their
    usernames: a shift is theirs by who they are, not by the name it shows."""
    signed_in = {}
    for username, role in (("ana", "hub_employee"), ("bea", "hub_employee"), ("marta", "hub_manager")):
        user = make_user(username, role=role)
        user.first_name, user.last_name = username.title(), "Ruiz"
        user.save()
        client = Client()
        client.force_login(user)
        signed_in[username] = client
    return signed_in


def open_shift(client, balance: int = 10000) -> dict:
    response = post(client, "/cash_register/sessions/open", {"opening_balance": balance})
    assert response.status_code == 201, response.content
    return response.json()


def close_shift(client, counted: int = 10000) -> dict:
    response = post(client, "/cash_register/sessions/close", {"closing_balance": counted})
    assert response.status_code == 200, response.content
    return response.json()


def charge(client, key: str, lines: list, payments: list | None = None) -> dict:
    body = {"idempotency_key": key, "lines": lines, **({"payments": payments} if payments else {})}
    response = post(client, "/sale/sales", body)
    assert response.status_code == 201, response.content
    return response.json()


def listed(client) -> set[str]:
    response = get(client, "/cash_register/sessions")
    assert response.status_code == 200, response.content
    page = response.json()
    assert page["total"] == len(page["rows"])
    return {row["number"] for row in page["rows"]}


@pytest.fixture
def shifts(people):
    """A shift Bea opened and closed, then one Ana opened and closed."""
    made = {}
    for name in ("bea", "ana"):
        open_shift(people[name])
        made[name] = close_shift(people[name])
    return made


@pytest.fixture
def shirt(db):
    """A 121.00 € shirt that costs the business 40.00 €."""
    return run(
        "inventory.product.create",
        {"name": "Shirt", "sku": "SHIRT", "price": 12100, "cost": 4000, "tax_category_key": "product.generic"},
        system_context(A),
    )


class TestAnEmployeeReachesOnlyTheirOwnShifts:
    def test_the_list_has_only_the_shifts_they_opened_or_closed(self, people, shifts):
        assert listed(people["ana"]) == {shifts["ana"]["number"]}
        assert listed(people["bea"]) == {shifts["bea"]["number"]}

    def test_someone_elses_shift_does_not_open_by_its_id_nor_by_its_number(self, people, shifts):
        ana, theirs = people["ana"], shifts["bea"]
        assert missing(get(ana, "/cash_register/sessions/detail", session_id=theirs["id"]))
        assert missing(get(ana, "/cash_register/sessions/detail", session=theirs["number"]))
        assert get(ana, "/cash_register/sessions/detail", session_id=shifts["ana"]["id"]).status_code == 200

    def test_nor_its_movements_nor_its_counts(self, people, shifts):
        ana, theirs, own = people["ana"], shifts["bea"]["id"], shifts["ana"]["id"]
        assert missing(get(ana, "/cash_register/movements", session_id=theirs))
        assert missing(get(ana, "/cash_register/counts", session_id=theirs))
        assert get(ana, "/cash_register/movements", session_id=own).status_code == 200
        assert get(ana, "/cash_register/counts", session_id=own).status_code == 200

    def test_nor_its_paper(self, people, shifts):
        ana = people["ana"]
        assert missing(post(ana, "/cash_register/sessions/print", {"session_id": shifts["bea"]["id"]}))
        assert post(ana, "/cash_register/sessions/print", {"session_id": shifts["ana"]["id"]}).status_code == 200

    def test_nor_a_write_that_names_it(self, people, shifts):
        named = {"session_id": shifts["bea"]["id"], "type": "in", "amount": 100}
        assert missing(post(people["ana"], "/cash_register/movements", named))


class TestTheShiftOpenNow:
    """One shift is open at a time in the whole business: the drawer everyone at the till charges, counts and closes."""

    def test_a_colleague_works_the_shift_open_now_and_keeps_the_one_they_closed(self, coffee, people):
        ana, bea = people["ana"], people["bea"]
        opened = open_shift(bea)
        assert get(ana, "/cash_register/sessions/current").json()["session"]["number"] == opened["number"]
        assert opened["number"] in listed(ana)
        assert get(ana, "/cash_register/sessions/detail", session_id=opened["id"]).status_code == 200
        # Sales asks the drawer as whoever charges: Ana charges cash in Bea's shift.
        charge(ana, "own-shift-cash-0001", [{"product": "COF"}], CASH)
        assert post(ana, "/cash_register/movements", {"type": "in", "amount": 500}).status_code == 201
        close_shift(ana, 10650)
        assert opened["number"] in listed(ana)
        assert opened["number"] in listed(bea)

    def test_what_the_shift_adds_up_is_the_whole_drawers_whoever_charged_it(self, coffee, people):
        ana, bea = people["ana"], people["bea"]
        opened = open_shift(ana)
        sale = charge(bea, "own-shift-cash-0002", [{"product": "COF"}], CASH)
        summary = get(ana, "/cash_register/sessions/detail", session_id=opened["id"]).json()["summary"]
        assert (summary["cash_sales"], summary["expected_cash"]) == (150, 10150)
        rows = get(ana, "/cash_register/movements", session_id=opened["id"]).json()["rows"]
        assert [row["sale_number"] for row in rows] == [sale["number"]]

    def test_a_forgotten_shift_that_closed_by_itself_stays_its_openers(self, people):
        ana, bea = people["ana"], people["bea"]
        forgotten = open_shift(bea)
        Session.objects.filter(pk=forgotten["id"]).update(opened_at=timezone.now() - dt.timedelta(days=2))
        run("cash_register.settings.update", {"auto_close_enabled": True})
        # Ana's opening closes Bea's forgotten shift first, by itself: it is not Ana's for that.
        opened = open_shift(ana)
        assert Session.objects.get(pk=forgotten["id"]).auto_closed is True
        assert listed(ana) == {opened["number"]}
        assert forgotten["number"] in listed(bea)


class TestWhoSeesEveryShift:
    def test_the_manager_lists_opens_and_prints_everyones(self, people, shifts):
        marta, theirs = people["marta"], shifts["bea"]["id"]
        assert listed(marta) == {shifts["ana"]["number"], shifts["bea"]["number"]}
        assert get(marta, "/cash_register/sessions/detail", session_id=theirs).status_code == 200
        assert get(marta, "/cash_register/movements", session_id=theirs).status_code == 200
        assert post(marta, "/cash_register/sessions/print", {"session_id": theirs}).status_code == 200

    def test_the_owner_the_administrator_and_the_manager_hold_it_the_employee_does_not(self):
        configs = all_live_app_configs()
        declared = next(config for config in configs if config.label == "cash_register").permissions
        assert "cash_register.view_all_sessions" in declared
        assert SESSIONS.all_permission == "cash_register.view_all_sessions"
        roles = ("hub_owner", "hub_admin", "hub_manager")
        assert {role: ctx_for(role).has("cash_register.view_all_sessions") for role in roles} == dict.fromkeys(
            roles, True
        )
        assert "cash_register.view_all_sessions" not in permissions_for_role(configs, "hub_employee")

    def test_a_caller_that_is_not_a_person_reaches_every_shift(self, shifts):
        # An API key, an automation or the platform has nothing of its own: its permission opens the shifts.
        page = run("cash_register.session.list", {}, ctx_for("hub_employee", actor="flow:7"))
        assert {row.number for row in page.rows} == {shifts["ana"]["number"], shifts["bea"]["number"]}


class TestWhatTheCompsCost:
    """A comp is given at cost: what it cost the business is a cost, seen only with ``base.view_costs``."""

    @pytest.fixture
    def comped(self, shirt, people):
        opened = open_shift(people["ana"])
        charge(people["marta"], "own-shift-comp-0001", [{"product": "SHIRT", "is_gift": True, "gift_reason": "birthday"}])
        return opened

    def test_an_employee_reads_the_comps_of_their_shift_without_their_cost(self, people, comped):
        def seen(client):
            summary = get(client, "/cash_register/sessions/detail", session_id=comped["id"]).json()["summary"]
            (line,) = get(client, "/cash_register/movements", session_id=comped["id"]).json()["rows"]
            return summary["total_gifts"], line["gift_total"]

        assert seen(people["ana"]) == (None, None)
        assert seen(people["marta"]) == (4000, 4000)

    def test_nor_on_its_paper(self, people, comped):
        run("printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"})

        def paper(client) -> dict:
            printed = post(client, "/cash_register/sessions/print", {"session_id": comped["id"]})
            assert printed.status_code == 200, printed.content
            document = PrintJob.objects.get(pk=printed.json()["job_id"]).document
            return {line["label"]: line["amount"] for line in document["transactions"]}

        employees, managers = paper(people["ana"]), paper(people["marta"])
        assert {label: amount for label, amount in managers.items() if label not in employees} == {"Comps": 40.0}
        assert all(managers[label] == amount for label, amount in employees.items())
