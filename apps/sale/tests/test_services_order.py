"""The open check (SALE-F01, F09, F10, F13–F18, F20, F23, F24, F26): every write of ``services.py``
that builds a check, with Inventory's real catalog and tax's real categories.

Every write locks the check first and raises its version; a line keeps the price it was ordered at.
"""

from decimal import Decimal
from uuid import uuid7

import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.sale.models import Order, OrderLine, Settings
from apps.sale.tests.conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


def events(prefix: str = "sale.") -> list[tuple[str, dict]]:
    return [
        (e.name, e.payload)
        for e in OutboxEvent.objects.filter(name__startswith=prefix).order_by(
            "created_at", "id"
        )
    ]


def names(prefix: str = "sale.") -> list[str]:
    return [name for name, _payload in events(prefix)]


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink", cost=40)


@pytest.fixture
def steak(product):
    return product("Steak", "STK", 1800, "restaurant.food")


@pytest.fixture
def prawns(product):
    """Prawns at 12.00 € a kilo, sold by the kilo."""
    return product("Prawns", "PRW", 1200, "restaurant.food", unit="kg")


def open_order(*lines, ctx=None, **more):
    return run("sale.order.open", {"lines": list(lines), **more}, ctx)


def add(order_id, ctx=None, **line):
    return run("sale.order.add_line", {"order_id": str(order_id), **line}, ctx)


def line_of(order, index: int = 0):
    return order.lines[index]


# ── Opening ─────────────────────────────────────────────────────────────────────────────────────


def test_a_new_check_is_open_empty_at_version_one(coffee):
    order = open_order(label="Ana — terrace")
    assert (
        order.status,
        order.label,
        order.version,
        order.provisional_total,
        order.lines,
    ) == (
        "open",
        "Ana — terrace",
        1,
        0,
        [],
    )
    assert events() == [
        ("sale.order.opened", {"order_id": str(order.id), "lines_count": 0})
    ]


def test_opening_with_lines_prices_them_from_the_catalog(coffee, steak):
    order = open_order(
        {"product": "COF", "quantity": "2"}, {"product_id": str(steak.id)}
    )
    first, second = order.lines
    assert (
        first.name,
        first.sku,
        first.unit_price,
        first.quantity,
        first.line_total,
    ) == (
        "Coffee",
        "COF",
        150,
        Decimal("2.000"),
        300,
    )
    assert (first.tax_category_key, first.product_id, first.position) == (
        "restaurant.drink",
        coffee.id,
        1,
    )
    assert (second.name, second.line_total, second.position) == ("Steak", 1800, 2)
    assert order.provisional_total == 2100


def test_a_line_keeps_the_price_it_was_ordered_at(coffee):
    order = open_order({"product": "COF"})
    run(
        "inventory.product.update",
        {"id": str(coffee.id), "price": 200},
        system_context(A),
    )
    order = add(order.id, product="COF")
    assert [line.unit_price for line in order.lines] == [150, 200]
    assert order.provisional_total == 350


def test_a_product_is_named_by_its_sku_or_its_name_and_never_guessed(product):
    product("Coffee with milk", "CWM", 170, "restaurant.drink")
    product("Coffee black", "CBL", 150, "restaurant.drink")
    order = open_order()
    assert add(order.id, product="coffee black").lines[0].sku == "CBL"
    with pytest.raises(Conflict) as refusal:
        add(order.id, product="coffee")
    assert refusal.value.code == "inventory.product_ambiguous"
    with pytest.raises(Conflict) as refusal:
        add(order.id, product="tea")
    assert refusal.value.code == "sale.product_not_available"


def test_an_inactive_product_is_not_sold(coffee):
    run(
        "inventory.product.update",
        {"id": str(coffee.id), "is_active": False},
        system_context(A),
    )
    with pytest.raises(Conflict) as refusal:
        add(open_order().id, product="COF")
    assert refusal.value.code == "sale.product_not_available"


def test_a_product_without_tax_category_is_not_sold(coffee):
    from apps.inventory.models import Product

    Product.objects.filter(pk=coffee.id).update(tax_category=None)
    with pytest.raises(Conflict) as refusal:
        add(open_order().id, product="COF")
    assert refusal.value.code == "sale.tax_category_missing"
    assert "tax category" in refusal.value.message


def test_a_quantity_must_fit_the_step_of_its_unit(coffee, prawns, product):
    order = open_order()
    with pytest.raises(Conflict) as refusal:
        add(order.id, product="COF", quantity="1.5")
    assert refusal.value.code == "sale.quantity_off_grid"
    # 0.345 kg of prawns at 12.00 €/kg = 4.14 €.
    order = add(order.id, product="PRW", quantity="0.345")
    assert (order.lines[0].unit, order.lines[0].line_total) == ("kg", 414)
    # Grams step by one gram.
    product("Saffron", "SAF", 900, "product.reduced", unit="g", pricing_unit="kg")
    with pytest.raises(Conflict) as refusal:
        add(order.id, product="SAF", quantity="0.5")
    assert refusal.value.code == "sale.quantity_off_grid"
    # 250 g priced per kilo: a quarter of 9.00 €.
    assert add(order.id, product="SAF", quantity="250").lines[-1].line_total == 225


def test_a_price_per_hundred_units(product):
    product("Screws", "SCR", 37, "product.generic", price_quantity="100")
    order = add(open_order().id, product="SCR", quantity="3")
    assert order.lines[0].line_total == 1  # 0.37 € per 100 × 3 = 0.0111 € → 1 cent


def test_a_line_on_a_closed_check_is_refused(coffee):
    order = open_order()
    Order.objects.filter(pk=order.id).update(status="completed")
    with pytest.raises(Conflict) as refusal:
        add(order.id, product="COF")
    assert refusal.value.code == "sale.order_changed"


def test_a_check_that_does_not_exist(coffee):
    with pytest.raises(NotFound) as refusal:
        add(uuid7(), product="COF")
    assert refusal.value.code == "sale.order_not_found"


# ── Open price ──────────────────────────────────────────────────────────────────────────────────


def test_an_open_price_line_takes_the_department_and_its_vat():
    run(
        "sale.department.create",
        {"name": "Fruit", "tax_category_key": "product.super_reduced"},
    )
    order = run(
        "sale.order.add_open_line",
        {"order_id": str(open_order().id), "department": "Fruit", "unit_price": 250},
    )
    line = order.lines[0]
    assert (
        line.name,
        line.unit_price,
        line.tax_category_key,
        line.line_total,
        line.product_id,
    ) == (
        "Fruit",
        250,
        "product.super_reduced",
        250,
        None,
    )
    assert line.department_id is not None


def test_with_inventory_off_no_product_is_sold_and_an_open_price_still_is(coffee, monkeypatch):
    # Inventory is asked by name through the platform's door: off, the till's own 409, and an open price needs no catalog.
    from apps.sale.queries import CATALOG_UNAVAILABLE
    from base import activation

    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"inventory"}))
    order = open_order()
    with pytest.raises(Conflict) as refused:
        add(order.id, product="COF")
    assert (refused.value.code, refused.value.message) == ("sale.catalog_unavailable", str(CATALOG_UNAVAILABLE))
    added = run(
        "sale.order.add_open_line",
        {"order_id": str(order.id), "tax_category_key": "product.generic", "unit_price": 999, "name": "Various"},
    )
    assert [line.unit_price for line in added.lines] == [999]


def test_without_departments_an_open_price_takes_a_tax_category_by_name():
    order = run(
        "sale.order.add_open_line",
        {
            "order_id": str(open_order().id),
            "tax_category_key": "product.generic",
            "unit_price": 999,
            "name": "Various",
        },
    )
    assert (order.lines[0].name, order.lines[0].tax_category_key) == (
        "Various",
        "product.generic",
    )


def test_an_open_price_needs_its_permission_at_every_door():
    run(
        "sale.department.create",
        {"name": "Fruit", "tax_category_key": "product.super_reduced"},
    )
    employee = ctx_for(EMPLOYEE)
    order = open_order(ctx=employee)
    with pytest.raises(PermissionDenied):
        run(
            "sale.order.add_open_line",
            {"order_id": str(order.id), "department": "Fruit", "unit_price": 250},
            employee,
        )
    with pytest.raises(PermissionDenied):
        run(
            "sale.order.open",
            {"open_lines": [{"department": "Fruit", "unit_price": 250}]},
            employee,
        )


def test_an_unknown_department_or_category_is_refused_by_its_field():
    order = open_order()
    with pytest.raises(InvalidPayload) as refusal:
        run(
            "sale.order.add_open_line",
            {"order_id": str(order.id), "department": "Ghost", "unit_price": 1},
        )
    assert set(refusal.value.fields) == {"department"}
    with pytest.raises(InvalidPayload) as refusal:
        run(
            "sale.order.add_open_line",
            {"order_id": str(order.id), "tax_category_key": "nowhere", "unit_price": 1},
        )
    assert set(refusal.value.fields) == {"tax_category_key"}


# ── Changing a line ─────────────────────────────────────────────────────────────────────────────


def test_changing_the_quantity_prices_it_from_the_row_and_raises_the_version(coffee):
    order = open_order({"product": "COF"})
    OutboxEvent.objects.all().delete()
    changed = run(
        "sale.order.update_line",
        {"order_id": str(order.id), "line_id": str(line_of(order).id), "quantity": "3"},
    )
    assert (
        changed.lines[0].quantity,
        changed.lines[0].line_total,
        changed.provisional_total,
    ) == (Decimal("3.000"), 450, 450)
    assert changed.version == order.version + 1
    assert names() == ["sale.order.changed"]


def test_a_note_is_kept_unless_sent_and_an_empty_one_clears_it(coffee):
    order = open_order({"product": "COF", "notes": "no sugar"})
    ref = {"order_id": str(order.id), "line_id": str(line_of(order).id)}
    assert (
        run("sale.order.update_line", {**ref, "quantity": "2"}).lines[0].notes
        == "no sugar"
    )
    assert (
        run("sale.order.update_line", {**ref, "notes": "very hot"}).lines[0].notes
        == "very hot"
    )
    assert run("sale.order.update_line", {**ref, "notes": ""}).lines[0].notes == ""


def test_a_comp_is_charged_at_zero(coffee):
    order = open_order({"product": "COF", "quantity": "2"})
    ref = {"order_id": str(order.id), "line_id": str(line_of(order).id)}
    comped = run(
        "sale.order.update_line", {**ref, "is_gift": True, "gift_reason": "regular"}
    )
    assert (
        comped.lines[0].is_gift,
        comped.lines[0].line_total,
        comped.provisional_total,
    ) == (True, 0, 0)
    back = run("sale.order.update_line", {**ref, "is_gift": False})
    assert (
        back.lines[0].is_gift,
        back.lines[0].gift_reason,
        back.lines[0].line_total,
    ) == (False, "", 300)


def test_the_professional_of_a_line(coffee):
    staff = uuid7()
    order = open_order({"product": "COF"})
    ref = {"order_id": str(order.id), "line_id": str(line_of(order).id)}
    assert (
        run("sale.order.set_line_staff", {**ref, "staff_id": str(staff)})
        .lines[0]
        .staff_id
        == staff
    )
    assert (
        run("sale.order.set_line_staff", {**ref, "staff_id": None}).lines[0].staff_id
        is None
    )


def test_removing_a_line_not_sent(coffee, steak):
    order = open_order({"product": "COF"}, {"product": "STK"})
    OutboxEvent.objects.all().delete()
    left = run(
        "sale.order.remove_line",
        {"order_id": str(order.id), "line_id": str(line_of(order).id)},
    )
    assert [line.name for line in left.lines] == [
        "Steak"
    ] and left.provisional_total == 1800
    assert OrderLine.objects.get(pk=line_of(order).id).removed_at is not None
    assert events() == [
        (
            "sale.order.line_removed",
            {"order_id": str(order.id), "line_id": str(line_of(order).id)},
        ),
        ("sale.order.changed", {"order_id": str(order.id)}),
    ]
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.remove_line",
            {"order_id": str(order.id), "line_id": str(line_of(order).id)},
        )
    assert refusal.value.code == "sale.order_line_not_removable"


# ── The kitchen ─────────────────────────────────────────────────────────────────────────────────


def test_firing_sends_the_pending_lines_as_a_round(coffee, steak):
    staff = uuid7()
    order = open_order({"product": "STK", "notes": "rare", "staff_id": str(staff)})
    OutboxEvent.objects.all().delete()
    fired = run("sale.order.fire", {"order_id": str(order.id), "label": "Table 4"})
    assert (fired.round_no, fired.lines_count) == (1, 1)
    assert (
        fired.order.lines[0].round_no == 1 and fired.order.lines[0].fired_at is not None
    )
    ((name, payload), changed) = events()
    assert name == "sale.order.fired" and changed[0] == "sale.order.changed"
    assert (
        payload["round_no"] == 1
        and payload["label"] == "Table 4"
        and payload["channel"] == "dine_in"
    )
    assert payload["items"] == [
        {
            "order_item_id": str(line_of(order).id),
            "product_id": str(steak.id),
            "product_name": "Steak",
            "quantity": "1.000",
            "unit": "ud",
            "notes": "rare",
            "is_service": False,
            "category_id": None,
            "staff_id": str(staff),
            # SALE-F11: the kitchen text of its options (MODIFIER-F08); none chosen here.
            "modifiers": "",
            # SALE-F12: a menu's kitchen name and dishes (COMBO-F11); not a menu here.
            "kitchen_name": "",
            "components": [],
        }
    ]
    with pytest.raises(Conflict) as refusal:
        run("sale.order.fire", {"order_id": str(order.id)})
    assert refusal.value.code == "sale.nothing_to_fire"
    second = run("sale.order.fire", {"order_id": str(add(order.id, product="COF").id)})
    assert second.round_no == 2 and second.lines_count == 1


def test_a_round_says_who_sends_it_by_the_name_a_person_reads(steak, django_user_model):
    """«Quién atiende» in ``sale.order.fired`` is a person (KITCHEN-F05, F08): their name, else their e-mail;
    their username (the id of the session) only as the last resort."""
    people = [
        django_user_model.objects.create_user("saas:42", email="ana@example.com", first_name="Ana", last_name="García"),
        django_user_model.objects.create_user("saas:43", email="luis@example.com"),
        django_user_model.objects.create_user("saas:44"),
    ]
    sent = []
    for person in people:
        order = open_order({"product": "STK"})
        OutboxEvent.objects.all().delete()
        run("sale.order.fire", {"order_id": str(order.id)}, ctx_for(actor=person))
        ((_, payload), _changed) = events()
        sent.append(payload["waiter"])
    assert sent == ["Ana García", "luis@example.com", "saas:44"]


def test_a_round_names_who_attends_the_check_else_who_sends_it(steak, django_user_model):
    """KITCHEN-F18, F08 (kitchen#82, hub#2033): the till names who attends the check («Atiende», a member of the
    team who may have no login); the kitchen reads that name. Empty or blank: who sends it."""
    luis = django_user_model.objects.create_user("saas:45", first_name="Luis", last_name="Pérez")
    named = []
    for waiter in ("Marta Ruiz", "   ", ""):
        order = open_order({"product": "STK"})
        OutboxEvent.objects.all().delete()
        run("sale.order.fire", {"order_id": str(order.id), "waiter": waiter}, ctx_for(actor=luis))
        ((_, payload), _changed) = events()
        named.append(payload["waiter"])
    assert named == ["Marta Ruiz", "Luis Pérez", "Luis Pérez"]


def test_a_line_sent_to_the_kitchen_is_not_changed_nor_removed_but_voided(
    steak, coffee
):
    order = open_order({"product": "STK"}, {"product": "COF"})
    run("sale.order.fire", {"order_id": str(order.id)})
    ref = {"order_id": str(order.id), "line_id": str(line_of(order).id)}
    for name, data in (
        ("sale.order.update_line", {"quantity": "2"}),
        ("sale.order.set_line_discount", {"discount_percent": "10"}),
        ("sale.order.set_line_staff", {"staff_id": None}),
        ("sale.order.split_line", {}),
    ):
        with pytest.raises(Conflict) as refusal:
            run(name, {**ref, **data})
        assert refusal.value.code in {
            "sale.order_line_not_available",
            "sale.line_not_splittable",
        }, name
    with pytest.raises(Conflict) as refusal:
        run("sale.order.remove_line", ref)
    assert refusal.value.code == "sale.order_line_not_removable"
    OutboxEvent.objects.all().delete()
    voided = run(
        "sale.order.void_line",
        {**ref, "reason": "  Wrong dish "},
        ctx_for(actor="manager"),
    )
    assert [line.name for line in voided.lines] == [
        "Coffee"
    ] and voided.provisional_total == 150
    row = OrderLine.objects.get(pk=line_of(order).id)
    assert (row.void_reason, row.voided_by, row.removed_at is not None) == (
        "Wrong dish",
        "manager",
        True,
    )
    assert events() == [
        (
            "sale.order.line_removed",
            {"order_id": str(order.id), "line_id": str(row.id)},
        ),
        (
            "sale.order.line_voided",
            {"order_id": str(order.id), "line_id": str(row.id), "reason": "Wrong dish"},
        ),
        ("sale.order.changed", {"order_id": str(order.id)}),
    ]
    with pytest.raises(Conflict) as refusal:
        run("sale.order.void_line", {**ref, "reason": "again"})
    assert refusal.value.code == "sale.order_line_not_voidable"


def test_a_line_not_sent_is_removed_not_voided_and_voiding_is_the_managers(steak):
    order = open_order({"product": "STK"})
    ref = {"order_id": str(order.id), "line_id": str(line_of(order).id)}
    with pytest.raises(Conflict) as refusal:
        run("sale.order.void_line", {**ref, "reason": "x"})
    assert refusal.value.code == "sale.order_line_not_voidable"
    run("sale.order.fire", {"order_id": str(order.id)})
    with pytest.raises(PermissionDenied):
        run("sale.order.void_line", {**ref, "reason": "x"}, ctx_for(EMPLOYEE))


# ── Splitting a line, splitting and merging checks ──────────────────────────────────────────────


def test_a_line_of_n_units_splits_into_n_lines_of_one(steak):
    order = open_order({"product": "STK", "quantity": "3", "notes": "with Marta"})
    split = run(
        "sale.order.split_line",
        {"order_id": str(order.id), "line_id": str(line_of(order).id)},
    )
    assert len(split.new_line_ids) == 2
    assert [
        (line.quantity, line.line_total, line.notes) for line in split.order.lines
    ] == [(Decimal("1.000"), 1800, "with Marta")] * 3
    assert split.order.lines[0].id == line_of(order).id
    assert split.order.provisional_total == 5400


@pytest.mark.parametrize(
    "line",
    [
        {"product": "STK"},
        {"product": "STK", "quantity": "51"},
        {"product": "STK", "quantity": "2", "is_gift": True},
    ],
    ids=["one unit", "over fifty", "a comp"],
)
def test_a_line_that_cannot_be_split(steak, line):
    order = open_order(line)
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.split_line",
            {"order_id": str(order.id), "line_id": str(line_of(order).id)},
        )
    assert refusal.value.code == "sale.line_not_splittable"


def test_a_fractional_line_cannot_be_split(prawns):
    order = open_order({"product": "PRW", "quantity": "1.5"})
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.split_line",
            {"order_id": str(order.id), "line_id": str(line_of(order).id)},
        )
    assert refusal.value.code == "sale.line_not_splittable"


def test_splitting_a_check_moves_whole_lines_and_both_add_up(coffee, steak):
    order = open_order(
        {"product": "COF"}, {"product": "STK"}, {"product": "COF", "quantity": "2"}
    )
    moving = [str(order.lines[1].id), str(order.lines[2].id)]
    OutboxEvent.objects.all().delete()
    split = run(
        "sale.order.split",
        {"order_id": str(order.id), "line_ids": moving, "label": "Second"},
    )
    assert [line.name for line in split.order.lines] == ["Coffee"]
    assert [line.name for line in split.new_order.lines] == ["Steak", "Coffee"]
    assert (
        split.order.provisional_total + split.new_order.provisional_total
        == 150 + 1800 + 300
    )
    assert split.new_order.label == "Second"
    assert names() == ["sale.order.opened", "sale.order.changed", "sale.order.changed"]
    # A replay: the lines are not there any more.
    with pytest.raises(Conflict) as refusal:
        run("sale.order.split", {"order_id": str(order.id), "line_ids": moving})
    assert refusal.value.code == "sale.order_changed"


def test_a_blank_split_opens_an_empty_check(coffee):
    order = open_order({"product": "COF"})
    split = run("sale.order.split", {"order_id": str(order.id)})
    assert split.new_order.lines == [] and split.order.provisional_total == 150


def test_merging_moves_the_unpaid_lines_and_voids_the_absorbed_check(coffee, steak):
    first = open_order({"product": "COF"})
    second = open_order({"product": "STK"})
    run("sale.order.fire", {"order_id": str(first.id)})
    OutboxEvent.objects.all().delete()
    merged = run(
        "sale.order.merge",
        {"from_order_id": str(first.id), "to_order_id": str(second.id)},
    )
    assert [line.name for line in merged.lines] == ["Steak", "Coffee"]
    assert merged.provisional_total == 1950
    # What was already sent to the kitchen keeps its round: it is not sent twice.
    assert merged.lines[1].round_no == 1
    assert Order.objects.get(pk=first.id).status == "voided"
    assert (
        "sale.order.merged",
        {"from_order_id": str(first.id), "to_order_id": str(second.id)},
    ) in events()
    # Again: nothing moves and nothing is said.
    OutboxEvent.objects.all().delete()
    again = run(
        "sale.order.merge",
        {"from_order_id": str(first.id), "to_order_id": str(second.id)},
    )
    assert len(again.lines) == 2 and events() == []


def test_a_check_cannot_merge_into_a_closed_one_nor_into_itself(coffee):
    first = open_order({"product": "COF"})
    second = open_order()
    Order.objects.filter(pk=second.id).update(status="completed")
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.merge",
            {"from_order_id": str(first.id), "to_order_id": str(second.id)},
        )
    assert refusal.value.code == "sale.order_changed"
    assert Order.objects.get(pk=first.id).status == "open"
    with pytest.raises(Conflict):
        run(
            "sale.order.merge",
            {"from_order_id": str(first.id), "to_order_id": str(first.id)},
        )


# ── Voiding a check ─────────────────────────────────────────────────────────────────────────────


def test_voiding_an_open_check(coffee):
    order = open_order({"product": "COF"})
    OutboxEvent.objects.all().delete()
    voided = run(
        "sale.order.void", {"order_id": str(order.id)}, ctx_for(actor="manager")
    )
    assert (
        voided.status == "voided"
        and Order.objects.get(pk=order.id).voided_by == "manager"
    )
    assert events() == [("sale.order.voided", {"order_id": str(order.id)})]
    # Twice: nothing new.
    assert run("sale.order.void", {"order_id": str(order.id)}).status == "voided"
    assert len(events()) == 1


def test_a_charged_check_cannot_be_voided_and_voiding_is_the_managers(coffee):
    order = open_order({"product": "COF"})
    with pytest.raises(PermissionDenied):
        run("sale.order.void", {"order_id": str(order.id)}, ctx_for(EMPLOYEE))
    Order.objects.filter(pk=order.id).update(status="completed")
    with pytest.raises(Conflict) as refusal:
        run("sale.order.void", {"order_id": str(order.id)})
    assert refusal.value.code == "sale.order_unavailable"


def test_whoever_builds_checks_voids_an_empty_one(coffee):
    # A party that leaves without ordering does not need a manager (TABLE-F21): a check with no live
    # line and no charge is voided with «build the check» alone, by the employee's own session.
    waiter = ctx_for(EMPLOYEE, actor="waiter")
    assert "sale.void_sale" not in waiter.permissions
    empty = open_order(ctx=waiter)
    voided = run("sale.order.void", {"order_id": str(empty.id)}, waiter)
    assert voided.status == "voided"
    assert Order.objects.get(pk=empty.id).voided_by == "waiter"
    # A check whose only line was taken off is empty too.
    emptied = open_order({"product": "COF"}, ctx=waiter)
    run(
        "sale.order.remove_line",
        {"order_id": str(emptied.id), "line_id": str(line_of(emptied).id)},
        waiter,
    )
    assert run("sale.order.void", {"order_id": str(emptied.id)}, waiter).status == "voided"


def test_a_check_with_something_ordered_or_charged_is_the_managers_to_void(coffee):
    waiter = ctx_for(EMPLOYEE)
    ordered = open_order({"product": "COF"}, ctx=waiter)
    with pytest.raises(PermissionDenied) as refusal:
        run("sale.order.void", {"order_id": str(ordered.id)}, waiter)
    assert "sale.void_sale" in str(refusal.value)
    assert Order.objects.get(pk=ordered.id).status == "open"
    # Part charged, the rest taken off: nothing left to charge, but money moved on it.
    partly = open_order({"product": "COF"}, {"product": "COF"}, ctx=waiter)
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "void-empty-0001",
            "order_id": str(partly.id),
            "line_ids": [str(line_of(partly).id)],
            "payments": [{"method": "card"}],
        },
        waiter,
    )
    run(
        "sale.order.remove_line",
        {"order_id": str(partly.id), "line_id": str(line_of(partly, 1).id)},
        waiter,
    )
    with pytest.raises(PermissionDenied):
        run("sale.order.void", {"order_id": str(partly.id)}, waiter)
    # Who may void, voids it.
    assert run("sale.order.void", {"order_id": str(partly.id)}).status == "voided"


# ── Discounts ───────────────────────────────────────────────────────────────────────────────────


def cap(percent: int, **more) -> None:
    run("sale.settings.update", {"max_discount_percent": percent, **more})


def test_a_ticket_discount_is_kept_on_the_check(coffee):
    order = open_order({"product": "COF", "quantity": "2"})
    ref = {"order_id": str(order.id)}
    changed = run(
        "sale.order.set_discount",
        {**ref, "discount_percent": "12.5", "discount_amount": 30},
    )
    assert (
        changed.discount_percent,
        changed.discount_amount,
        changed.discount_approved,
    ) == (Decimal("12.50"), 30, False)
    # The amount is kept when not sent; the provisional total does not change.
    changed = run("sale.order.set_discount", {**ref, "discount_percent": "5"})
    assert (
        changed.discount_percent,
        changed.discount_amount,
        changed.provisional_total,
    ) == (Decimal("5.00"), 30, 300)


def test_a_ticket_discount_over_the_cap_is_the_managers(coffee):
    cap(10)
    order = open_order({"product": "COF", "quantity": "2"})
    ref = {"order_id": str(order.id)}
    with pytest.raises(Conflict) as refusal:
        run("sale.order.set_discount", {**ref, "discount_percent": "90"})
    assert refusal.value.code == "sale.discount_over_limit"
    # A fixed amount is capped on what it comes off: 10 % of 3.00 is 0.30.
    with pytest.raises(Conflict):
        run(
            "sale.order.set_discount",
            {**ref, "discount_percent": "0", "discount_amount": 31},
        )
    assert (
        run(
            "sale.order.set_discount",
            {**ref, "discount_percent": "0", "discount_amount": 30},
        ).discount_amount
        == 30
    )
    with pytest.raises(PermissionDenied):
        run(
            "sale.order.set_discount_over_limit",
            {**ref, "discount_percent": "90"},
            ctx_for(EMPLOYEE),
        )
    approved = run(
        "sale.order.set_discount_over_limit",
        {**ref, "discount_percent": "90"},
        ctx_for(actor="manager"),
    )
    assert approved.discount_approved is True
    assert Order.objects.get(pk=order.id).discount_approved_by == "manager"
    # The usual door afterwards wipes the approval (the 0.30 kept on top of 5 % would pass the cap).
    usual = run(
        "sale.order.set_discount",
        {**ref, "discount_percent": "5", "discount_amount": 0},
    )
    assert usual.discount_approved is False


def test_a_discount_bigger_than_the_check_or_with_discounts_off(coffee):
    order = open_order({"product": "COF"})
    ref = {"order_id": str(order.id)}
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.set_discount",
            {**ref, "discount_percent": "0", "discount_amount": 151},
        )
    assert refusal.value.code == "sale.discount_out_of_range"
    cap(100, allow_discounts=False)
    with pytest.raises(Conflict) as refusal:
        run("sale.order.set_discount", {**ref, "discount_percent": "5"})
    assert refusal.value.code == "sale.discounts_not_allowed"
    # Removing one is always possible.
    assert (
        run(
            "sale.order.set_discount",
            {**ref, "discount_percent": "0", "discount_amount": 0},
        ).discount_percent
        == 0
    )


def test_a_line_discount(coffee):
    cap(10)
    order = open_order({"product": "COF", "quantity": "2"})
    ref = {"order_id": str(order.id), "line_id": str(line_of(order).id)}
    changed = run("sale.order.set_line_discount", {**ref, "discount_percent": "10"})
    assert (
        changed.lines[0].discount_percent,
        changed.lines[0].line_total,
        changed.provisional_total,
    ) == (
        Decimal("10.00"),
        270,
        270,
    )
    with pytest.raises(Conflict) as refusal:
        run("sale.order.set_line_discount", {**ref, "discount_percent": "50"})
    assert refusal.value.code == "sale.discount_over_limit"
    approved = run(
        "sale.order.set_line_discount_over_limit",
        {**ref, "discount_percent": "50"},
        ctx_for(actor="manager"),
    )
    assert (approved.lines[0].line_total, approved.lines[0].discount_approved) == (
        150,
        True,
    )


def test_discounts_on_a_closed_check(coffee):
    order = open_order({"product": "COF"})
    Order.objects.filter(pk=order.id).update(status="voided")
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.set_discount",
            {"order_id": str(order.id), "discount_percent": "5"},
        )
    assert refusal.value.code == "sale.order_unavailable"


# ── Title and appointment ───────────────────────────────────────────────────────────────────────


def test_the_title_and_the_appointment_of_a_check():
    order = open_order()
    appointment = uuid7()
    assert (
        run(
            "sale.order.set_label",
            {"order_id": str(order.id), "label": "Ana — terrace"},
        ).label
        == "Ana — terrace"
    )
    linked = run(
        "sale.order.set_appointment",
        {"order_id": str(order.id), "appointment_id": str(appointment)},
    )
    assert linked.appointment_id == appointment and linked.version == 3
    assert (
        run(
            "sale.order.set_appointment",
            {"order_id": str(order.id), "appointment_id": None},
        ).appointment_id
        is None
    )
    Order.objects.filter(pk=order.id).update(status="completed")
    with pytest.raises(Conflict) as refusal:
        run("sale.order.set_label", {"order_id": str(order.id), "label": "late"})
    assert refusal.value.code == "sale.order_unavailable"


def test_a_check_of_an_appointment_opens_once(coffee):
    # Two «Charge» of the same appointment (two taps, two devices) never open two checks of it: the
    # second answers the open check it already has, as it is, and adds nothing to it.
    appointment = uuid7()
    first = open_order({"product": "COF"}, appointment_id=str(appointment), label="Ana · APT-1")
    again = open_order({"product": "COF"}, appointment_id=str(appointment), label="Ana · APT-1")
    assert (first.already, again.already) == (False, True)
    assert again.id == first.id and len(again.lines) == 1
    assert Order.objects.filter(appointment_id=appointment).count() == 1
    assert names().count("sale.order.opened") == 1
    # Once that check is no longer open (charged, voided), the appointment may open another.
    run("sale.order.void", {"order_id": str(first.id)})
    third = open_order({"product": "COF"}, appointment_id=str(appointment))
    assert (third.already, third.id != first.id) == (False, True)


def test_an_appointment_is_linked_to_one_open_check_at_a_time(coffee):
    appointment = uuid7()
    open_order({"product": "COF"}, appointment_id=str(appointment))
    other = open_order({"product": "COF"})
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.order.set_appointment",
            {"order_id": str(other.id), "appointment_id": str(appointment)},
        )
    assert refusal.value.code == "sale.appointment_check_open"
    assert Order.objects.get(pk=other.id).appointment_id is None


def test_an_employee_builds_the_check(coffee):
    employee = ctx_for(EMPLOYEE)
    order = open_order({"product": "COF"}, ctx=employee)
    order = add(order.id, employee, product="COF")
    assert len(order.lines) == 2
    run(
        "sale.order.set_discount",
        {"order_id": str(order.id), "discount_percent": "5"},
        employee,
    )


def test_the_settings_of_the_till_are_read_from_their_row():
    assert Settings.objects.count() == 0
    cap(25)
    assert Settings.objects.get().max_discount_percent == 25


def test_sessions_are_released_in_the_order_of_their_voucher_like_settle_locks_them(monkeypatch):
    # Two tills releasing the same two vouchers in opposite orders would lock each other's grant: every
    # release goes by voucher id (then session id), the order service.session.settle locks them in.
    from types import SimpleNamespace

    from apps.sale import services

    released = []
    monkeypatch.setattr(
        services,
        "call_services",
        lambda ctx, name, data: released.append((name, data["id"])),
    )
    low, high = sorted([uuid7(), uuid7()])
    first, second, third = uuid7(), uuid7(), uuid7()
    lines = [
        SimpleNamespace(voucher_session_id=second, voucher_grant_id=high),
        SimpleNamespace(voucher_session_id=None, voucher_grant_id=None),
        SimpleNamespace(voucher_session_id=third, voucher_grant_id=low),
        SimpleNamespace(voucher_session_id=first, voucher_grant_id=high),
    ]
    services._release_vouchers(ctx_for(), lines)
    assert released == [
        ("service.session.release", third),
        ("service.session.release", min(first, second)),
        ("service.session.release", max(first, second)),
    ]
