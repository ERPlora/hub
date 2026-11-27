"""How a person is named at the till: the faces of the PIN door and of «Switch user», «Who approves it?» and the card of
the user menu.

erplora.com names an account without a name by its address, and nobody is asked for a name when they accept an
invitation. The business names its team in Staff: a record linked to the person's account (STAFF-F03) gives them the
name the business knows them by, as Square, Toast or Fresha show the team member's name at the till. A name of their
own in «My profile» goes first; without either, the account's, as before.
"""

import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext
from live.operations import get as get_operation

from apps.staff.models import Member
from base.models import Membership
from base.models.profile import Profile
from base.queries.people import actor_name, face_name
from base.schemas.approvals import ApproversIn
from base.schemas.sessions import SessionMeIn
from base.services import sessions
from base.tenancy.tests.business import A, HUB_DB, in_business_a
from base.tests.test_access_pin import a_device, door, with_pin
from base.tests.test_app_activation import set_rows

__all__ = ["in_business_a"]

pytestmark = HUB_DB

#: A command of base a manager may approve with their PIN, named for these tests only.
APPROVABLE = "base.access.settings_update"


@pytest.fixture
def ana(make_user):
    """An invited employee: erplora.com named her account by its address."""
    return make_user("saas:1", host=A.key, role=Membership.Role.EMPLOYEE, first_name="ana.qa@example.com", email="ana.qa@example.com")


@pytest.fixture
def olga(make_user):
    return make_user("saas:2", host=A.key, role=Membership.Role.OWNER, first_name="Olga Ruiz", email="olga@example.com")


def staff_record(user, first_name="Ana", last_name="Estilista QA") -> Member:
    return Member.objects.create(first_name=first_name, last_name=last_name, user=sessions.ensure_hub_user(user))


def faces(client) -> list[tuple[str, str]]:
    return [(person["name"], person["initials"]) for person in door(client)["people"]]


def as_person(user) -> OperationContext:
    return OperationContext(scope=A, actor=user, permissions=frozenset({"*"}))


class TestTheGrid:
    def test_an_invited_person_shows_by_the_name_of_their_staff_record_never_their_address(self, client, ana, olga):
        a_device(client)
        with_pin(ana, "4826")
        with_pin(olga, "9071")
        staff_record(ana)

        assert faces(client) == [("Ana Estilista QA", "AE"), ("Olga Ruiz", "OR")]
        assert "example.com" not in json.dumps(door(client))

    def test_a_profile_that_only_kept_the_address_gives_way_to_the_staff_record(self, client, ana):
        # Saving a preference makes the profile with the account's name, which for her is the address.
        a_device(client)
        with_pin(ana, "4826")
        Profile.objects.create(username=ana.username, first_name="ana.qa@example.com")
        staff_record(ana)

        assert faces(client) == [("Ana Estilista QA", "AE")]

    def test_a_name_of_their_own_in_my_profile_goes_before_the_staff_record(self, client, ana):
        a_device(client)
        with_pin(ana, "4826")
        Profile.objects.create(username=ana.username, first_name="Anita", last_name="Gómez")
        staff_record(ana)

        assert faces(client) == [("Anita Gómez", "AG")]

    def test_the_staff_record_names_them_before_the_account_s_name(self, client, olga):
        a_device(client)
        with_pin(olga, "9071")
        staff_record(olga, "Olga", "Propietaria")

        assert faces(client) == [("Olga Propietaria", "OP")]

    def test_without_a_record_of_their_own_they_show_as_before(self, client, ana, olga):
        a_device(client)
        with_pin(ana, "4826")
        staff_record(olga, "Olga", "Propietaria")
        Member.objects.create(first_name="Nobody", last_name="Linked")

        assert faces(client) == [("ana.qa", "A")]

    def test_a_record_far_down_a_long_directory_still_names_them(self, client, ana):
        a_device(client)
        with_pin(ana, "4826")
        Member.objects.bulk_create(Member(first_name="Aaron", last_name=f"Team {number:03}") for number in range(250))
        staff_record(ana, "Zoe", "Estilista")

        assert faces(client) == [("Zoe Estilista", "ZE")]

    def test_with_staff_off_they_show_as_before(self, client, ana):
        a_device(client)
        with_pin(ana, "4826")
        staff_record(ana)
        set_rows()  # every module off

        assert faces(client) == [("ana.qa", "A")]


class TestWhoApproves:
    def test_the_approver_shows_by_the_name_of_their_staff_record(self, monkeypatch, ana, olga):
        monkeypatch.setattr(apps.get_app_config("base"), "approvals", {APPROVABLE: "Change the PIN pad"}, raising=False)
        olga.first_name = "olga@example.com"
        olga.save()
        with_pin(olga, "9071")
        staff_record(olga, "Olga", "Propietaria")

        approvers = get_operation("base.approval.approvers")(as_person(ana), ApproversIn(operation=APPROVABLE))

        assert [(person.name, person.initials) for person in approvers.people] == [("Olga Propietaria", "OP")]


class TestTheUserMenuCard:
    def me(self, user) -> dict:
        return get_operation("base.session.me")(as_person(user), SessionMeIn()).model_dump(mode="json")["user"]

    def test_it_names_an_invited_person_by_their_staff_record(self, ana):
        staff_record(ana)

        assert self.me(ana)["label"] == "Ana Estilista QA"

    def test_without_a_record_it_names_them_as_before(self, ana):
        sessions.ensure_hub_user(ana)

        assert self.me(ana)["label"] == "ana.qa@example.com"


class TestWhoActed:
    """What a person does is signed with the name a colleague reads on the grid: «My profile», else their account's,
    else what goes before the «@» of their e-mail; never an address (CUSTOMER-F03, APPOINTMENT-F10)."""

    def test_a_name_of_their_own_in_my_profile_signs_what_they_do(self, ana, olga):
        Profile.objects.create(username=ana.username, first_name="QA", last_name="Empleado")
        Profile.objects.create(username=olga.username, first_name="Olguita")

        assert [actor_name(ana), actor_name(olga)] == ["QA Empleado", "Olguita"]

    def test_without_one_their_account_s_name_signs(self, olga):
        assert actor_name(olga) == "Olga Ruiz"

    def test_with_no_name_anywhere_what_goes_before_the_at_signs(self, ana, make_user):
        email_only = make_user("saas:3", email="luis.qa@example.com")

        assert [actor_name(ana), actor_name(email_only)] == ["ana.qa", "luis.qa"]

    def test_a_profile_that_only_kept_the_address_never_shows_it(self, ana):
        Profile.objects.create(username=ana.username, first_name="ana.qa@example.com")

        assert actor_name(ana) == "ana.qa"

    def test_whoever_is_not_a_person_is_kept_as_it_comes(self):
        assert [actor_name(None), actor_name("system"), actor_name("API · Zapier")] == ["", "system", "API · Zapier"]

    def test_they_sign_with_the_name_their_face_shows(self, ana, olga, make_user):
        Profile.objects.create(username=ana.username, first_name="QA", last_name="Empleado")
        people = [ana, olga, make_user("saas:3", email="luis.qa@example.com"), make_user("saas:4")]

        assert [actor_name(person) for person in people] == [face_name(person) for person in people]


#: The hub's own code: its apps and its platform.
HUB = Path(__file__).resolve().parents[2]
#: The one place that names a person of the team from their account.
THE_PIECE = HUB / "base" / "queries" / "people.py"
#: A name made from the account itself: ``user.get_full_name() or …`` skips «My profile».
OWN_NAMING = re.compile(r"get_full_name\(\)\s*(or|if)\b")


def test_only_the_common_piece_names_whoever_acts_from_their_account():
    """An app names whoever acts with ``base.queries.people.actor_name``: its own ``get_full_name() or …`` signs an
    invited colleague with their address while the rest of the Hub calls them by their «My profile» name."""
    found = [
        f"{path.relative_to(HUB)}:{number}"
        for folder in ("apps", "base")
        for path in sorted((HUB / folder).rglob("*.py"))
        if path != THE_PIECE and not {"tests", "migrations"} & set(path.parts)
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if OWN_NAMING.search(line)
    ]

    assert found == []
