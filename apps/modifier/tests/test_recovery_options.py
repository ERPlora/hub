"""An option taken away from a group the business keeps comes back from a separate copy (hub#1505; BASE-F114,
MODIFIER-F10).

Between the groups and their links, Modifiers reads every option of the copy and adds again, by
``modifier.option.recover``, each one a group the business still has no longer holds: the same group, or the one a
recovery brought back with its name. One the business made again with its name stays as it is. One chosen by default
comes back chosen only where its group has room for it: the business's own defaults are never taken away, and the
recovery notes why it came back without.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connections
from django.utils import translation
from live.models import OutboxEvent
from live.operations import get as get_operation

from apps.modifier import queries
from apps.modifier.models import ModifierGroup, ModifierOption
from apps.modifier.services import DEFAULT_KEPT
from apps.tax.models import TaxCategory
from base.recovery import actor_of, giving_back
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.test_recovery import fields_held_since, fresh, run, run_in

from . import test_recovery as whole
from .conftest import GENERIC, HUB_DB, ctx_for, ctx_with
from .conftest import run as run_here
from .test_recovery import recoveries  # noqa: F401 - the fixture of the two databases

OPTIONS = whole.GROUPS | {"label": "Modifier options"}


def an_option(group, name: str, **fields) -> ModifierOption:
    return ModifierOption.objects.get(
        pk=run_here("modifier.option.create", {"group_id": str(group.id), "name": name, "price_delta": 0, **fields}).id
    )


def of_the_copy(group_id, name: str, **fields) -> dict:
    """An option as ``options_in_copy`` gives it, of the copy's group ``group_id``, whose groups are the business's."""
    return {
        "id": uuid.uuid7(), "group_id": group_id, "name": name, "kitchen_name": "", "price_delta": 0,
        "is_default": False, "sort_order": 0, "tax_category_id": None, "copy_groups": whole.groups_now(), **fields,
    }


def as_recovered(option: dict, group_id, **fields) -> dict:
    """What ``options_not_in_business`` gives of ``option`` of the copy: as its recover takes it, in ``group_id``."""
    taken = ("id", "name", "kitchen_name", "price_delta", "is_default", "sort_order")
    return {key: option[key] for key in taken} | {"group_id": group_id, "tax_category_key": "", **fields}


@HUB_DB
def test_the_copy_gives_each_option_with_its_group_and_what_its_create_takes():
    sauces, extras = whole.a_group("Sauces"), whole.a_group("Extras")
    ketchup = an_option(sauces, "Ketchup", is_default=True)
    cheese = an_option(extras, "Cheese", kitchen_name="+CH", price_delta=100, tax_category_key=GENERIC, sort_order=2)
    bbq = an_option(sauces, "BBQ", sort_order=1)
    generic = TaxCategory.objects.get(key=GENERIC).pk

    read = queries.recovery.options_in_copy(whole.direct())

    # By id, the order they were added in, with every group of the copy by name to pair a group the business deleted.
    named = {sauces.id: "Sauces", extras.id: "Extras"}
    assert read == [
        {"id": ketchup.id, "group_id": sauces.id, "name": "Ketchup", "kitchen_name": "", "price_delta": 0,
         "is_default": True, "sort_order": 0, "allergens": [], "tax_category_id": None, "copy_groups": named},
        {"id": cheese.id, "group_id": extras.id, "name": "Cheese", "kitchen_name": "+CH", "price_delta": 100,
         "is_default": False, "sort_order": 2, "allergens": [], "tax_category_id": generic, "copy_groups": named},
        {"id": bbq.id, "group_id": sauces.id, "name": "BBQ", "kitchen_name": "", "price_delta": 0,
         "is_default": False, "sort_order": 1, "allergens": [], "tax_category_id": None, "copy_groups": named},
    ]


@HUB_DB
def test_a_copy_whose_options_table_is_there_without_any_option_reads_no_group():
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction: with no option to pair, the groups by name are never read.
        cursor.execute("DROP TABLE modifier_modifiergroup CASCADE")

    assert queries.recovery.options_in_copy(whole.direct()) == []


@HUB_DB
def test_lacking_is_an_option_a_group_the_business_keeps_no_longer_has():
    generic = TaxCategory.objects.get(key=GENERIC).pk
    sauces = whole.a_group("Sauces")
    # Renamed since, it is the same group all the same.
    run_here("modifier.group.update", {"id": str(sauces.id), "name": "Dips"})
    renamed = an_option(sauces, "Ketchup")
    run_here("modifier.option.update", {"id": str(renamed.id), "name": "Tomato"})
    still = of_the_copy(sauces.id, "Ketchup") | {"id": renamed.id}
    # Made again by the business with its name, the case aside: its own stays, never a second one.
    an_option(sauces, "ALIOLI")
    made_again = of_the_copy(sauces.id, "Alioli")
    taken = of_the_copy(
        sauces.id, "Truffle", kitchen_name="+TRF", price_delta=300, is_default=True, sort_order=4,
        tax_category_id=generic,
    )

    lacking = queries.recovery.options_not_in_business([still, made_again, taken])

    assert lacking == [as_recovered(taken, sauces.id, tax_category_key=GENERIC)]


@HUB_DB
def test_an_option_another_group_has_by_its_name_is_lacking_all_the_same():
    sauces, extras = whole.a_group("Sauces"), whole.a_group("Extras")
    # A name is taken in its own group only.
    an_option(extras, "Alioli")
    taken, other = of_the_copy(sauces.id, "Alioli"), of_the_copy(extras.id, "Cheese")

    lacking = queries.recovery.options_not_in_business([taken, other])

    assert lacking == [as_recovered(taken, sauces.id), as_recovered(other, extras.id)]


@HUB_DB
def test_an_option_of_a_group_gone_goes_to_the_one_a_recovery_brought_back_with_its_name():
    back = whole.a_group_brought_back("SAUCES")
    an_option(back, "Ketchup")
    # Made again by hand with its name: its own, which takes nothing; its option keeps the copy's group, which the
    # create then refuses as not found.
    whole.a_group("Extras")
    lost, gone = uuid.uuid7(), uuid.uuid7()
    copy = {lost: "Sauces", gone: "Extras"}
    kept = of_the_copy(lost, "Ketchup", copy_groups=copy)
    taken = of_the_copy(lost, "Mayo", copy_groups=copy)
    by_hand = of_the_copy(gone, "Cheese", copy_groups=copy)

    lacking = queries.recovery.options_not_in_business([kept, taken, by_hand])

    assert lacking == [as_recovered(taken, back.id), as_recovered(by_hand, gone)]


@HUB_DB
def test_the_options_of_a_group_this_same_recovery_brought_back_came_back_with_it():
    now, earlier = actor_of(uuid.uuid7()), actor_of(uuid.uuid7())
    with_it = ModifierGroup.objects.create(name="Sauces", created_by=now)
    before = ModifierGroup.objects.create(name="Extras", created_by=earlier)
    copy = {uuid.uuid7(): "Sauces", uuid.uuid7(): "Extras"}
    [sauces, extras] = copy
    # Its recover gave back its options, and said what it came back without: none is asked twice.
    left_out = of_the_copy(sauces, "Wine sauce", copy_groups=copy)
    taken = of_the_copy(extras, "Cheese", copy_groups=copy)

    with giving_back(now):
        lacking = queries.recovery.options_not_in_business([left_out, taken])

    assert lacking == [as_recovered(taken, before.id)]
    assert queries.recovery.options_not_in_business([left_out]) == [as_recovered(left_out, with_it.id)]


@HUB_DB
def test_with_nothing_read_no_option_is_lacking():
    assert queries.recovery.options_not_in_business([]) == []


def recovered(record: dict, actor: str = "system"):
    """``record`` of ``options_not_in_business`` added again as the platform does: all of it but its id in the copy."""
    return run_here(
        "modifier.option.recover", {key: value for key, value in record.items() if key != "id"},
        ctx=ctx_with("*", actor=actor),
    )


@HUB_DB
def test_an_option_comes_back_by_the_option_sheets_own_create():
    actor = actor_of(uuid.uuid7())
    sauces = whole.a_group("Sauces")
    [record] = queries.recovery.options_not_in_business([
        of_the_copy(sauces.id, "Truffle", kitchen_name="+TRF", price_delta=300, sort_order=3,
                    tax_category_id=TaxCategory.objects.get(key=GENERIC).pk)
    ])

    made = recovered(record, actor)

    assert made.left_out == []
    option = ModifierOption.objects.get(pk=made.id)
    assert (option.group_id, option.name, option.kitchen_name, option.price_delta, option.tax_category.key,
            option.is_default, option.sort_order, option.created_by) == (
        sauces.id, "Truffle", "+TRF", 300, GENERIC, False, 3, actor
    )
    assert list(OutboxEvent.objects.filter(actor=actor).values_list("name", flat=True)) == ["modifier.option.created"]


def alioli_back_to(most: int, chosen: list[str], **fields) -> tuple:
    """A group «Sauces» that takes at most ``most`` options, with ``chosen`` chosen by default, and the copy's «Alioli»
    it no longer has, as its recover takes it: the group and the record."""
    sauces = run_here("modifier.group.create", {"name": "Sauces", "max_choices": most})
    for name in chosen:
        an_option(sauces, name, is_default=True)
    [record] = queries.recovery.options_not_in_business([of_the_copy(sauces.id, "Alioli", **fields)])
    return sauces, record


@HUB_DB
@pytest.mark.parametrize(("most", "chosen"), [(1, []), (0, ["Ketchup"]), (2, ["Ketchup"])])
def test_one_chosen_by_default_comes_back_chosen_where_its_group_has_room(most, chosen):
    _sauces, record = alioli_back_to(most, chosen, is_default=True)

    made = recovered(record)

    assert (made.is_default, made.left_out) == (True, [])


@HUB_DB
@pytest.mark.parametrize(("most", "chosen"), [(1, ["Ketchup"]), (2, ["BBQ", "Ketchup"])])
def test_one_chosen_by_default_never_takes_it_from_the_ones_the_business_chose(most, chosen):
    actor = actor_of(uuid.uuid7())
    sauces, record = alioli_back_to(most, chosen, is_default=True)

    with translation.override("es"):
        made = recovered(record, actor)
        spanish = DEFAULT_KEPT % {"chosen": ", ".join(chosen)}

    # It comes back, not chosen; the business's stay chosen, unchanged, and the recovery says why.
    assert made.is_default is False
    chosen_now = ModifierOption.objects.filter(group_id=sauces.id, is_default=True).values_list("name", flat=True)
    assert sorted(chosen_now) == chosen
    assert list(OutboxEvent.objects.filter(actor=actor).values_list("name", flat=True)) == ["modifier.option.created"]
    [said] = made.left_out
    assert (said.code, said.message) == ("modifier.default_kept", spanish)
    assert spanish != DEFAULT_KEPT % {"chosen": ", ".join(chosen)}


@HUB_DB
def test_one_not_chosen_by_default_comes_back_as_it_was_whatever_its_group_holds():
    _sauces, record = alioli_back_to(1, ["Ketchup"])

    made = recovered(record)

    assert (made.is_default, made.left_out) == (False, [])


@HUB_DB
def test_bringing_an_option_back_is_only_the_systems():
    op = get_operation("modifier.option.recover")

    assert op.permission == "modifier.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_the_app_declares_the_options_of_its_groups_after_the_groups_and_before_their_links():
    labels = [str(one.label) for one in apps.get_app_config("modifier").recoverable_from_copy()]
    _groups, options, _categories, _links = apps.get_app_config("modifier").recoverable_from_copy()

    assert labels == [
        "Modifier groups", "Modifier options", "Modifier groups of categories", "Modifier groups of products"
    ]
    assert (options.read, options.missing, options.create, options.deleted, options.restore) == (
        queries.recovery.options_in_copy,
        queries.recovery.options_not_in_business,
        "modifier.option.recover",
        None,
        "",
    )
    assert options.reads_since == "0001_initial"
    # A copy that far back holds what the read takes: each column of an option, and its group's name.
    assert {"id", "group", "tax_category", *queries.recovery.OPTION_COPY_FIELDS} <= fields_held_since(
        "modifier", "modifieroption", options.reads_since
    )
    assert {"id", "name"} <= fields_held_since("modifier", "modifiergroup", options.reads_since)


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


def options_of(hub, group) -> list[tuple]:
    with use_hub(hub):
        return list(
            ModifierOption.objects.filter(group_id=group)
            .order_by("sort_order", "name")
            .values_list("name", "kitchen_name", "price_delta", "tax_category__key", "is_default", "sort_order")
        )


class TestOptionsComeBack:
    def a_business(self, recoveries, every_app_on, *, most: int = 0):  # noqa: F811 - the fixture
        """A business whose group «Sauces» offers «Ketchup» and «Alioli», the second chosen by default with a
        supplement and a tax category of its own: the hub, the group's id and the options' ids."""
        hub, _ = recoveries.business(every_app_on)
        sauces = run_in(hub, "modifier.group.create", name="Sauces", max_choices=most).id
        with use_hub(hub):
            own = TaxCategory.objects.filter(is_active=True).order_by("key").first().key
        ketchup = run_in(hub, "modifier.option.create", price_delta=0, group_id=sauces, name="Ketchup").id
        alioli = run_in(hub, "modifier.option.create", group_id=sauces, name="Alioli", kitchen_name="+ALI",
                        price_delta=50, tax_category_key=own, is_default=True, sort_order=1).id
        self.own = own
        return hub, sauces, {"Ketchup": ketchup, "Alioli": alioli}

    def test_an_option_taken_from_a_group_the_business_keeps_comes_back(self, recoveries, every_app_on):  # noqa: F811
        hub, sauces, options = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        run_in(hub, "modifier.option.delete", id=options["Alioli"])
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        assert whole.said(row) == (
            "done", [whole.MODIFIER_GROUPS, OPTIONS | {"created": 1}, whole.CATEGORY_GROUPS, whole.GROUPS]
        )
        assert options_of(hub, sauces) == [
            ("Ketchup", "", 0, None, False, 0), ("Alioli", "+ALI", 50, self.own, True, 1)
        ]
        with use_hub(hub):
            assert ModifierOption.objects.get(name="Alioli").created_by == actor_of(row.pk)
        # Asked again: it is in its place, never added twice.
        again = recoveries.ask(copy, "modifier")
        assert run() == 1
        assert whole.said(again) == ("done", [whole.MODIFIER_GROUPS, OPTIONS, whole.CATEGORY_GROUPS, whole.GROUPS])
        assert len(options_of(hub, sauces)) == 2

    def test_an_option_the_business_made_again_stays_as_it_is(self, recoveries, every_app_on):  # noqa: F811
        hub, sauces, options = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        run_in(hub, "modifier.option.delete", id=options["Alioli"])
        run_in(hub, "modifier.option.create", group_id=sauces, name="ALIOLI", price_delta=80)
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        assert whole.said(row)[1][1] == OPTIONS
        assert options_of(hub, sauces) == [("ALIOLI", "", 80, None, False, 0), ("Ketchup", "", 0, None, False, 0)]

    def test_one_chosen_by_default_comes_back_without_taking_it_from_the_business(self, recoveries, every_app_on):  # noqa: F811
        hub, sauces, options = self.a_business(recoveries, every_app_on, most=1)
        copy = recoveries.copy_of(hub)
        run_in(hub, "modifier.option.delete", id=options["Alioli"])
        # The business chose another one by default since.
        run_in(hub, "modifier.option.update", id=options["Ketchup"], is_default=True)
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        [_groups, result, _categories, _links] = fresh(row).results
        assert (result["created"], result["noted"]) == (1, 1)
        [note] = result["notes"]
        assert (note["id"], note["note"].split(":")[0]) == (str(options["Alioli"]), "modifier.default_kept")
        assert "Ketchup" in note["note"]
        assert options_of(hub, sauces) == [
            ("Ketchup", "", 0, None, True, 0), ("Alioli", "+ALI", 50, self.own, False, 1)
        ]
