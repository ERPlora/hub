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
from base.api_keys import KeyCaller
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


@pytest.fixture
def items():
    return {name: Item.objects.create(name=name).pk for name in ("ana", "bea")}


class TestOwned:
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


def key_of(maker: str) -> KeyCaller:
    """An API key made by the person known as ``maker`` (``""``: made before its maker was recorded)."""
    return KeyCaller(key_id="k1", name="Shop", prefix="erpk_live_ab", owner=maker)


class TestAnApiKey:
    """A key reads what has an owner as whoever made it (BASE-F125); at the counter it stays on the customer's side, so
    it is still no person to ``me``."""

    def test_without_the_all_permission_it_reads_only_its_makers(self, items):
        assert set(ITEMS.visible(ctx_of(key_of("ana"))).values_list("pk", flat=True)) == {items["ana"]}

    def test_with_it_it_reads_everyones(self, items):
        assert ITEMS.visible(ctx_of(key_of("ana"), "demo.view_all_items")).count() == 2

    def test_its_figures_are_its_makers_without_the_business_totals(self, items):
        rows = ITEMS.counted(ctx_of(key_of("ana"), "demo.view_all_items"))
        assert set(rows.values_list("name", flat=True)) == {"ana"}

    def test_its_makers_staff_record_is_its_makers(self):
        record = staff_record(person("ana"))
        theirs = Item.objects.create(name=str(record.id))
        Item.objects.create(name="someone else's")
        by_record = Owned(Item, all_permission="demo.view_all_items", mine=lambda who: Q(name__in=map(str, who.records)))
        assert list(by_record.visible(ctx_of(key_of("ana"))).values_list("pk", flat=True)) == [theirs.pk]

    def test_one_made_before_its_maker_was_recorded_reaches_what_its_permission_opens(self, items):
        assert ITEMS.visible(ctx_of(key_of(""))).count() == 2

    def test_it_is_no_person_at_the_counter(self):
        assert me(ctx_of(key_of("ana"))) is None


def test_the_see_all_permissions_are_the_ones_the_declarations_name():
    assert {
        "sale.view_all_sales",
        "cash_register.view_all_sessions",
        "invoice.view_all_invoices",
        "appointment.view_appointment",
        "staff.view_compensation",
        "demo.view_all_items",
    } <= ownership.see_all_permissions()


class TestCounted:
    """The rows a caller's figures add up: a period's totals, a day's takings, the close by person."""

    @pytest.mark.parametrize(
        ("permissions", "counted"),
        [
            ((), {"ana"}),
            (("demo.view_all_items",), {"ana"}),
            (("base.view_business_totals",), {"ana"}),
            (("demo.view_all_items", "base.view_business_totals"), {"ana", "bea"}),
        ],
        ids=["neither", "everyones rows without the business totals", "the business totals of only theirs", "both"],
    )
    def test_a_person_counts_the_whole_business_only_with_both_permissions(self, items, permissions, counted):
        rows = ITEMS.counted(ctx_of(person("ana"), *permissions))
        assert set(rows.values_list("name", flat=True)) == counted

    def test_a_caller_that_is_not_a_person_counts_what_its_permission_opens(self, items):
        assert ITEMS.counted(ctx_of("flow:7")).count() == 2
