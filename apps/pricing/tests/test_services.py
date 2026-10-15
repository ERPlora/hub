"""Write operations of the pricing app: one operation = one transaction, with its events in the outbox
(WORKBOOK PRICING-F02 to F05, F07, F08, F10 to F12 and F14). A refusal writes nothing and records no
event."""

import datetime as dt
import json
import uuid
from decimal import Decimal

import psycopg
import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.pricing.models import DiscountRule, PriceItem, PriceList

from .conftest import (
    A,
    B,
    ctx_for,
    make_category,
    make_group,
    make_item,
    make_list,
    make_product,
    make_rule,
    make_service,
)

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin", actor="tester"):
    op = get(name)
    return op(ctx_for(role, actor=actor), op.input.model_validate(data))


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")]


def no_events() -> bool:
    return not OutboxEvent.objects.filter(name__startswith="pricing.").exists()


def refused(error, name, data, role="hub_admin"):
    with pytest.raises(error) as caught:
        run(name, data, role)
    return caught.value


# Price lists: create (F02)


def test_a_list_is_created_active_with_its_group_by_name_and_announced():
    vip = make_group("VIP")
    row = run(
        "pricing.price_list.create",
        {"code": "VIP", "name": "VIP members", "customer_group": "vip", "tax_included": True, "valid_from": "2026-07-01"},
        actor="ana",
    )
    assert (row.code, row.customer_group_id, row.customer_group_name, row.is_active, row.item_count) == (
        "VIP",
        vip.id,
        "VIP",
        True,
        0,
    )
    stored = PriceList.objects.get()
    assert (stored.created_by, stored.updated_by, stored.valid_from) == ("ana", "ana", dt.date(2026, 7, 1))
    assert events("pricing.price_list.created") == [{"id": str(row.id), "code": "VIP", "is_default": False}]


def test_a_repeated_code_is_refused_under_code_whatever_its_case_also_an_inactive_list():
    make_list("VIP", is_active=False)
    error = refused(Conflict, "pricing.price_list.create", {"code": "vip", "name": "Again"})
    assert (error.code, error.fields) == (
        "pricing.duplicate_code",
        {"code": "A price list with that code already exists. Pick a different code."},
    )
    assert PriceList.objects.count() == 1 and no_events()


def test_a_group_that_does_not_exist_is_said_under_its_field():
    error = refused(InvalidPayload, "pricing.price_list.create", {"code": "X", "name": "X", "customer_group": "Nobody"})
    assert set(error.fields) == {"customer_group"}
    error = refused(InvalidPayload, "pricing.price_list.create", {"code": "X", "name": "X", "customer_group_id": str(uuid.uuid7())})
    assert set(error.fields) == {"customer_group_id"}
    assert not PriceList.objects.exists()


def test_a_new_general_list_takes_the_mark_from_the_old_one():
    old = make_list("OLD", is_default=True)
    row = run("pricing.price_list.create", {"code": "NEW", "name": "New", "is_default": True})
    old.refresh_from_db()
    assert (row.is_default, old.is_default) == (True, False)
    assert events("pricing.price_list.default_changed") == [{"id": str(row.id), "is_default": True, "previous_id": str(old.id)}]


def test_a_manager_creates_and_an_employee_does_not():
    run("pricing.price_list.create", {"code": "M", "name": "M"}, role="hub_manager")
    refused(PermissionDenied, "pricing.price_list.create", {"code": "E", "name": "E"}, role="hub_employee")


# Price lists: edit (F03)


def test_an_edit_changes_only_what_is_sent_and_says_so_once():
    vip = make_group("VIP")
    price_list = make_list("VIP", "VIP", customer_group_id=vip.id, currency="EUR")
    row = run("pricing.price_list.update", {"price_list": "VIP", "name": "VIP members", "valid_until": "2026-12-31"})
    assert (row.name, row.customer_group_id, row.valid_until) == ("VIP members", vip.id, dt.date(2026, 12, 31))
    assert events("pricing.price_list.updated") == [{"id": str(price_list.id)}]
    run("pricing.price_list.update", {"id": str(price_list.id), "name": "VIP members"})
    assert len(events("pricing.price_list.updated")) == 1
    cleared = run("pricing.price_list.update", {"id": str(price_list.id), "customer_group_id": None, "tax_included": None})
    assert (cleared.customer_group_id, cleared.tax_included) == (None, None)


def test_an_edit_keeps_the_rules_of_a_list():
    general = make_list("GEN", is_default=True)
    vip = make_group("VIP")
    error = refused(InvalidPayload, "pricing.price_list.update", {"id": str(general.id), "customer_group": "VIP"})
    assert error.fields == {"customer_group": "The general list is for everybody: take its customer group off."}
    dated = make_list("DATED", valid_from=dt.date(2026, 7, 10))
    error = refused(InvalidPayload, "pricing.price_list.update", {"id": str(dated.id), "valid_until": "2026-07-01"})
    assert set(error.fields) == {"valid_until"}
    make_list("TAKEN")
    error = refused(Conflict, "pricing.price_list.update", {"id": str(dated.id), "code": "taken"})
    assert error.code == "pricing.duplicate_code"
    assert vip.id and no_events()


# Price lists: the general one (F04)


def test_making_a_list_general_takes_the_mark_from_the_old_one():
    old = make_list("OLD", is_default=True)
    new = make_list("NEW")
    row = run("pricing.price_list.set_default", {"price_list": "NEW"})
    old.refresh_from_db()
    assert (row.is_default, old.is_default) == (True, False)
    assert events("pricing.price_list.default_changed") == [{"id": str(new.id), "is_default": True, "previous_id": str(old.id)}]
    # Again: nothing changes, nothing is said.
    run("pricing.price_list.set_default", {"price_list": "NEW"})
    assert len(events("pricing.price_list.default_changed")) == 1


def test_the_mark_can_be_taken_off():
    general = make_list("GEN", is_default=True)
    row = run("pricing.price_list.set_default", {"id": str(general.id), "is_default": False})
    assert row.is_default is False
    assert events("pricing.price_list.default_changed") == [{"id": str(general.id), "is_default": False, "previous_id": None}]


def test_an_inactive_list_or_one_with_a_group_is_never_general():
    make_list("OFF", is_active=False)
    make_list("VIP", customer_group_id=make_group().id)
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "OFF"}).code == "pricing.price_list_inactive"
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "VIP"}).code == "pricing.default_has_group"
    assert no_events()


def test_a_general_list_that_keeps_losing_the_race_is_refused_with_its_code(monkeypatch):
    # Another choice wins every try (here: the old general list is never unmarked): a 409 with a stable
    # code, never the database's IntegrityError (a 500).
    import apps.pricing.services as services

    make_list("OLD", is_default=True)
    make_list("NEW")
    monkeypatch.setattr(services, "_take_default_mark", lambda price_list: None)
    error = refused(Conflict, "pricing.price_list.set_default", {"price_list": "NEW"})
    assert error.code == "pricing.default_busy"
    assert PriceList.objects.get(is_default=True).code == "OLD" and no_events()


def test_the_general_list_is_in_the_business_s_currency():
    # A general list in dollars would never apply: the till sells in euros.
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as invalid:  # the schema refuses it, as a route's 422 says
        run("pricing.price_list.create", {"code": "USD", "name": "USD", "currency": "USD", "is_default": True})
    assert [error["loc"] for error in invalid.value.errors()] == [("is_default",)]
    make_list("DOLLARS", currency="USD")
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "DOLLARS"}).code == "pricing.default_currency"
    make_list("GEN", is_default=True)
    error = refused(InvalidPayload, "pricing.price_list.update", {"price_list": "GEN", "currency": "USD"})
    assert set(error.fields) == {"currency"}
    assert PriceList.objects.get(code="GEN").currency == "EUR" and no_events()


# Price lists: deactivate and activate (F05)


def test_a_list_is_deactivated_and_activated_again_but_never_the_general_one():
    price_list = make_list("SUMMER")
    assert run("pricing.price_list.deactivate", {"price_list": "summer"}).is_active is False
    assert refused(Conflict, "pricing.price_list.deactivate", {"price_list": "summer"}).code == (
        "pricing.price_list_already_inactive"
    )
    assert run("pricing.price_list.activate", {"price_list": "summer"}).is_active is True
    assert refused(Conflict, "pricing.price_list.activate", {"price_list": "summer"}).code == "pricing.price_list_already_active"
    assert events("pricing.price_list.deactivated") == [{"id": str(price_list.id)}]
    assert events("pricing.price_list.activated") == [{"id": str(price_list.id)}]
    make_list("GEN", is_default=True)
    error = refused(Conflict, "pricing.price_list.deactivate", {"price_list": "GEN"})
    assert error.code == "pricing.price_list_is_default"


# Prices (F07, F08)


def test_a_product_s_price_is_put_in_a_list_by_their_names():
    price_list = make_list("VIP")
    product = make_product("Shampoo", "SH-1", price=1500)
    row = run("pricing.price_item.add", {"price_list": "vip", "product": "sh-1", "price": 1200, "min_quantity": "10"})
    assert (row.name, row.sku, row.base_price, row.price, row.min_quantity) == ("Shampoo", "SH-1", 1500, 1200, Decimal("10.000"))
    assert events("pricing.price_item.added") == [
        {
            "id": str(row.id),
            "price_list_id": str(price_list.id),
            "product_id": str(product.id),
            "service_id": None,
            "min_quantity": "10.000",
            "price": 1200,
        }
    ]


def test_a_service_s_price_keeps_a_copy_of_its_name():
    make_list("VIP")
    haircut = make_service("Haircut", price=1800)
    row = run("pricing.price_item.add", {"price_list": "VIP", "service": "haircut", "price": 1500})
    assert (row.kind, row.service_id, row.name, row.base_price) == ("service", haircut.id, "Haircut", None)
    assert PriceItem.objects.get().service_name == "Haircut"


def test_the_same_article_twice_from_the_same_quantity_is_refused():
    price_list = make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    make_item(price_list, product, min_quantity="1")
    error = refused(Conflict, "pricing.price_item.add", {"price_list": "VIP", "product_id": str(product.id), "price": 1})
    assert (error.code, set(error.fields)) == ("pricing.price_item_exists", {"min_quantity"})
    assert PriceItem.objects.count() == 1


def test_a_price_needs_a_live_list_a_live_product_and_a_quantity_on_its_step():
    make_list("OFF", is_active=False)
    make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    assert refused(Conflict, "pricing.price_item.add", {"price_list": "OFF", "product": "SH-1", "price": 1}).code == (
        "pricing.price_list_unavailable"
    )
    refused(NotFound, "pricing.price_item.add", {"price_list": "NOPE", "product": "SH-1", "price": 1})
    gone = make_product("Wax", "WX", is_deleted=True)
    refused(NotFound, "pricing.price_item.add", {"price_list": "VIP", "product_id": str(gone.id), "price": 1})
    error = refused(InvalidPayload, "pricing.price_item.add", {"price_list": "VIP", "product_id": str(product.id), "price": 1, "min_quantity": "1.5"})
    assert set(error.fields) == {"min_quantity"}
    by_weight = make_product("Coffee", "CF", unit="kg")
    run("pricing.price_item.add", {"price_list": "VIP", "product_id": str(by_weight.id), "price": 1, "min_quantity": "0.5"})
    make_service("Haircut")
    error = refused(InvalidPayload, "pricing.price_item.add", {"price_list": "VIP", "service": "Haircut", "price": 1, "min_quantity": "2.5"})
    assert set(error.fields) == {"min_quantity"}


def test_without_services_a_service_cannot_be_priced(monkeypatch):
    import apps.pricing.queries as queries
    from live.operations import UnknownOperation

    def missing(name):
        raise UnknownOperation(name)

    monkeypatch.setattr(queries, "get", missing)
    make_list("VIP")
    error = refused(Conflict, "pricing.price_item.add", {"price_list": "VIP", "service": "Haircut", "price": 1})
    assert error.code == "pricing.services_unavailable"


def test_a_price_is_changed_and_removed():
    price_list = make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    item = make_item(price_list, product, price=1200)
    make_item(price_list, product, price=1000, min_quantity="10")
    row = run("pricing.price_item.update", {"id": str(item.id), "price": 1100})
    assert row.price == 1100
    assert events("pricing.price_item.updated") == [{"id": str(item.id)}]
    run("pricing.price_item.update", {"id": str(item.id), "price": 1100})
    assert len(events("pricing.price_item.updated")) == 1
    error = refused(Conflict, "pricing.price_item.update", {"id": str(item.id), "min_quantity": "10"})
    assert error.code == "pricing.price_item_exists"
    removed = run("pricing.price_item.remove", {"price_list": "VIP", "product": "Shampoo"})
    assert removed.id == item.id
    assert events("pricing.price_item.removed") == [{"id": str(item.id), "price_list_id": str(price_list.id)}]
    refused(NotFound, "pricing.price_item.remove", {"id": str(item.id)})
    refused(NotFound, "pricing.price_item.update", {"id": str(item.id), "price": 1})
    assert PriceItem.objects.count() == 1


def test_the_prices_of_a_deactivated_list_are_not_changed_but_can_be_removed():
    price_list = make_list("OFF")
    item = make_item(price_list, make_product("Shampoo", "SH-1"), price=1200)
    price_list.is_active = False
    price_list.save()
    error = refused(Conflict, "pricing.price_item.update", {"id": str(item.id), "price": 1000})
    assert error.code == "pricing.price_list_unavailable"
    assert PriceItem.objects.get().price == 1200 and no_events()
    assert run("pricing.price_item.remove", {"id": str(item.id)}).id == item.id


# Rules (F10 to F12)


def test_a_rule_is_created_with_its_targets_by_their_names():
    category = make_category("Colour")
    vip = make_group("VIP")
    row = run(
        "pricing.rule.create",
        {
            "code": "COL10",
            "name": "Colour 10 %",
            "rule_type": "percent",
            "percent": "10",
            "applies_to": "category",
            "category": "colour",
            "customer_group": "VIP",
            "min_quantity": "2",
        },
    )
    assert (row.category_id, row.category_name, row.customer_group_id, row.min_quantity) == (
        category.id,
        "Colour",
        vip.id,
        Decimal("2.000"),
    )
    assert events("pricing.rule.created") == [{"id": str(row.id), "code": "COL10"}]


def test_every_type_and_scope_is_saved_with_its_values():
    product = make_product("Shampoo", "SH-1")
    haircut = make_service("Haircut")
    fixed = run("pricing.rule.create", {"code": "F", "name": "F", "rule_type": "fixed", "amount": 50, "applies_to": "product", "product": "SH-1"})
    assert (fixed.amount, fixed.product_id, fixed.product_name) == (50, product.id, "Shampoo")
    bogo = run("pricing.rule.create", {"code": "B", "name": "B", "rule_type": "buy_x_get_y", "buy_quantity": 2, "get_quantity": 1, "applies_to": "service", "service": "Haircut"})
    assert (bogo.buy_quantity, bogo.get_quantity, bogo.service_id, bogo.service_name) == (2, 1, haircut.id, "Haircut")
    tiered = run(
        "pricing.rule.create",
        {"code": "T", "name": "T", "rule_type": "tiered", "tiers": [{"min_quantity": "3", "percent": "10"}, {"min_quantity": "6", "percent": "15.5"}]},
    )
    assert DiscountRule.objects.get(pk=tiered.id).tiers == [
        {"min_quantity": "3", "percent": "10"},
        {"min_quantity": "6", "percent": "15.5"},
    ]


def test_an_incoherent_rule_is_refused_field_by_field():
    error = refused(InvalidPayload, "pricing.rule.create", {"code": "X", "name": "X", "rule_type": "percent", "amount": 5, "applies_to": "product"})
    assert set(error.fields) == {"percent", "amount", "product"}
    error = refused(InvalidPayload, "pricing.rule.create", {"code": "X", "name": "X", "rule_type": "percent", "percent": "5", "applies_to": "category", "category": "Nope"})
    assert set(error.fields) == {"category"}
    error = refused(InvalidPayload, "pricing.rule.create", {"code": "X", "name": "X", "rule_type": "percent", "percent": "5", "customer_group": "Nope"})
    assert set(error.fields) == {"customer_group"}
    make_rule("TAKEN")
    error = refused(Conflict, "pricing.rule.create", {"code": "taken", "name": "X", "rule_type": "percent", "percent": "5"})
    assert (error.code, set(error.fields)) == ("pricing.duplicate_code", {"code"})
    assert DiscountRule.objects.count() == 1 and no_events()


def test_an_edit_of_a_rule_changes_only_what_is_sent_and_drops_the_old_type_s_value():
    product = make_product("Shampoo", "SH-1")
    rule = make_rule("TEN", percent=Decimal("10"))
    row = run("pricing.rule.update", {"rule": "TEN", "rule_type": "fixed", "amount": 40, "applies_to": "product", "product": "SH-1"})
    assert (row.rule_type, row.percent, row.amount, row.applies_to, row.product_id) == ("fixed", None, 40, "product", product.id)
    assert events("pricing.rule.updated") == [{"id": str(rule.id)}]
    back = run("pricing.rule.update", {"id": str(rule.id), "applies_to": "all"})
    assert (back.applies_to, back.product_id) == ("all", None)
    run("pricing.rule.update", {"id": str(rule.id), "priority": 100})
    assert len(events("pricing.rule.updated")) == 2
    error = refused(InvalidPayload, "pricing.rule.update", {"id": str(rule.id), "percent": "5"})
    assert set(error.fields) == {"percent"}


def test_a_rule_is_deactivated_and_activated_again():
    rule = make_rule("TEN")
    assert run("pricing.rule.deactivate", {"rule": "ten"}).is_active is False
    assert refused(Conflict, "pricing.rule.deactivate", {"rule": "ten"}).code == "pricing.rule_already_inactive"
    assert run("pricing.rule.activate", {"rule": "TEN"}).is_active is True
    assert refused(Conflict, "pricing.rule.activate", {"rule": "TEN"}).code == "pricing.rule_already_active"
    assert events("pricing.rule.deactivated") == [{"id": str(rule.id)}]
    assert events("pricing.rule.activated") == [{"id": str(rule.id)}]
    refused(NotFound, "pricing.rule.deactivate", {"rule": "nothing"})


def test_a_rule_of_a_deleted_group_is_not_activated_again():
    group = make_group("VIP")
    rule = make_rule("VIP10", customer_group_id=group.id, is_active=False)
    group.delete()
    error = refused(Conflict, "pricing.rule.activate", {"id": str(rule.id)})
    assert error.code == "pricing.rule_group_deleted"
    rule.refresh_from_db()
    assert rule.is_active is False and no_events()
    # Taking the group off (or choosing another) lets it apply again.
    run("pricing.rule.update", {"id": str(rule.id), "customer_group_id": None})
    assert run("pricing.rule.activate", {"id": str(rule.id)}).is_active is True


# Reactions (F14): run as the platform


def react(name, payload):
    from live.context import system_context

    from .conftest import A

    op = get(name)
    return op(system_context(A), op.input.model_validate(payload))


def test_a_deleted_product_leaves_no_price_and_switches_its_rules_off_once():
    product = make_product("Shampoo", "SH-1")
    other = make_product("Gel", "GE")
    item = make_item(make_list("VIP"), product)
    make_item(make_list("GEN"), other)
    rule = make_rule("PROD", applies_to="product", product=product)
    answer = react("pricing.catalog.forget_product", {"id": str(product.id), "sku": "SH-1", "name": "Shampoo"})
    assert (answer.items, answer.rules, answer.lists) == (1, 1, 0)
    assert list(PriceItem.objects.values_list("product_id", flat=True)) == [other.id]
    rule.refresh_from_db()
    assert rule.is_active is False
    assert events("pricing.price_item.removed")[0]["id"] == str(item.id)
    assert events("pricing.rule.deactivated") == [{"id": str(rule.id)}]
    again = react("pricing.catalog.forget_product", {"id": str(product.id)})
    assert (again.items, again.rules) == (0, 0)


def test_a_deleted_category_switches_its_rules_off():
    category = make_category("Colour")
    rule = make_rule("CAT", applies_to="category", category=category)
    assert react("pricing.catalog.forget_category", {"id": str(category.id), "name": "Colour"}).rules == 1
    rule.refresh_from_db()
    assert rule.is_active is False


def test_a_deleted_group_leaves_its_lists_without_group_and_switches_its_rules_off():
    group_id = uuid.uuid7()
    price_list = make_list("VIP", customer_group_id=group_id)
    rule = make_rule("VIP", customer_group_id=group_id)
    answer = react("pricing.catalog.forget_group", {"id": str(group_id)})
    assert (answer.lists, answer.rules) == (1, 1)
    price_list.refresh_from_db()
    rule.refresh_from_db()
    assert (price_list.customer_group_id, rule.is_active, rule.customer_group_id) == (None, False, group_id)
    assert events("pricing.price_list.updated") == [{"id": str(price_list.id)}]


def test_a_renamed_service_is_renamed_in_its_prices_and_rules():
    haircut = make_service("Haircut")
    make_item(make_list("VIP"), None, service_id=haircut.id, service_name="Haircut")
    rule = make_rule("CUT", applies_to="service", service_id=haircut.id, service_name="Haircut")
    haircut.name = "Women's haircut"
    haircut.save()
    answer = react("pricing.catalog.refresh_service", {"id": str(haircut.id)})
    assert (answer.items, answer.rules) == (1, 1)
    assert PriceItem.objects.get().service_name == "Women's haircut"
    rule.refresh_from_db()
    assert rule.service_name == "Women's haircut"
    assert events("pricing.price_item.updated") == [{"service_id": str(haircut.id)}]
    assert events("pricing.rule.updated") == [{"id": str(rule.id)}]
    assert react("pricing.catalog.refresh_service", {"id": str(haircut.id)}).items == 0


def test_a_reaction_is_no_person_s():
    product = make_product()
    refused(PermissionDenied, "pricing.catalog.forget_product", {"id": str(product.id)})


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
    op = get("pricing.price_list.create")
    op(ctx_for("hub_admin", B), op.input.model_validate({"code": "VIP", "name": "VIP", "is_default": True}))
    assert received(on_b, stop_after=1) == [{"events": ["pricing.price_list.created", "pricing.price_list.default_changed"]}]
    assert received(on_a, timeout=0.3) == []
