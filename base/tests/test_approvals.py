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
from base.tenancy.tests.hubs import HUB_DATABASES
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


def recorded(
    operation=APPROVABLE, *, way="pin", used=True, at=None, asked="Eva", approver="Adam", figures=None
) -> Approval:
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
        figures=figures,
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


# ── What is approved, with the figure of that very request (FIX-HUB-BASE-APPROVAL-LABEL-WITHOUT-DISCOUNT-FIGURE) ─────
# hub#2180, hub#2186, sales#398, sales#403: the manager sees how much they approve («a 50 % discount»), as Toast and
# Square print it, not only what kind of action. Beside its words, an app declares in ``approval_figures`` how they are
# said with the figures of the request: sentences tried in order, whose holes name fields of the command's input
# (``{field}``, ``{field, percent}``, ``{field, money}``); the first one whose every hole fills is said. The figures are
# read from the input as the command's own schema validates it, never from the raw body, and only the fields a sentence
# names; a hole fills with no empty value and no zero; none fills, or no declaration: the words of always.

FIGURED = {APPROVABLE: ["Lock the till after {pin_inactivity_minutes} minutes with {pin_length} digits",
                        "Lock the till after {pin_inactivity_minutes} minutes"]}
PERCENT = {APPROVABLE: ["Lock the till at {pin_inactivity_minutes, percent}"]}
THIRTY = {"pin_policy": "always", "pin_inactivity_minutes": 30}


def declare(monkeypatch, figures: dict, config: str = "base") -> None:
    monkeypatch.setattr(apps.get_app_config(config), "approval_figures", figures, raising=False)


def asked_in(client, language: str, body=THIRTY) -> dict:
    response = client.post(
        f"/api{SETTINGS}", json.dumps(body), content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE=language
    )
    assert response.status_code == 403, response.content
    assert code(response) == "requires_elevation"
    return response.json()["error"]["approval"]


class TestTheFigure:
    def test_the_question_says_the_figure_of_that_very_request_in_the_person_s_language(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, PERCENT)
        assert asked_in(client, "en")["label"] == "Lock the till at 30%"
        assert asked_in(client, "es")["label"] == "Lock the till at 30\xa0%"

    def test_the_first_sentence_whose_every_hole_fills_is_said(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, FIGURED)
        assert asked_in(client, "en", {**THIRTY, "pin_length": 6})["label"] == "Lock the till after 30 minutes with 6 digits"
        # No ``pin_length`` in this request: its sentence does not fill, the next one does.
        assert asked_in(client, "en")["label"] == "Lock the till after 30 minutes"

    def test_no_sentence_that_fills_is_the_words_of_always(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, FIGURED)
        assert asked_in(client, "en", {"pin_policy": "never"})["label"] == "Change how the till asks who is there"

    def test_without_a_declaration_it_is_the_words_of_always(self, client, adam, eva):
        assert asked_in(client, "en")["label"] == "Change how the till asks who is there"

    def test_an_input_the_command_does_not_take_is_the_words_of_always_and_no_new_error(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, PERCENT)
        # The raw body says 30, but the command's schema refuses it (an unknown policy): no figure is read from it.
        asked = asked_in(client, "en", {"pin_policy": "bogus", "pin_inactivity_minutes": 30})
        assert asked["label"] == "Change how the till asks who is there"
        # A text where the command takes a number: refused by its schema, so no figure either.
        assert asked_in(client, "en", {"pin_inactivity_minutes": "30"})["label"] == "Change how the till asks who is there"

    def test_the_figure_is_the_validated_input_s_not_the_body_s(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, FIGURED)
        # The body says 30.0; the command's schema reads 30, and 30 is what the manager reads.
        assert asked_in(client, "en", {"pin_inactivity_minutes": 30.0})["label"] == "Lock the till after 30 minutes"

    def test_the_fingerprint_does_not_change_with_the_declaration(self, client, adam, eva, monkeypatch):
        before = asked_in(client, "en")["fingerprint"]
        declare(monkeypatch, PERCENT)
        assert asked_in(client, "en")["fingerprint"] == before

    def test_another_app_cannot_say_the_figures_of_a_command_of_base(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, PERCENT, config="table")
        assert asked_in(client, "en")["label"] == "Change how the till asks who is there"


class TestTheFigureOnTheRecord:
    """BASE-F85: the record says the figure of what was done with the approval, in the language of who reads it; an
    approval nobody used says the action without one (nothing was done)."""

    def test_the_pass_spent_keeps_only_the_figures_its_sentences_name(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, FIGURED)
        asked = asked_in(client, "en")
        token = approve(client, asked, "saas:2").json()["token"]
        assert Approval.objects.get().figures is None
        assert post(client, SETTINGS, THIRTY, **with_pass(token)).status_code == 200
        assert Approval.objects.get().figures == {"pin_inactivity_minutes": 30, "pin_length": None}

    def test_the_list_says_the_figure_in_the_reader_s_language_and_the_action_without_it_for_its_filter(
        self, client, adam, eva, monkeypatch
    ):
        declare(monkeypatch, PERCENT)
        token = approve(client, asked_in(client, "en"), "saas:2").json()["token"]
        post(client, SETTINGS, THIRTY, **with_pass(token))
        recorded(used=False)
        client.force_login(adam)
        rows = client.get("/api/approvals", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").json()["approvals"]
        assert [row["action"] for row in rows] == ["Change how the till asks who is there", "Lock the till at 30\xa0%"]
        assert {row["operation_label"] for row in rows} == {"Change how the till asks who is there"}
        [_, used] = client.get("/api/approvals", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="en").json()["approvals"]
        assert used["action"] == "Lock the till at 30%"

    def test_the_export_says_it_and_its_search_finds_it(self, client, adam, eva, monkeypatch):
        declare(monkeypatch, PERCENT)
        recorded(asked="Eva", figures={"pin_inactivity_minutes": 30})
        recorded(asked="Ana", figures={"pin_inactivity_minutes": 5})
        client.force_login(adam)
        assert [row[1] for row in lines(exported(client, "es"))[1:]] == ["Lock the till at 5\xa0%", "Lock the till at 30\xa0%"]
        assert [row[3] for row in lines(exported(client, "en", search="30%"))[1:]] == ["Eva"]
        assert [row[3] for row in lines(exported(client, "en", search="till"))[1:]] == ["Ana", "Eva"]

class TestTheFigureOfEachHub:
    """Two hubs with their own databases (phase 2): the figure approved in one is never on the other's record."""

    pytestmark = pytest.mark.django_db(databases=HUB_DATABASES)

    @pytest.fixture(autouse=True)
    def as_in_production(self, monkeypatch):
        from base.tenancy import context

        monkeypatch.setattr(context, "_test_fallback", None)

    def test_each_record_says_only_its_own(self, client, hub_a, hub_b, monkeypatch):
        from django.contrib.auth import get_user_model

        from base.tenancy.context import use_hub

        declare(monkeypatch, PERCENT)
        with use_hub(hub_a):
            recorded(figures={"pin_inactivity_minutes": 30})
        with use_hub(hub_b):
            recorded(figures={"pin_inactivity_minutes": 5})
        boss, _ = get_user_model().objects.get_or_create(username="saas:21", defaults={"first_name": "Bea"})
        for hub in (hub_a, hub_b):
            Membership.objects.get_or_create(user=boss, host=hub.slug, defaults={"role": Membership.Role.ADMIN})
        client.force_login(boss)

        def actions(hub) -> list[str]:
            response = client.get("/api/approvals", HTTP_HOST=f"{hub.slug}.localhost:8000")
            assert response.status_code == 200, response.content
            return [row["action"] for row in response.json()["approvals"]]

        assert actions(hub_a) == ["Lock the till at 30%"]
        assert actions(hub_b) == ["Lock the till at 5%"]


class TestTheFiguresOfTheTill:
    """The sentences Sales will declare (its FIX, ``espera: base``), on its real commands and their schemas: a percent
    and an amount in the business's currency, and the check's discount that may carry either or both (hub#2186: never
    «and 0.00 €»)."""

    CHECK = "sale.order.set_discount_over_limit"
    LINE = "sale.order.set_line_discount_over_limit"
    SENTENCES = {
        CHECK: [
            "Discount the check by {discount_percent, percent} and {discount_amount, money}",
            "Discount the check by {discount_percent, percent}",
            "Discount the check by {discount_amount, money}",
        ],
        LINE: ["Discount a line by {discount_percent, percent}"],
    }

    @pytest.fixture(autouse=True)
    def in_spain(self, monkeypatch):
        from base.models import Hub

        Hub.objects.update_or_create(slug="a", defaults={"status": "ready", "name": "A", "country": "ES"})
        declare(monkeypatch, self.SENTENCES, config="sale")

    def said(self, name: str, language: str = "en", **data) -> str:
        from django.utils import translation
        from live.context import Scope
        from live.operations import get as get_operation

        from base.approvals import figures_of, label_of

        op = get_operation(name)
        with translation.override(language):
            return label_of(op, figures_of(op, op.input.model_validate(data)), Scope("host", "a"))

    def test_a_line_discount_says_its_percent(self):
        line = {"order_id": "0190a1b2-0000-7000-8000-000000000001", "line_id": "0190a1b2-0000-7000-8000-000000000002"}
        assert self.said(self.LINE, discount_percent="50", **line) == "Discount a line by 50%"
        assert self.said(self.LINE, "es", discount_percent="12.5", **line) == "Discount a line by 12,5\xa0%"

    def test_the_check_s_discount_names_what_it_has_and_never_a_zero(self):
        order = {"order_id": "0190a1b2-0000-7000-8000-000000000001"}
        assert self.said(self.CHECK, discount_percent="50", discount_amount=123456, **order) == (
            "Discount the check by 50% and €1,234.56"
        )
        assert self.said(self.CHECK, "es", discount_percent="50", discount_amount=0, **order) == "Discount the check by 50\xa0%"
        assert self.said(self.CHECK, "es", discount_percent="50", **order) == "Discount the check by 50\xa0%"
        assert self.said(self.CHECK, "es", discount_percent="0", discount_amount=500, **order) == "Discount the check by 5,00\xa0€"

    def test_the_amount_is_in_the_business_s_currency(self):
        from base.models import Hub

        Hub.objects.filter(slug="a").update(country="JP")
        order = {"order_id": "0190a1b2-0000-7000-8000-000000000001"}
        assert self.said(self.CHECK, discount_percent="0", discount_amount=500, **order) == "Discount the check by ¥500"

    def test_a_business_whose_currency_is_unknown_says_the_words_of_always(self):
        from base.models import Hub

        Hub.objects.filter(slug="a").delete()
        order = {"order_id": "0190a1b2-0000-7000-8000-000000000001"}
        assert self.said(self.CHECK, discount_percent="0", discount_amount=500, **order) == "Discount the check above the maximum"


class TestTheFiguresAreCheckedAtStart:
    """``base.E008``: a sentence names a command of its own app that it names in ``approvals``, fields its input has, and
    a format it knows (``percent`` and ``money`` of a number; ``money`` of whole minor units), the same in every language."""

    def errors(self) -> list:
        from django.core import checks

        return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E008"]

    def test_the_apps_of_today_declare_well(self):
        assert self.errors() == []

    def test_a_field_its_input_does_not_have(self, monkeypatch):
        declare(monkeypatch, {APPROVABLE: ["Lock after {minutes}"]})
        [error] = self.errors()
        assert "minutes" in error.msg and APPROVABLE in error.msg

    def test_a_command_its_approvals_do_not_name(self, monkeypatch):
        declare(monkeypatch, {"base.device.prune": ["Prune {older_than}"]})
        [error] = self.errors()
        assert "base.device.prune" in error.msg

    def test_another_app_s_command(self, monkeypatch):
        declare(monkeypatch, {APPROVABLE: ["Lock after {pin_inactivity_minutes}"]}, config="table")
        [error] = self.errors()
        assert APPROVABLE in error.msg and "table" in error.msg

    def test_a_format_it_does_not_know_or_a_figure_that_is_no_number(self, monkeypatch):
        declare(monkeypatch, {APPROVABLE: ["Lock on {pin_inactivity_minutes, date}", "As {pin_policy, percent}"]})
        assert len(self.errors()) == 2

    def test_a_sentence_with_a_brace_that_closes_no_hole(self, monkeypatch):
        declare(monkeypatch, {APPROVABLE: ["Lock after {pin_inactivity_minutes minutes"]})
        assert len(self.errors()) == 1

    def test_a_translation_that_names_other_holes(self, monkeypatch):
        from django.utils import translation

        class Translated(str):
            """A sentence whose Spanish names another field, as a translator's slip would."""

            def __str__(self) -> str:
                return "Bloquear tras {pin_length}" if translation.get_language() == "es" else "Lock after {pin_inactivity_minutes}"

        declare(monkeypatch, {APPROVABLE: [Translated("Lock after {pin_inactivity_minutes}")]})
        [error] = self.errors()
        assert "es" in error.msg
