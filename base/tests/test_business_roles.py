"""A business's own role (``BusinessRole``): made by duplicating a basic one, it keeps the state of every permission of
the apps it was saved with, and reads the apps of today against them.

An app none of whose permissions the role saved (turned on after it) gives what it gives the basic role the role was
duplicated from; a permission an app added after the role was saved is off. Both are left to review. A person holds at
most one, in ``HubUser.business_role``; none is the role of their invitation, and a role somebody holds is not deleted.
"""

import pytest
from django.db.models import ProtectedError

from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.roles import APPROVAL, OFF, ON, effective, raised, saved, to_review
from base.tenancy.tests.business import HUB_DB, in_business_a

__all__ = ["in_business_a"]

SALE = ("sale.view_sale", "sale.void_sale")
STOCK = ("inventory.view", "inventory.manage")
REVIEWED_SALE = {"sale.view_sale": ON, "sale.void_sale": APPROVAL}


class TestWhatItAllows:
    def test_an_app_it_was_saved_with_keeps_what_was_saved(self):
        allowed = effective(REVIEWED_SALE, {"sale": SALE}, given=set(SALE))

        assert allowed == {"sale.view_sale": ON, "sale.void_sale": APPROVAL}

    def test_an_app_turned_on_after_it_was_saved_gives_what_it_gives_the_basic_role_it_came_from(self):
        allowed = effective(
            REVIEWED_SALE, {"sale": SALE, "inventory": STOCK}, given={"inventory.view"}, approvable={"inventory.manage"}
        )

        assert (allowed["inventory.view"], allowed["inventory.manage"]) == (ON, APPROVAL)

    def test_an_app_turned_on_later_gives_nothing_its_origin_lacks(self):
        allowed = effective(REVIEWED_SALE, {"sale": SALE, "inventory": STOCK}, given=set())

        assert (allowed["inventory.view"], allowed["inventory.manage"]) == (OFF, OFF)

    def test_a_permission_an_app_added_after_it_was_saved_is_off_even_if_its_origin_has_it(self):
        allowed = effective({"sale.view_sale": ON}, {"sale": SALE}, given=set(SALE))

        assert allowed == {"sale.view_sale": ON, "sale.void_sale": OFF}

    def test_it_never_changes_with_its_origin_once_saved(self):
        allowed = effective({"sale.view_sale": OFF, "sale.void_sale": OFF}, {"sale": SALE}, given=set(SALE))

        assert allowed == {"sale.view_sale": OFF, "sale.void_sale": OFF}

    def test_it_reads_only_the_apps_it_is_given(self):
        allowed = effective({**REVIEWED_SALE, "inventory.view": ON}, {"sale": SALE}, given=set())

        assert set(allowed) == set(SALE)


class TestWhatSavingAChangeKeeps:
    APPS = {"sale": SALE, "inventory": STOCK}

    def change(self, states, **changes) -> dict:
        named = {permission.replace("__", "."): state for permission, state in changes.items()}
        return saved(states, self.APPS, {"inventory.view"}, {"inventory.manage"}, named)

    def test_only_what_the_change_names_of_an_app_it_was_saved_with(self):
        assert self.change(REVIEWED_SALE, sale__view_sale=OFF) == {"sale.view_sale": OFF, "sale.void_sale": APPROVAL}

    def test_an_app_it_was_not_saved_with_is_saved_whole_with_what_it_gave(self):
        kept = self.change(REVIEWED_SALE, inventory__view=OFF)

        assert kept == {**REVIEWED_SALE, "inventory.view": OFF, "inventory.manage": APPROVAL}

    def test_a_permission_an_app_added_after_it_was_saved_is_saved_alone(self):
        assert self.change({"sale.view_sale": ON}, sale__void_sale=ON) == {"sale.view_sale": ON, "sale.void_sale": ON}

    def test_what_it_was_saved_with_of_an_app_that_is_off_stays(self):
        assert self.change({"task.view": ON}, sale__view_sale=ON)["task.view"] == ON

    def test_what_it_was_saved_with_is_not_changed_in_place(self):
        states = dict(REVIEWED_SALE)

        self.change(states, sale__view_sale=OFF)

        assert states == REVIEWED_SALE


class TestWhatAChangeRaises:
    @pytest.mark.parametrize("before", [ON, APPROVAL, OFF, None])
    @pytest.mark.parametrize("after", [ON, APPROVAL, OFF])
    def test_is_what_does_more_than_it_did(self, before, after):
        more = {(None, APPROVAL), (None, ON), (OFF, APPROVAL), (OFF, ON), (APPROVAL, ON)}
        was = {} if before is None else {"sale.void_sale": before}

        assert raised(was, {"sale.void_sale": after}) == ({"sale.void_sale": after} if (before, after) in more else {})

    def test_is_nothing_of_what_stays_as_it_was_or_is_gone(self):
        assert raised({"sale.view_sale": ON, "sale.void_sale": APPROVAL}, {"sale.view_sale": ON}) == {}


class TestWhatIsLeftToReview:
    def test_nothing_when_it_was_saved_with_every_app(self):
        saved = {**REVIEWED_SALE, "inventory.view": OFF, "inventory.manage": OFF}

        assert to_review(saved, {"sale": SALE, "inventory": STOCK}) == set()

    def test_every_permission_of_an_app_turned_on_after_it_was_saved(self):
        assert to_review(REVIEWED_SALE, {"sale": SALE, "inventory": STOCK}) == set(STOCK)

    def test_a_permission_an_app_added_after_it_was_saved(self):
        assert to_review({"sale.view_sale": ON}, {"sale": SALE}) == {"sale.void_sale"}


@HUB_DB
class TestWhoHoldsIt:
    def test_a_person_holds_the_role_of_their_invitation_until_given_one_of_the_business(self):
        assert HubUser.objects.create(username="saas:3").business_role is None

    def test_a_role_is_kept_with_its_origin_and_what_it_allows(self):
        cashier = BusinessRole.objects.create(name="Cashier", origin=Membership.Role.EMPLOYEE, states=REVIEWED_SALE)
        HubUser.objects.create(username="saas:3", business_role=cashier)

        kept = HubUser.objects.get(username="saas:3").business_role
        assert (kept.name, kept.origin, kept.states, kept.description) == ("Cashier", "hub_employee", REVIEWED_SALE, "")

    def test_a_role_somebody_holds_is_not_deleted(self):
        cashier = BusinessRole.objects.create(name="Cashier", origin=Membership.Role.EMPLOYEE)
        HubUser.objects.create(username="saas:3", business_role=cashier)

        with pytest.raises(ProtectedError):
            cashier.delete()

    def test_a_role_nobody_holds_is_deleted(self):
        BusinessRole.objects.create(name="Cashier", origin=Membership.Role.EMPLOYEE).delete()

        assert not BusinessRole.objects.exists()
