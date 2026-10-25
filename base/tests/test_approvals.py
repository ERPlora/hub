"""BASE-G136 and G145: a manager's PIN lets one refused action through, and Employees › Approvals keeps the record.

An app names the commands of its own that a manager may approve on the spot (``LiveAppConfig.approvals``: operation →
what is approved, in words). Whoever lacks the permission of one of them gets, instead of a flat refusal,
``requires_elevation`` with what is approved and a fingerprint of that exact request; somebody of the business who
holds the permission approves it with their PIN (or their badge) and the hub hands back a pass of one use, for two
minutes, bound to that person, that command, that very request and this business. The command repeated with the pass
goes through once; the record (who asked, who approved, what, when, whether it was used) stays in the hub and only who
runs the business reads it. A query, a command no app names and a command the caller may run anyway never ask. The
PIN is checked as the PIN pad checks it (APP-BASE-3): same hash, same brakes.
"""

import csv
import datetime as dt
import io
import json
import secrets

import pytest
from django.apps import apps
from django.core.cache import cache
from django.utils import timezone
from live.models import OutboxEvent

from base.models import AccessSettings, Approval, Membership
from base.tests.test_people import with_badge, with_pin

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
B_HOST = "b.localhost:8000"
APPROVABLE = "base.access.settings_update"
SETTINGS = "/access/settings/update"
CHANGE = {"pin_policy": "always", "pin_inactivity_minutes": 5, "pin_length": 4}
OTHER_CHANGE = {"pin_policy": "never", "pin_inactivity_minutes": 5, "pin_length": 4}


def post(client, path, body=None, host=HOST, **headers):
    return client.post(f"/api{path}", json.dumps(body or {}), content_type="application/json", HTTP_HOST=host, **headers)


def get(client, path, host=HOST, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def code(response) -> str:
    return response.json()["error"]["code"]


def with_pass(token: str) -> dict:
    return {"HTTP_X_ELEVATION_TOKEN": token}


@pytest.fixture(autouse=True)
def approvable(monkeypatch):
    """``base`` names one of its commands as approvable, as an app would in its ``LiveAppConfig``."""
    monkeypatch.setattr(apps.get_app_config("base"), "approvals", {APPROVABLE: "Change how the till asks who is there"}, raising=False)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def adam(make_user):
    user = make_user("saas:2", host="a", role=Membership.Role.ADMIN, first_name="Adam")
    with_pin("saas:2", "2580")
    return user


@pytest.fixture
def eva(make_user, client):
    user = make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva")
    client.force_login(user)
    return user


@pytest.fixture
def mario(make_user):
    user = make_user("saas:4", host="a", role=Membership.Role.MANAGER, first_name="Mario")
    with_pin("saas:4", "1357")
    return user


def refused(client, body=CHANGE, host=HOST) -> dict:
    response = post(client, SETTINGS, body, host=host)
    assert response.status_code == 403, response.content
    assert code(response) == "requires_elevation"
    return response.json()["error"]["approval"]


def approve(client, asked: dict, person: str, pin: str = "2580", host=HOST):
    credential = person_id(person)
    body = {"operation": asked["operation"], "fingerprint": asked["fingerprint"], "person": credential, "pin": pin}
    return post(client, "/approvals", body, host=host)


def person_id(username: str) -> str:
    from base.models import Credential

    return str(Credential.objects.get(username=username).pk)


def granted(client, person="saas:2", pin="2580") -> str:
    response = approve(client, refused(client), person, pin)
    assert response.status_code == 200, response.content
    return response.json()["token"]


class TestAskingForApproval:
    def test_a_refusal_that_a_manager_can_lift_asks_for_approval_naming_what_and_writes_nothing(self, client, adam, eva):
        asked = refused(client)
        assert asked["operation"] == APPROVABLE
        assert asked["label"] == "Change how the till asks who is there"
        assert len(asked["fingerprint"]) == 64
        assert AccessSettings.objects.filter(pin_policy="always").count() == 0

    def test_a_command_no_app_names_is_refused_flat(self, client, adam, eva):
        response = post(client, "/devices/prune", {})
        assert response.status_code == 403
        assert code(response) == "permission_denied"

    def test_a_query_is_refused_flat_even_when_an_app_names_it(self, client, adam, eva, monkeypatch):
        monkeypatch.setattr(apps.get_app_config("base"), "approvals", {"base.device.list": "See the devices"}, raising=False)
        response = get(client, "/devices")
        assert response.status_code == 403
        assert code(response) == "permission_denied"

    def test_an_app_cannot_make_another_apps_command_approvable(self, client, adam, eva, monkeypatch):
        monkeypatch.setattr(apps.get_app_config("base"), "approvals", {}, raising=False)
        monkeypatch.setattr(apps.get_app_config("table"), "approvals", {APPROVABLE: "Borrowed"}, raising=False)
        response = post(client, SETTINGS, CHANGE)
        assert code(response) == "permission_denied"

    def test_who_may_run_it_never_sees_the_question(self, client, adam):
        client.force_login(adam)
        response = post(client, SETTINGS, CHANGE)
        assert response.status_code == 200, response.content

    def test_without_a_session_it_is_no_question_either(self, client, adam):
        response = post(client, SETTINGS, CHANGE)
        assert response.status_code == 401


class TestApproving:
    def test_the_managers_pin_lets_the_refused_action_through_once(self, client, adam, eva):
        token = granted(client)
        response = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert response.status_code == 200, response.content
        assert response.json()["pin_policy"] == "always"
        again = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert code(again) == "requires_elevation"

    def test_the_answer_names_who_approved_and_how_long_the_pass_lasts(self, client, adam, eva):
        response = approve(client, refused(client), "saas:2")
        answer = response.json()
        assert answer["approver"] == "Adam"
        assert answer["expires_in"] == 120
        assert answer["token"].startswith("elev_")

    def test_the_record_says_who_asked_who_approved_what_and_that_it_was_used(self, client, adam, eva):
        token = granted(client)
        post(client, SETTINGS, CHANGE, **with_pass(token))
        record = Approval.objects.get()
        assert (record.requested_by, record.approved_by, record.operation) == ("saas:3", "saas:2", APPROVABLE)
        assert record.requested_by_name == "Eva" and record.approved_by_name == "Adam"
        assert record.used_at is not None
        assert token not in record.token_digest
        events = list(OutboxEvent.objects.filter(name="base.approval.granted").values_list("payload", flat=True))
        assert events == [{"id": str(record.pk), "operation": APPROVABLE}]

    def test_a_wrong_pin_or_an_unknown_person_approve_nothing_and_say_the_same(self, client, adam, eva):
        asked = refused(client)
        wrong = approve(client, asked, "saas:2", pin="0000")
        assert wrong.status_code == 401 and code(wrong) == "base.approval_refused"
        unknown = post(client, "/approvals", {**asked, "person": "0190a1b2-0000-7000-8000-000000000000", "pin": "2580"})
        assert unknown.status_code == 401 and code(unknown) == "base.approval_refused"
        assert Approval.objects.count() == 0

    def test_five_wrong_pins_for_one_person_brake_the_next_try(self, client, adam, eva):
        asked = refused(client)
        for _ in range(5):
            approve(client, asked, "saas:2", pin="0000")
        braked = approve(client, asked, "saas:2")
        assert braked.status_code == 429 and code(braked) == "base.too_many_attempts"

    def test_only_somebody_who_could_do_it_themselves_approves_it(self, client, adam, eva, mario):
        response = approve(client, refused(client), "saas:4", pin="1357")
        assert response.status_code == 403 and code(response) == "base.approver_cannot"

    def test_nothing_is_approved_for_who_already_holds_the_permission(self, client, adam, make_user):
        olga = make_user("saas:1", host="a", role=Membership.Role.OWNER, first_name="Olga")
        client.force_login(olga)
        asked = {"operation": APPROVABLE, "fingerprint": "0" * 64}
        response = approve(client, asked, "saas:2")
        assert response.status_code == 409 and code(response) == "base.approval_not_needed"

    def test_a_query_is_never_approved_by_pin_even_named(self, client, adam, eva, monkeypatch):
        monkeypatch.setattr(apps.get_app_config("base"), "approvals", {"base.device.list": "See the devices"}, raising=False)
        response = approve(client, {"operation": "base.device.list", "fingerprint": "0" * 64}, "saas:2")
        assert response.status_code == 409 and code(response) == "base.approval_not_offered"
        assert Approval.objects.count() == 0

    def test_a_command_nobody_names_is_not_approved_by_pin(self, client, adam, eva):
        response = approve(client, {"operation": "base.device.prune", "fingerprint": "0" * 64}, "saas:2")
        assert response.status_code == 409 and code(response) == "base.approval_not_offered"

    def test_a_badge_approves_as_the_pin_does(self, client, adam, eva):
        with_badge("saas:2", "CARD-0002")
        asked = refused(client)
        response = post(client, "/approvals", {"operation": asked["operation"], "fingerprint": asked["fingerprint"], "badge": "CARD-0002"})
        assert response.status_code == 200, response.content
        assert response.json()["approver"] == "Adam"

    def test_who_may_approve_is_offered_by_name_only_those_with_a_pin_who_hold_the_permission(self, client, adam, eva, mario):
        response = get(client, "/approvals/approvers", operation=APPROVABLE)
        assert response.status_code == 200, response.content
        assert [person["name"] for person in response.json()["people"]] == ["Adam"]
        assert response.json()["people"][0]["id"] == person_id("saas:2")
        assert response.json()["pin_length"] == 4


class TestThePassIsBound:
    def test_to_that_very_request(self, client, adam, eva):
        token = granted(client)
        response = post(client, SETTINGS, OTHER_CHANGE, **with_pass(token))
        assert code(response) == "requires_elevation"
        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200

    def test_to_that_command(self, client, adam, eva):
        token = granted(client)
        response = post(client, "/devices/prune", {}, **with_pass(token))
        assert code(response) == "permission_denied"

    def test_to_the_person_who_asked(self, client, adam, eva, make_user):
        token = granted(client)
        ana = make_user("saas:5", host="a", role=Membership.Role.EMPLOYEE, first_name="Ana")
        client.force_login(ana)
        assert code(post(client, SETTINGS, CHANGE, **with_pass(token))) == "requires_elevation"

    def test_to_this_business(self, client, adam, eva):
        Membership.objects.create(user=eva, host="b", role=Membership.Role.EMPLOYEE)
        token = granted(client)
        assert code(post(client, SETTINGS, CHANGE, host=B_HOST, **with_pass(token))) == "requires_elevation"

    def test_for_two_minutes(self, client, adam, eva):
        token = granted(client)
        Approval.objects.update(expires_at=Approval.objects.get().created_at - dt.timedelta(seconds=1))
        assert code(post(client, SETTINGS, CHANGE, **with_pass(token))) == "requires_elevation"

    def test_a_token_nobody_minted_authorises_nothing(self, client, adam, eva):
        """Also with a real pass waiting for this same request: the pass is the token, not the request it names."""
        assert code(post(client, SETTINGS, CHANGE, **with_pass("elev_forged"))) == "requires_elevation"
        token = granted(client)
        forged = "elev_" + "f" * (len(token) - len("elev_"))
        assert code(post(client, SETTINGS, CHANGE, **with_pass(forged))) == "requires_elevation"
        assert Approval.objects.get().used_at is None
        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200


class TestTheRecord:
    def test_who_runs_the_business_reads_it_in_words_newest_first(self, client, adam, eva):
        token = granted(client)
        post(client, SETTINGS, CHANGE, **with_pass(token))
        client.force_login(adam)
        response = get(client, "/approvals")
        assert response.status_code == 200, response.content
        [row] = response.json()["approvals"]
        assert row["action"] == "Change how the till asks who is there"
        assert (row["requested_by"], row["approved_by"], row["used"]) == ("Eva", "Adam", True)

    def test_an_employee_cannot_read_it(self, client, adam, eva):
        response = get(client, "/approvals")
        assert response.status_code == 403


def recorded(operation=APPROVABLE, *, way="pin", used=True, at=None, asked="Eva", approver="Adam") -> Approval:
    """An approval on the record, as `base.approval.approve` leaves it (`at`: when it was approved)."""
    row = Approval.objects.create(
        operation=operation,
        permission="base.manage",
        fingerprint=secrets.token_hex(32),
        token_digest=secrets.token_hex(32),
        requested_by="saas:3",
        requested_by_name=asked,
        approved_by="saas:2",
        approved_by_name=approver,
        way=way,
        expires_at=timezone.now() + dt.timedelta(minutes=2),
        used_at=timezone.now() if used else None,
    )
    if at is not None:
        Approval.objects.filter(pk=row.pk).update(created_at=at)
    return row


def exported(client, language="en", **filters):
    response = client.get("/api/approvals/export", filters, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 200, response.content
    return response.json()


def lines(file: dict) -> list[list[str]]:
    return list(csv.reader(io.StringIO(file["csv"])))


class TestTheExport:
    """Employees › Approvals › «Export CSV» (BASE-F85; the old hub exported its record): the server writes the file
    with every approval the search and the filters keep, in words and in the person's language."""

    def test_an_employee_cannot_export_it(self, client, adam, eva):
        response = client.get("/api/approvals/export", HTTP_HOST=HOST)
        assert response.status_code == 403

    def test_who_runs_the_business_gets_it_in_words_and_in_their_language(self, client, adam, eva):
        recorded(at=dt.datetime(2026, 10, 24, 9, 30, tzinfo=dt.UTC))
        recorded(way="badge", used=False, at=dt.datetime(2026, 10, 23, 18, 5, tzinfo=dt.UTC), asked="Ana", approver="Mario")
        client.force_login(adam)
        file = exported(client, "es")
        assert (file["filename"], file["content_type"], file["rows"]) == ("approvals.csv", "text/csv", 2)
        assert lines(file) == [
            ["Cuándo", "Acción", "Autorizado por", "Lo pidió", "Con", "Estado"],
            ["2026-10-24 11:30", "Change how the till asks who is there", "Adam", "Eva", "PIN", "Usada"],
            ["2026-10-23 20:05", "Change how the till asks who is there", "Mario", "Ana", "Placa", "Sin usar"],
        ]
        assert "base.access" not in file["csv"]

    def test_in_english_too(self, client, adam, eva):
        recorded(way="badge", used=False)
        client.force_login(adam)
        [header, row] = lines(exported(client, "en"))
        assert header == ["When", "Action", "Approved by", "Asked by", "With", "State"]
        assert row[4:] == ["Badge", "Not used"]

    def test_nothing_yet_is_only_the_header(self, client, adam, eva):
        client.force_login(adam)
        file = exported(client)
        assert file["rows"] == 0
        assert lines(file) == [["When", "Action", "Approved by", "Asked by", "With", "State"]]

    def test_the_filters_and_the_search_of_the_list(self, client, adam, eva):
        recorded(at=dt.datetime(2026, 10, 20, 12, tzinfo=dt.UTC), asked="Eva")
        recorded("ghost.thing.do", at=dt.datetime(2026, 10, 22, 12, tzinfo=dt.UTC), asked="Ana")
        recorded(way="badge", used=False, at=dt.datetime(2026, 10, 24, 12, tzinfo=dt.UTC), asked="Luis", approver="Mario")
        client.force_login(adam)

        def asked(**filters) -> list[str]:
            return [row[3] for row in lines(exported(client, **filters))[1:]]

        assert asked() == ["Luis", "Ana", "Eva"]
        assert asked(at_from="2026-10-21") == ["Luis", "Ana"]
        assert asked(at_to="2026-10-22") == ["Ana", "Eva"]
        assert asked(at_from="2026-10-21", at_to="2026-10-23") == ["Ana"]
        assert asked(operation="ghost.thing.do") == ["Ana"]
        assert asked(way="badge") == ["Luis"]
        assert asked(used="false") == ["Luis"]
        assert asked(used="true") == ["Ana", "Eva"]
        # The search reads what the list shows: the action in words and the two names, in any case.
        assert asked(search="mario") == ["Luis"]
        assert asked(search="ANA") == ["Ana"]
        assert asked(search="no app names") == ["Ana"]
        assert asked(search="till", way="pin") == ["Eva"]

    def test_a_name_a_spreadsheet_would_run_is_written_as_text(self, client, adam, eva):
        recorded(asked="=HYPERLINK(1)")
        client.force_login(adam)
        [_, row] = lines(exported(client))
        assert row[3] == "'=HYPERLINK(1)"


class TestFollowedLive:
    def test_the_record_follows_each_approval_and_each_pass_spent_and_who_approves_the_people(self):
        from live.live_registry import live_registry

        from base import events

        on = live_registry.subscribable
        assert on["base.approval.list"] == sorted({events.APPROVAL_GRANTED, events.APPROVAL_USED})
        assert on["base.approval.approvers"] == sorted(
            {events.PIN_SET, events.PROFILE_UPDATED, events.HUB_STATE_APPLIED, *events.PERSON_EVENTS}
        )


APPROVAL_ROUTES = {
    ("GET", "/approvals", "base.approval.list"),
    ("GET", "/approvals/approvers", "base.approval.approvers"),
    ("GET", "/approvals/export", "base.approval.export"),
    ("POST", "/approvals", "base.approval.approve"),
}



class TestNotOfTheBusiness:
    """rv-hub-244: whoever is not of the business gets the refusal of always, never the approval's question with what
    it would approve."""

    def test_a_session_of_another_business_is_refused_flat(self, client, adam, make_user):
        stranger = make_user("saas:9", host="b", role=Membership.Role.EMPLOYEE, first_name="Zoe")
        client.force_login(stranger)
        response = post(client, SETTINGS, CHANGE)
        assert response.status_code == 403, response.content
        assert code(response) == "permission_denied"
        assert "approval" not in response.json()["error"]

    def test_a_session_of_nobody_s_business_is_refused_flat(self, client, adam, make_user):
        client.force_login(make_user("saas:10", first_name="Nobody"))
        response = post(client, SETTINGS, CHANGE)
        assert response.status_code == 403, response.content
        assert code(response) == "permission_denied"
        assert "approval" not in response.json()["error"]


class TestACommandThatTouchesNoDatabase:
    """rv-live-10: a manager's pass is spent in the transaction of the command it lets through (base.approval_spend).
    A command declared ``database=False`` (live#10) opens none, so naming it approvable is an error of the declaration,
    said at start, and never a ``LiveMisuse`` at the till."""

    NO_DATABASE = "base.assistant.report"

    def test_it_is_refused_at_start_with_a_clear_error(self, monkeypatch):
        from django.core import checks
        from live.operations import get as get_operation

        assert get_operation(self.NO_DATABASE).database is False
        monkeypatch.setattr(apps.get_app_config("base"), "approvals", {self.NO_DATABASE: "Report an answer"}, raising=False)
        errors = [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E004"]
        assert len(errors) == 1
        assert self.NO_DATABASE in errors[0].msg and "database=False" in errors[0].msg

    def test_the_apps_of_today_name_none(self):
        from django.core import checks

        assert [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E004"] == []

    def test_it_is_never_approvable_even_without_the_check(self, monkeypatch):
        from base.approvals import approvable

        monkeypatch.setattr(apps.get_app_config("base"), "approvals", {self.NO_DATABASE: "Report an answer"}, raising=False)
        assert approvable(self.NO_DATABASE) is None
