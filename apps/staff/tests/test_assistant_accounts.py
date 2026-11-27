"""STAFF-F03 from the assistant: «link Ana's record to her account». The model reads the accounts a record can hang from
in the same list as the record form's selector (``staff.account.list``), with the id the record takes; the card says
the name of the account it links, and an account it cannot name never reaches a card."""

import json
import uuid

import pytest
from live.operations import get

from apps.staff.models import Member
from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import assert_offered_or_found, place_of_no_ask
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, the_model_hears, turn_as, yes_to
from base.tests.test_services_assistant import call

from .conftest import HUB_DB, B, ctx_for, make_member

pytestmark = HUB_DB

ADMIN = "hub_admin"


@pytest.fixture
def ana(make_user):
    """Ana's account: an employee of the business who already gets in at the till with her PIN."""
    return make_user("saas:ana", role=Membership.Role.EMPLOYEE, first_name="Ana")


def as_person(role: str = ADMIN, language: str = "es"):
    return ctx_for(role, actor=f"asker-{role}", language=language)


def heard(plan: dict) -> dict:
    """What the model hears of the read it asked for."""
    return json.loads(plan["append"][0]["content"])


def linking(member: Member, user_id) -> dict:
    return call("staff.member.update", {"id": str(member.id), "user_id": str(user_id)})


@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER])
def test_whoever_links_records_has_the_list_of_the_accounts_in_the_assistant(catalog_of, role):
    assert "staff.account.list" in catalog_of(role, "es")


def test_asked_to_hook_ana_s_record_to_her_user_the_turn_offers_the_change_and_its_search_finds_the_accounts(
    catalog_of,
):
    """The QA's words: «enganchar» is to link (Staff's own words), so the change of a record is offered, and the search
    the model makes for what its account datum names finds the accounts."""
    tools = catalog_of(Membership.Role.ADMIN, "es")
    phrase = "La ficha de Ana engánchala a su usuario, que ella ya entra en la tablet con su PIN."
    assert place_of_no_ask(tools, "staff.member.update", phrase) is not None
    assert_offered_or_found(tools, "staff.account.list", phrase, task="vincular usuario a ficha de personal")


def test_a_record_asks_for_its_account_by_the_id_the_accounts_list_gives():
    for name in ("staff.member.create", "staff.member.update"):
        datum = get(name).input.model_json_schema()["properties"]["user_id"]
        assert "staff.account.list" in datum["description"], name


def test_ana_s_record_is_linked_to_her_account_from_the_assistant(ana):
    """The model reads the accounts, sends the id it read, the card names Ana's account, and the yes links them."""
    record = make_member("Ana", "Martín")
    person = as_person()

    read = heard(turn_as(person, call("staff.account.list", {"search": "Ana"})))
    assert [row["name"] for row in read["rows"]] == ["Ana"]

    plan = turn_as(person, linking(record, read["rows"][0]["user_id"]))
    shown = {field["name"]: field["value"] for field in plan["confirm"]["fields"]}
    assert shown == {"id": "Ana Martín", "user_id": "Ana"}

    done = yes_to(plan, turn_of=lambda *calls, decision: turn_as(person, *calls, decision=decision))
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    record.refresh_from_db()
    assert record.user_id == ana.person.id


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_card_of_a_new_record_names_the_account_it_links(ana, language):
    card = assistant.cards.card(
        get("staff.member.create"),
        {"first_name": "Ana", "last_name": "Martín", "user_id": str(ana.person.id)},
        language,
        as_person(language=language),
    )
    assert [field["value"] for field in card["fields"] if field["name"] == "user_id"] == ["Ana"]


@pytest.fixture
def unnameable(make_user):
    """Ids that name no account of this business: another business's, a deactivated one's, and nobody's."""
    elsewhere = make_user("saas:eva", host=B.key, first_name="Eva")
    gone = make_user("saas:leo", role=Membership.Role.EMPLOYEE, first_name="Leo")
    gone.is_active = False
    gone.save()
    return {"another business's": elsewhere.person.id, "deactivated": gone.person.id, "nobody's": uuid.uuid4()}


def test_an_account_the_card_cannot_name_gets_no_card_and_the_model_hears_which_datum(unnameable):
    record = make_member("Ana", "Martín")
    for why, user_id in unnameable.items():
        plan = turn_as(as_person(), linking(record, user_id))
        no_card_but_the_model_hears(plan, "invalid_payload")
        assert set(the_model_hears(plan)["fields"]) == {"user_id"}, why
        new = call("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz", "user_id": str(user_id)})
        no_card_but_the_model_hears(turn_as(as_person(), new), "invalid_payload")
    record.refresh_from_db()
    assert record.user_id is None
    assert Member.objects.count() == 1


def test_a_change_that_links_no_account_still_gets_its_card():
    """Positive control: the account's check reads nothing when the change does not send one."""
    record = make_member("Ana", "Martín")
    plan = turn_as(as_person(), call("staff.member.update", {"id": str(record.id), "phone": "600111222"}))
    assert plan["confirm"]["operation"] == "staff.member.update"


@pytest.mark.parametrize(
    ("permission", "write", "data"),
    [
        ("staff.change_member", "staff.member.update", {"phone": "600111222"}),
        ("staff.add_member", "staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"}),
    ],
)
def test_the_account_s_check_asks_for_no_more_than_the_write_it_checks(permission, write, data):
    """A role of the business's own may edit records without seeing the team: the check before the card asks for what
    the write asks, so the card still comes."""
    record = make_member("Ana", "Martín")
    person = ctx_for(permissions={"base.view_home", permission}, actor="asker")
    sent = {"id": str(record.id), **data} if write == "staff.member.update" else data
    assert turn_as(person, call(write, sent))["confirm"]["operation"] == write

