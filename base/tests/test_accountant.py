"""The Accountant (``hub_accountant``, «Gestoría» in Spanish): the basic role of the business's accountancy firm.

erplora.com invites it like any other role and the Hub takes it at the login and in the photo. It reads, prints and
downloads the invoices issued, the taxes, VeriFactu's records and everyone's sales with the business's totals; it does
not sell, charge nor change any setting; and it takes no place of the plan (BASE-F77, BASE-F81, BASE-F82).
"""

import pytest
from live.operations import registry

from base.models import Hub, Membership
from base.permissions import VIEW_HOME, permissions_of_role
from base.tenancy.tests.business import A, HUB_DB, in_business_a
from base.tests.test_hub_state_members import member, role_of
from base.tests.test_hub_state_members import photo as photo_put
from base.tests.test_internal import PATH, signed
from base.tests.test_people import get, people, photo, row
from base.tests.test_session_revoke import acme, login

__all__ = ["acme", "in_business_a"]

pytestmark = HUB_DB

ACCOUNTANT = Membership.Role.ACCOUNTANT

#: Everything the role holds: reading the sales of everyone with the business's totals, the invoices, the taxes and
#: VeriFactu, besides the Home every person of the business has.
GRANTS = {
    "base.view_home",
    "base.view_business_totals",
    "sale.view_sale",
    "sale.view_all_sales",
    "sale.view_paymentmethod",
    "invoice.view_invoice",
    "tax.view",
    "verifactu.view_record",
}

#: The only commands its permissions reach beyond what every person does for themselves (``base.view_home``: their
#: profile, their PIN, the assistant): printing a document and checking VeriFactu's chain, which write nothing of the
#: business.
READING_COMMANDS = {"invoice.invoice.print", "sale.order.print_bill", "sale.sale.print", "verifactu.chain.validate"}

GEMA = "0199c4b0-0000-7000-8000-00000000c0c0"


@pytest.fixture
def olga(make_user):
    return make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga", email="olga@example.com")


@pytest.fixture
def eva(make_user):
    return make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva", email="eva@example.com")


@pytest.fixture
def mario(make_user):
    return make_user("saas:4", host=A.key, role=Membership.Role.MANAGER, first_name="Mario", email="mario@example.com")


@pytest.fixture
def gema(make_user):
    return make_user("saas:5", host=A.key, role=ACCOUNTANT, first_name="Gema", email="gema@example.com")


def test_the_role_is_hub_accountant_the_last_of_erplora_com_s():
    assert (ACCOUNTANT.value, str(ACCOUNTANT.label)) == ("hub_accountant", "Accountant")
    assert Membership.Role.values[-1] == ACCOUNTANT


def test_it_holds_only_reading_the_sales_the_invoices_the_taxes_and_verifactu():
    assert permissions_of_role(ACCOUNTANT) == GRANTS


def test_it_sells_charges_and_changes_no_setting():
    """No command its permissions reach writes in the business: no sale, no charge, no setting, no approval of
    someone else's action (an approver must hold the approved operation's permission)."""
    reached = {
        name
        for name, op in registry.items()
        if op.kind != "query" and op.permission != VIEW_HOME and op.permission in permissions_of_role(ACCOUNTANT)
    }
    assert reached == READING_COMMANDS


class TestTheSaaSSendsIt:
    def test_a_photo_with_an_accountant_gives_it_that_role(self, client, acme):
        login(GEMA, acme, "hub_employee")

        answer = signed(client, "put", PATH, photo_put(1, member(GEMA, "hub_accountant")))

        assert answer.json() == {"applied": True, "version": 1}
        assert role_of(GEMA) == "hub_accountant"


class TestItTakesNoPlaceOfThePlan:
    def test_employees_lists_the_accountant_last_and_does_not_count_it_among_the_places(
        self, client, olga, mario, eva, gema
    ):
        photo(
            members=[
                {"user_id": "1", "role": "hub_owner", "email": "olga@example.com", "name": "Olga"},
                {"user_id": GEMA, "role": "hub_accountant", "email": "asesoria@example.com", "name": "Asesoría"},
            ],
            max_users=3,
        )
        client.force_login(olga)

        answer = people(client)

        assert [entry["id"] for entry in answer["people"]] == ["saas:1", "saas:4", "saas:3", f"saas:{GEMA}", "saas:5"]
        assert {row(answer, person)["role"] for person in ("saas:5", f"saas:{GEMA}")} == {"hub_accountant"}
        assert answer["seats"] == {"known": True, "used": 3, "limit": 3, "full": True}

    def test_usage_and_plan_does_not_count_it_among_the_people(self, client, olga, eva, gema):
        Hub.objects.filter(slug=A.key).update(state={"plan": {"max_users": 3, "max_devices": 0}})
        client.force_login(olga)

        response = get(client, "/system/plan")

        assert response.status_code == 200, response.content
        assert response.json()["people"] == {"used": 2, "limit": 3}


def test_the_roles_of_the_business_are_five_with_the_accountant_last(client, olga, gema):
    client.force_login(olga)

    response = get(client, "/roles")

    assert response.status_code == 200, response.content
    accountant = response.json()["roles"][-1]
    assert [role["key"] for role in response.json()["roles"]] == Membership.Role.values
    assert (accountant["label"], accountant["members"], accountant["permissions"]) == ("Accountant", 1, len(GRANTS))
