"""Writes of the discount rules (WORKBOOK PRICING-F10 to F12): create, edit, deactivate and activate one. A refusal
writes nothing and records no event."""

from decimal import Decimal

from live.errors import Conflict, InvalidPayload, NotFound

from apps.pricing.models import DiscountRule

from .conftest import HUB_DB, make_category, make_group, make_product, make_rule, make_service
from .test_services import events, no_events, refused, run

pytestmark = HUB_DB


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
