"""Write operations of the modifier app: groups, options and links (MODIFIER-F02 to F05), each one a
transaction with its events in the outbox. Inventory and Taxes are the real apps (no doubles)."""

import json
import uuid

import psycopg
import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.modifier.models import (
    MAX_OPTIONS,
    ModifierGroup,
    ModifierLink,
    ModifierOption,
)

from .conftest import A, B, FOOD, GENERIC, ctx_for, make_category, make_product, run

pytestmark = pytest.mark.django_db


def events(name: str) -> list[dict]:
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")
    ]


def refusal(error) -> tuple:
    return (type(error.value).__name__, error.value.code, error.value.fields)


def group(name="Sauces", **fields):
    return run("modifier.group.create", {"name": name, **fields})


def option(group_name="Sauces", name="Ketchup", **fields):
    return run("modifier.option.create", {"group": group_name, "name": name, **fields})


# Groups (MODIFIER-F02, F03)


def test_creating_a_group_keeps_what_was_typed_and_says_so():
    created = group(
        "Doneness", kitchen_name="POINT", min_choices=1, max_choices=1, sort_order=10
    )
    assert (
        created.name,
        created.kitchen_name,
        created.min_choices,
        created.max_choices,
    ) == ("Doneness", "POINT", 1, 1)
    assert (created.is_required, created.allow_repeat, created.sort_order) == (
        True,
        False,
        10,
    )
    assert (created.option_count, created.default_count, created.link_count) == (
        0,
        0,
        0,
    )
    row = ModifierGroup.objects.get(pk=created.id)
    assert (row.created_by, row.updated_by) == ("tester", "tester")
    assert events("modifier.group.created") == [
        {"id": str(created.id), "name": "Doneness"}
    ]


def test_a_group_name_taken_whatever_the_case_is_a_409_on_the_name():
    group("Sauces")
    with pytest.raises(Conflict) as error:
        group("  sauces ")
    assert refusal(error) == (
        "Conflict",
        "modifier.group_name_taken",
        {"name": "There is already a group with that name."},
    )
    assert ModifierGroup.objects.count() == 1


def test_an_employee_reads_but_never_writes():
    with pytest.raises(PermissionDenied):
        run("modifier.group.create", {"name": "Sauces"}, role="hub_employee")
    group("Sauces")
    with pytest.raises(PermissionDenied):
        run(
            "modifier.option.create",
            {"group": "Sauces", "name": "Mayo"},
            role="hub_employee",
        )


def test_changing_a_group_keeps_what_is_not_sent():
    created = group(
        "Sauces",
        kitchen_name="SAUCE",
        min_choices=1,
        max_choices=3,
        allow_repeat=True,
        sort_order=5,
    )
    changed = run(
        "modifier.group.update",
        {"group": "sauces", "max_choices": 2},
        role="hub_manager",
    )
    assert (
        changed.name,
        changed.kitchen_name,
        changed.min_choices,
        changed.max_choices,
    ) == ("Sauces", "SAUCE", 1, 2)
    assert (changed.allow_repeat, changed.sort_order) == (True, 5)
    assert events("modifier.group.updated") == [
        {"id": str(created.id), "name": "Sauces"}
    ]
    # Nothing changes, nothing is said.
    run("modifier.group.update", {"id": str(created.id), "name": "Sauces"})
    assert len(events("modifier.group.updated")) == 1


def test_a_change_that_leaves_the_maximum_below_the_minimum_is_a_422_on_the_field_that_broke_it():
    group("Sauces", min_choices=1, max_choices=2)
    with pytest.raises(InvalidPayload) as error:
        run("modifier.group.update", {"group": "Sauces", "min_choices": 3})
    assert error.value.fields == {
        "min_choices": "The maximum cannot be below the minimum (0 = no ceiling)."
    }
    group("Extras", min_choices=2, max_choices=3)
    with pytest.raises(InvalidPayload) as error:
        run("modifier.group.update", {"group": "Extras", "max_choices": 1})
    assert error.value.fields == {
        "max_choices": "The maximum cannot be below the minimum (0 = no ceiling)."
    }
    # 0 is no ceiling: that one is fine.
    assert (
        run(
            "modifier.group.update",
            {"group": "Sauces", "max_choices": 0, "min_choices": 5},
        ).min_choices
        == 5
    )


def test_renaming_a_group_to_a_taken_name_is_a_409():
    group("Sauces")
    group("Extras")
    with pytest.raises(Conflict) as error:
        run("modifier.group.update", {"group": "Extras", "name": "SAUCES"})
    assert error.value.code == "modifier.group_name_taken"


def test_a_group_that_does_not_exist_is_a_404():
    for name, data in (
        ("modifier.group.update", {"id": str(uuid.uuid7()), "name": "X"}),
        ("modifier.group.delete", {"group": "Nowhere"}),
    ):
        with pytest.raises(NotFound) as error:
            run(name, data)
        assert error.value.message == "This group does not exist."
    assert events("modifier.group.updated") == events("modifier.group.deleted") == []


def test_deleting_a_group_takes_its_options_and_links_in_one_step():
    created = group("Sauces")
    option(name="Ketchup")
    run(
        "modifier.link.attach",
        {"group": "Sauces", "product_id": str(make_product().id)},
    )
    deleted = run("modifier.group.delete", {"group": "Sauces"})
    assert deleted.id == created.id
    assert (
        ModifierGroup.objects.count(),
        ModifierOption.objects.count(),
        ModifierLink.objects.count(),
    ) == (0, 0, 0)
    assert events("modifier.group.deleted") == [
        {"id": str(created.id), "name": "Sauces"}
    ]


# Options (MODIFIER-F04)


def test_adding_an_option_with_its_supplement():
    sauces = group("Sauces")
    cheese = option(
        name="Cheese", kitchen_name="+CHEESE", price_delta=100, sort_order=2
    )
    assert (cheese.group_id, cheese.group_name, cheese.name, cheese.kitchen_name) == (
        sauces.id,
        "Sauces",
        "Cheese",
        "+CHEESE",
    )
    assert (
        cheese.price_delta,
        cheese.tax_category_key,
        cheese.is_default,
        cheese.sort_order,
    ) == (100, None, False, 2)
    assert events("modifier.option.created") == [
        {
            "id": str(cheese.id),
            "group_id": str(sauces.id),
            "name": "Cheese",
            "price_delta": 100,
        }
    ]
    # A discount and a free one.
    assert option(name="No bread", price_delta=-50).price_delta == -50
    assert option(name="No onion").price_delta == 0


def test_an_option_name_is_unique_in_its_group():
    group("Sauces")
    group("Extras")
    option("Sauces", "Cheese")
    option("Extras", "Cheese")
    with pytest.raises(Conflict) as error:
        option("Sauces", "CHEESE")
    assert refusal(error) == (
        "Conflict",
        "modifier.option_name_taken",
        {"name": "This group already has an option with that name."},
    )


def test_an_option_of_a_group_that_does_not_exist_is_a_404():
    with pytest.raises(NotFound):
        option("Nowhere", "Cheese")


def test_an_own_tax_category_by_its_key_or_its_name_and_never_an_unknown_one():
    group("Drinks")
    soda = option("Drinks", "Soda", price_delta=250, tax_category_key=GENERIC)
    assert (soda.tax_category_key, soda.tax_category_name) == (
        GENERIC,
        "Product — generic",
    )
    water = option(
        "Drinks", "Water", price_delta=150, tax_category_key="Product — generic"
    )
    assert water.tax_category_key == GENERIC
    with pytest.raises(InvalidPayload) as error:
        option("Drinks", "Juice", price_delta=200, tax_category_key="nowhere.tax")
    assert error.value.fields == {
        "tax_category_key": "This tax category does not exist in Taxes."
    }


def test_an_option_with_its_own_tax_category_must_be_worth_more_than_zero():
    group("Drinks")
    message = "An option with its own tax category is billed on a line of its own: its supplement must be more than zero."
    for delta in (0, -100):
        with pytest.raises(InvalidPayload) as error:
            option(
                "Drinks", f"Soda {delta}", price_delta=delta, tax_category_key=GENERIC
            )
        assert error.value.fields == {"price_delta": message}
    soda = option("Drinks", "Soda", price_delta=250, tax_category_key=GENERIC)
    with pytest.raises(InvalidPayload) as error:
        run("modifier.option.update", {"id": str(soda.id), "price_delta": 0})
    assert error.value.fields == {"price_delta": message}
    # Back to the dish's category, it may be free again.
    assert (
        run(
            "modifier.option.update",
            {"id": str(soda.id), "price_delta": 0, "tax_category_key": ""},
        ).tax_category_key
        is None
    )


def test_a_save_the_database_refuses_for_an_own_line_worth_nothing_is_a_422_on_the_supplement():
    # Two saves at once may pass the check before writing; the database's constraint says the same.
    from apps.modifier.services import _save
    from apps.tax.models import TaxCategory

    group("Drinks")
    soda = ModifierOption(group=ModifierGroup.objects.get(name="Drinks"), name="Soda", price_delta=0, tax_category=TaxCategory.objects.get(key=GENERIC))
    with pytest.raises(InvalidPayload) as error:
        _save(soda)
    assert error.value.fields == {
        "price_delta": "An option with its own tax category is billed on a line of its own: its supplement must be more than zero."
    }


def test_in_a_group_of_one_a_new_default_takes_the_place_of_the_old_one():
    group("Doneness", min_choices=1, max_choices=1)
    rare = option("Doneness", "Rare", is_default=True)
    medium = option("Doneness", "Medium", is_default=True)
    assert medium.is_default is True
    assert ModifierOption.objects.get(pk=rare.id).is_default is False
    assert events("modifier.option.updated") == [
        {
            "id": str(rare.id),
            "group_id": str(rare.group_id),
            "name": "Rare",
            "price_delta": 0,
        }
    ]
    well = option("Doneness", "Well done")
    run("modifier.option.update", {"id": str(well.id), "is_default": True})
    assert list(
        ModifierOption.objects.filter(is_default=True).values_list("name", flat=True)
    ) == ["Well done"]


def test_otherwise_there_are_never_more_defaults_than_the_maximum():
    group("Sauces", max_choices=2)
    option("Sauces", "Ketchup", is_default=True)
    option("Sauces", "Mayo", is_default=True)
    message = "This group has more options chosen by default than its maximum."
    with pytest.raises(Conflict) as error:
        option("Sauces", "Mustard", is_default=True)
    assert refusal(error) == (
        "Conflict",
        "modifier.too_many_defaults",
        {"is_default": message},
    )
    mustard = option("Sauces", "Mustard")
    with pytest.raises(Conflict):
        run("modifier.option.update", {"id": str(mustard.id), "is_default": True})
    # Lowering the group's maximum below its defaults is the same refusal, on the maximum.
    with pytest.raises(Conflict) as error:
        run("modifier.group.update", {"group": "Sauces", "max_choices": 1})
    assert refusal(error) == (
        "Conflict",
        "modifier.too_many_defaults",
        {"max_choices": message},
    )
    # No ceiling, no limit.
    run("modifier.group.update", {"group": "Sauces", "max_choices": 0})
    assert (
        run(
            "modifier.option.update", {"id": str(mustard.id), "is_default": True}
        ).is_default
        is True
    )


def test_a_group_holds_at_most_100_options():
    sauces = ModifierGroup.objects.create(name="Sauces")
    ModifierOption.objects.bulk_create(
        [ModifierOption(group=sauces, name=f"O{i}") for i in range(MAX_OPTIONS)]
    )
    with pytest.raises(Conflict) as error:
        option("Sauces", "One more")
    assert error.value.code == "modifier.group_full"


def test_changing_an_option_keeps_what_is_not_sent():
    group("Drinks")
    soda = option(
        "Drinks",
        "Soda",
        kitchen_name="SODA",
        price_delta=250,
        tax_category_key=GENERIC,
        sort_order=3,
    )
    changed = run(
        "modifier.option.update",
        {"option": "soda", "price_delta": 300},
        role="hub_manager",
    )
    assert (
        changed.name,
        changed.kitchen_name,
        changed.price_delta,
        changed.tax_category_key,
        changed.sort_order,
    ) == (
        "Soda",
        "SODA",
        300,
        GENERIC,
        3,
    )
    assert events("modifier.option.updated")[-1] == {
        "id": str(soda.id),
        "group_id": str(soda.group_id),
        "name": "Soda",
        "price_delta": 300,
    }
    run("modifier.option.update", {"id": str(soda.id), "name": "Soda"})
    assert len(events("modifier.option.updated")) == 1


def test_an_option_named_in_two_groups_needs_its_group():
    group("Sauces")
    group("Extras")
    option("Sauces", "Cheese")
    extra_cheese = option("Extras", "Cheese")
    with pytest.raises(Conflict) as error:
        run("modifier.option.update", {"option": "Cheese", "price_delta": 50})
    assert error.value.code == "modifier.option_ambiguous"
    assert (
        "Cheese (Sauces)" in error.value.message
        and "Cheese (Extras)" in error.value.message
    )
    assert (
        run(
            "modifier.option.update",
            {"option": "Cheese", "group": "Extras", "price_delta": 50},
        ).id
        == extra_cheese.id
    )


def test_renaming_an_option_to_a_taken_name_is_a_409():
    group("Sauces")
    option("Sauces", "Ketchup")
    mayo = option("Sauces", "Mayo")
    with pytest.raises(Conflict) as error:
        run("modifier.option.update", {"id": str(mayo.id), "name": "ketchup"})
    assert error.value.code == "modifier.option_name_taken"


def test_deleting_an_option():
    group("Sauces")
    ketchup = option("Sauces", "Ketchup", price_delta=20)
    assert (
        run("modifier.option.delete", {"option": "Ketchup", "group": "Sauces"}).id
        == ketchup.id
    )
    assert ModifierOption.objects.count() == 0
    assert events("modifier.option.deleted") == [
        {
            "id": str(ketchup.id),
            "group_id": str(ketchup.group_id),
            "name": "Ketchup",
            "price_delta": 20,
        }
    ]
    with pytest.raises(NotFound) as error:
        run("modifier.option.delete", {"id": str(ketchup.id)})
    assert error.value.message == "This option does not exist."


# Links (MODIFIER-F05)


def test_linking_a_group_to_a_product_by_its_sku_and_to_a_category_by_its_name():
    sauces = group("Sauces")
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    by_product = run("modifier.link.attach", {"group": "Sauces", "product": "bur-01"})
    assert (
        by_product.target_kind,
        by_product.product_id,
        by_product.product_name,
        by_product.product_sku,
    ) == (
        "product",
        burger.id,
        "Burger",
        "BUR-01",
    )
    by_category = run(
        "modifier.link.attach", {"group_id": str(sauces.id), "category": "Mains"}
    )
    assert (
        by_category.target_kind,
        by_category.category_id,
        by_category.category_name,
        by_category.product_id,
    ) == (
        "category",
        mains.id,
        "Mains",
        None,
    )
    assert events("modifier.link.attached") == [
        {
            "id": str(by_product.id),
            "group_id": str(sauces.id),
            "product_id": str(burger.id),
            "category_id": None,
        },
        {
            "id": str(by_category.id),
            "group_id": str(sauces.id),
            "product_id": None,
            "category_id": str(mains.id),
        },
    ]
    assert ModifierLink.objects.get(pk=by_product.id).created_by == "tester"


def test_the_same_link_twice_is_a_409():
    group("Sauces")
    make_product("Burger", "BUR-01")
    run("modifier.link.attach", {"group": "Sauces", "product": "BUR-01"})
    with pytest.raises(Conflict) as error:
        run("modifier.link.attach", {"group": "Sauces", "product": "Burger"})
    assert refusal(error) == (
        "Conflict",
        "modifier.link_exists",
        {"__all__": "This group already applies there."},
    )


def test_a_deleted_or_unknown_product_or_category_cannot_be_linked():
    group("Sauces")
    burger = make_product("Burger", "BUR-01")
    run("inventory.product.delete", {"id": str(burger.id)})
    with pytest.raises(NotFound) as error:
        run("modifier.link.attach", {"group": "Sauces", "product_id": str(burger.id)})
    assert error.value.message == "This product does not exist in this hub."
    with pytest.raises(NotFound):
        run("modifier.link.attach", {"group": "Sauces", "category": "Nowhere"})


def test_detaching_by_the_link_or_by_the_group_and_the_target():
    sauces = group("Sauces")
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    by_product = run("modifier.link.attach", {"group": "Sauces", "product": "BUR-01"})
    by_category = run("modifier.link.attach", {"group": "Sauces", "category": "Mains"})
    assert run("modifier.link.detach", {"id": str(by_product.id)}).id == by_product.id
    assert (
        run(
            "modifier.link.detach", {"group": "Sauces", "category_id": str(mains.id)}
        ).id
        == by_category.id
    )
    assert ModifierLink.objects.count() == 0
    assert events("modifier.link.detached") == [
        {
            "id": str(by_product.id),
            "group_id": str(sauces.id),
            "product_id": str(burger.id),
            "category_id": None,
        },
        {
            "id": str(by_category.id),
            "group_id": str(sauces.id),
            "product_id": None,
            "category_id": str(mains.id),
        },
    ]
    # It can be linked again afterwards; detaching what is not linked is a 404.
    run("modifier.link.attach", {"group": "Sauces", "product": "BUR-01"})
    with pytest.raises(NotFound) as error:
        run("modifier.link.detach", {"group": "Sauces", "category": "Mains"})
    assert error.value.message == "This group does not apply there."


def test_the_reactions_are_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run(
            "modifier.link.drop_product",
            {"id": str(uuid.uuid7())},
            ctx=ctx_for("hub_owner"),
        )


def test_a_product_with_its_food_tax_is_still_linkable_whatever_its_category():
    group("Sauces")
    make_product("Paella", "PAE", tax=FOOD)
    assert (
        run("modifier.link.attach", {"group": "Sauces", "product": "PAE"}).product_sku
        == "PAE"
    )


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=1.0, stop_after=None):
    return [json.loads(note.payload) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_a_write_in_scope_b_notifies_b_only(listen):
    on_a, on_b = listen(A), listen(B)

    run("modifier.group.create", {"name": "Sauces"}, ctx=ctx_for("hub_admin", B))

    assert received(on_b, stop_after=1) == [{"events": ["modifier.group.created"]}]
    assert received(on_a, timeout=0.3) == []
