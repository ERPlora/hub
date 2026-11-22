"""Whose a record is: who the caller is to the apps that keep what people did (``me``), and the reads of a model whose
rows belong to someone (``Owned``), which give a person only theirs unless they may see everyone's, as the market's
«view own / view all» (Square, Toast, Odoo).

A person is the user of a session; their records are what the apps that keep people answer for them (Staff: their live
staff record). A caller that is not a person (an API key, an automation, the platform) has nothing of its own: it
reaches what its permission opens.
"""

import dataclasses

import pytest
from django.contrib.auth import get_user_model
from django.db.models import Q
from live.context import OperationContext, system_context
from live.operations import get as get_operation

from apps.demo.models import Item
from base.models import Membership
from base.queries import ownership
from base.queries.ownership import Me, Owned, me
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import A, HUB_DB, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB

#: The items «of» a person in these tests: those named as their user.
ITEMS = Owned(Item, all_permission="demo.view_all_items", mine=lambda person: Q(name=person.username))


def person(username: str, role: str = Membership.Role.EMPLOYEE):
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host=A.key, role=role)
    user.person = ensure_hub_user(user)
    return user


def ctx_of(actor, *permissions: str) -> OperationContext:
    return OperationContext(scope=A, actor=actor, permissions=frozenset(permissions))


def staff_record(user, first_name: str = "Ana"):
    """A live staff record linked to ``user``, made by Staff."""
    create = get_operation("staff.member.create")
    data = {"first_name": first_name, "last_name": "Ruiz", "user_id": str(user.person.pk)}
    return create(system_context(A), create.input.model_validate(data))


class TestMe:
    def test_a_person_is_their_username_with_no_records_without_a_staff_record(self):
        ana = person("ana")
        assert me(ctx_of(ana)) == Me(username="ana", records=frozenset())

    def test_their_staff_record_is_theirs_as_staff_answers_it(self):
        ana = person("ana")
        record = staff_record(ana)
        assert me(ctx_of(ana)) == Me(username="ana", records=frozenset({record.id}))

    def test_with_staff_off_they_have_no_records(self, monkeypatch):
        ana = person("ana")
        staff_record(ana)
        on = ownership.active_apps(A)
        monkeypatch.setattr(ownership, "active_apps", lambda scope: on - {"staff"})
        assert me(ctx_of(ana)) == Me(username="ana", records=frozenset())

    @pytest.mark.parametrize("actor", [None, "flow:7", object()], ids=["nobody", "a label", "an api key"])
    def test_a_caller_that_is_not_a_person_is_nobody(self, actor):
        assert me(ctx_of(actor)) is None


class TestOwned:
    @pytest.fixture
    def items(self):
        return {name: Item.objects.create(name=name).pk for name in ("ana", "bea")}

    def test_a_person_without_the_all_permission_reads_only_theirs(self, items):
        assert set(ITEMS.visible(ctx_of(person("ana"))).values_list("pk", flat=True)) == {items["ana"]}

    def test_with_it_they_read_everyones(self, items):
        visible = ITEMS.visible(ctx_of(person("ana"), "demo.view_all_items"))
        assert set(visible.values_list("pk", flat=True)) == set(items.values())

    def test_a_whole_app_granted_with_a_star_reads_everyones(self, items):
        assert ITEMS.visible(ctx_of(person("ana"), "demo.*")).count() == 2

    def test_a_caller_that_is_not_a_person_reaches_what_its_permission_opens(self, items):
        assert ITEMS.visible(ctx_of("flow:7")).count() == 2

    def test_a_person_with_nothing_of_their_own_reads_nothing(self, items):
        assert ITEMS.visible(ctx_of(person("carla"))).count() == 0

    def test_theirs_are_a_persons_rows_whatever_the_caller_holds(self, items):
        # What another model whose rows follow these reads them by: an invoice is whoever's its sale is.
        theirs = ITEMS.theirs(Me(username="bea", records=frozenset()))
        assert set(theirs.values_list("pk", flat=True)) == {items["bea"]}

    def test_sees_all_says_which_of_the_two(self):
        ana = person("ana")
        assert (ITEMS.sees_all(ctx_of(ana)), ITEMS.sees_all(ctx_of(ana, "demo.view_all_items"))) == (False, True)
        assert ITEMS.sees_all(dataclasses.replace(ctx_of(ana), actor=None)) is True
