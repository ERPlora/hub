"""«Role in this business» on a person's page (``base.person.detail``, BASE-F130): the role of the business they hold,
whether who asks may give them another and, when not, why."""

import json

import pytest

from base.models import Membership
from base.roles import ON
from base.tenancy.tests.business import A, HOST, HUB_DB, in_business_a
from base.tests.roles import a_role, held_by
from base.tests.test_services_roles import adam, eva, olga

__all__ = ["adam", "eva", "in_business_a", "olga"]

pytestmark = HUB_DB


def page(client, person: str) -> dict:
    response = client.get("/api/people/detail", {"person": person}, HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    return response.json()


def role_on(answer: dict) -> tuple:
    return answer["business_role"], answer["may"]["give_role"], answer["role_refusal"]


@pytest.fixture
def gema(make_user):
    return make_user("saas:7", host=A.key, role=Membership.Role.ACCOUNTANT, first_name="Gema")


@pytest.fixture
def cashier():
    return a_role("Cashier", sale__view_sale=ON)


class TestWhatItSays:
    def test_the_role_of_the_business_they_hold(self, client, adam, eva, cashier):
        held_by(eva, cashier)
        client.force_login(adam)

        assert role_on(page(client, "saas:3")) == (str(cashier.pk), True, None)

    def test_without_one_the_role_of_their_invitation_rules(self, client, adam, eva):
        client.force_login(adam)

        assert role_on(page(client, "saas:3")) == (None, True, None)

    def test_nobody_gives_the_owner_another(self, client, adam, olga):
        client.force_login(adam)

        assert role_on(page(client, "saas:1")) == (None, False, "base.role_of_owner")

    def test_nobody_changes_their_own(self, client, adam):
        client.force_login(adam)

        assert role_on(page(client, "saas:2")) == (None, False, "base.role_own")

    def test_only_to_somebody_below(self, client, adam, make_user):
        make_user("saas:6", host=A.key, role=Membership.Role.ADMIN, first_name="Ada")
        client.force_login(adam)

        assert role_on(page(client, "saas:6")) == (None, False, "base.role_above")

    def test_the_accountancy_firm_keeps_its_own_even_with_one_from_before(self, client, adam, gema, cashier):
        held_by(gema, cashier)
        client.force_login(adam)

        assert role_on(page(client, "saas:7")) == (None, False, "base.role_of_accountant")

    def test_whoever_does_not_manage_roles_is_told_no_reason(self, client, make_user, eva):
        office = make_user("saas:8", host=A.key, role=Membership.Role.MANAGER, first_name="Otto")
        held_by(office, a_role("Office", base__view_home=ON, base__administer_hub=ON))
        client.force_login(office)

        assert role_on(page(client, "saas:3")) == (None, False, None)


def test_what_it_says_is_what_giving_it_answers(client, adam, gema, cashier):
    """The page offers it exactly when ``base.role.assign`` takes it, and says the code it would answer with."""
    client.force_login(adam)
    for person in ("saas:2", "saas:7"):
        said = page(client, person)
        given = client.post(
            "/api/roles/assign",
            json.dumps({"person": person, "role": str(cashier.pk)}),
            content_type="application/json",
            HTTP_HOST=HOST,
        )
        assert (given.status_code, given.json()["error"]["code"]) == (403, said["role_refusal"])
