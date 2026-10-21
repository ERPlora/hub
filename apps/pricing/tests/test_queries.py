"""Read operations of the pricing app: the lists, a list, the prices, the rules, and the price of a line
(WORKBOOK PRICING-F01, F06, F09 and F13). Every resolution reads a fixed day: never the real clock."""

import datetime as dt
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from live.errors import Conflict, NotFound
from live.operations import get

from .conftest import (
    TODAY,
    categorize,
    ctx_for,
    make_category,
    make_customer,
    make_group,
    make_item,
    make_list,
    make_product,
    make_rule,
    make_service,
)

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")


def run(name, data=None, role="hub_admin"):
    op = get(name)
    return op(ctx_for(role), op.input.model_validate(data or {}))


def resolve(**data):
    data.setdefault("when", dt.datetime.combine(TODAY, dt.time(12), MADRID).isoformat())
    return run("pricing.price.resolve", data)


# Price lists (F01)


def test_the_lists_are_the_active_ones_by_name_with_their_group_and_how_many_prices():
    vip = make_group("VIP")
    general = make_list("GEN", "General", is_default=True)
    members = make_list("VIP", "VIP members", customer_group_id=vip.id, tax_included=True)
    make_list("OLD", "Old list", is_active=False)
    make_item(members, make_product("Shampoo", "S1"))
    make_item(members, make_product("Gel", "G1"))
    gone = make_product("Wax", "W1", is_deleted=True)
    make_item(members, gone)
    page = run("pricing.price_list.list")
    assert [(row.code, row.customer_group_name, row.item_count) for row in page.rows] == [
        ("GEN", None, 0),
        ("VIP", "VIP", 2),
    ]
    assert page.total == 2
    assert page.rows[0].is_default is True and page.rows[0].id == general.id
    assert page.rows[1].tax_included is True


def test_the_lists_are_searched_filtered_and_sorted():
    vip = make_group("VIP")
    make_list("VIP", "VIP members", customer_group_id=vip.id, tax_included=True)
    make_list("WHOLE", "Wholesale", currency="USD", tax_included=False)
    make_list("SUMMER", "Summer")
    make_list("OLD", "Old list", is_active=False)

    def codes(**params):
        return [row.code for row in run("pricing.price_list.list", params).rows]

    assert codes(search="whole") == ["WHOLE"]
    assert codes(search="vip") == ["VIP"]
    assert codes(currency="us") == ["WHOLE"]
    assert codes(customer_group_id=str(vip.id)) == ["VIP"]
    assert codes(tax_basis="included") == ["VIP"]
    assert codes(tax_basis="excluded") == ["WHOLE"]
    assert codes(tax_basis="business") == ["SUMMER"]
    assert codes(status="inactive") == ["OLD"]
    assert codes(status="all", sort="code", dir="desc") == ["WHOLE", "VIP", "SUMMER", "OLD"]
    assert codes(limit=1, offset=1) == ["VIP"]


def test_a_list_is_found_by_id_code_or_name():
    vip = make_list("VIP", "VIP members")
    make_list("VIPPLUS", "VIP plus")
    assert run("pricing.price_list.get", {"id": str(vip.id)}).code == "VIP"
    assert run("pricing.price_list.get", {"price_list": "vip"}).id == vip.id
    assert run("pricing.price_list.get", {"price_list": "vip members"}).id == vip.id
    with pytest.raises(Conflict) as caught:
        run("pricing.price_list.get", {"price_list": "vi"})
    assert caught.value.code == "pricing.ambiguous_price_list"
    with pytest.raises(NotFound) as missing:
        run("pricing.price_list.get", {"price_list": "nothing"})
    assert missing.value.code == "pricing.price_list_not_found"


def test_a_deleted_group_has_no_name_and_an_inactive_list_is_still_readable():
    group = make_group("Gone")
    group_id = group.id
    price_list = make_list("GONE", customer_group_id=group_id, is_active=False)
    group.delete()
    row = run("pricing.price_list.get", {"id": str(price_list.id)})
    assert (row.customer_group_id, row.customer_group_name, row.is_active) == (group_id, None, False)


def test_tied_lists_follow_the_list_s_direction_and_empty_values_stay_last():
    """hub#2355 (the old product's rule, 2026-09-28; Sales, Cash register, Inventory and Tasks follow it): ties on the
    sorted column come by code in the list's own direction, never always ascending; empty values go last both ways."""
    from apps.pricing.models import PriceList

    for code in ("A1", "B2", "C3"):
        make_list(code, "Same name")
    make_list("Z9", "Same name", tax_included=True)
    # Postgres writes a touched row's new version after the others: without a tie-break, A1 would come last.
    PriceList.objects.filter(code="A1").update(name="Same name")

    def codes(sort, direction, **page):
        return [row.code for row in run("pricing.price_list.list", {"sort": sort, "dir": direction, **page}).rows]

    for column in ("name", "currency", "customer_group_name"):
        assert codes(column, "asc") == ["A1", "B2", "C3", "Z9"], column
        assert codes(column, "desc") == ["Z9", "C3", "B2", "A1"], column
    # Only Z9 has a tax basis: the empty ones come after it both ways, their ties in the list's direction.
    assert codes("tax_included", "asc") == ["Z9", "A1", "B2", "C3"]
    assert codes("tax_included", "desc") == ["Z9", "C3", "B2", "A1"]
    paged = [code for offset in (0, 2) for code in codes("name", "desc", limit=2, offset=offset)]
    assert paged == ["Z9", "C3", "B2", "A1"]


# Prices (F06)


def test_the_prices_of_a_list_with_the_catalog_s_name_sku_unit_and_price():
    price_list = make_list("VIP")
    shampoo = make_product("Shampoo", "SH-1", price=1500)
    make_item(price_list, shampoo, price=1200)
    make_item(price_list, shampoo, price=1000, min_quantity="10")
    service_id = uuid.uuid7()
    make_item(price_list, None, price=1600, service_id=service_id, service_name="Haircut")
    make_item(make_list("OTHER"), shampoo, price=1100)
    make_item(price_list, make_product("Wax", "WX", is_deleted=True))
    page = run("pricing.price_item.list", {"price_list": "VIP"})
    assert [(row.name, row.kind, row.sku, row.unit, row.base_price, row.min_quantity, row.price) for row in page.rows] == [
        ("Haircut", "service", None, None, None, Decimal("1.000"), 1600),
        ("Shampoo", "product", "SH-1", "ud", 1500, Decimal("1.000"), 1200),
        ("Shampoo", "product", "SH-1", "ud", 1500, Decimal("10.000"), 1000),
    ]
    assert page.rows[1].price_list_code == "VIP"


def test_the_prices_are_searched_filtered_and_sorted_and_read_across_lists():
    price_list = make_list("VIP")
    shampoo = make_product("Shampoo", "SH-1")
    make_item(price_list, shampoo, price=1200)
    make_item(price_list, make_product("Gel", "GE-9"), price=800)
    make_item(price_list, None, price=1600, service_id=uuid.uuid7(), service_name="Haircut")
    make_item(make_list("OTHER"), shampoo, price=1100)

    def names(**params):
        return [row.name for row in run("pricing.price_item.list", {"price_list": "VIP", **params}).rows]

    assert names(search="ge-9") == ["Gel"]
    assert names(search="hair") == ["Haircut"]
    assert names(kind="service") == ["Haircut"]
    assert names(sort="price", dir="desc") == ["Haircut", "Shampoo", "Gel"]
    across = run("pricing.price_item.list", {"product_id": str(shampoo.id), "sort": "price"})
    assert [(row.price_list_code, row.price) for row in across.rows] == [("OTHER", 1100), ("VIP", 1200)]
    with pytest.raises(NotFound):
        run("pricing.price_item.list", {"price_list": "missing"})


def test_tied_prices_follow_the_list_s_direction():
    """hub#2355: prices tied on the sorted column come by their from quantity, then by id, in the list's own
    direction (two products with the same name and price, two breaks each)."""
    from apps.pricing.models import PriceItem

    price_list = make_list("VIP")
    first, second = make_product("Shampoo", "SH-1"), make_product("Shampoo", "SH-2")
    items = [
        make_item(price_list, product, price=1000, min_quantity=quantity)
        for quantity in ("1", "5")
        for product in (first, second)
    ]
    # Postgres writes a touched row's new version after the others: without a tie-break, it would come last.
    PriceItem.objects.filter(pk=items[0].pk).update(price=1000)
    expected = [item.id for item in sorted(items, key=lambda item: (item.min_quantity, item.id))]

    def ids(sort, direction, **page):
        params = {"price_list": "VIP", "sort": sort, "dir": direction, **page}
        return [row.id for row in run("pricing.price_item.list", params).rows]

    for column in ("name", "min_quantity", "price"):
        assert ids(column, "asc") == expected, column
        assert ids(column, "desc") == expected[::-1], column
    assert [row for offset in (0, 2) for row in ids("price", "desc", limit=2, offset=offset)] == expected[::-1]


# Rules (F09)


def test_the_rules_are_the_active_ones_with_the_names_of_what_they_apply_to():
    category = make_category("Colour")
    product = make_product("Shampoo", "SH-1")
    vip = make_group("VIP")
    make_rule("CAT", applies_to="category", category=category, name="Colour 10")
    make_rule("PROD", "fixed", amount=50, applies_to="product", product=product, name="Shampoo off")
    make_rule(
        "TIER",
        "tiered",
        tiers=[{"min_quantity": "3", "percent": "10"}, {"min_quantity": "6", "percent": "15"}],
        customer_group_id=vip.id,
        name="Volume",
    )
    make_rule("OFF", name="Old", is_active=False)
    rows = {row.code: row for row in run("pricing.rule.list").rows}
    assert set(rows) == {"CAT", "PROD", "TIER"}
    assert rows["CAT"].category_name == "Colour"
    assert (rows["PROD"].product_name, rows["PROD"].amount) == ("Shampoo", 50)
    assert rows["TIER"].customer_group_name == "VIP"
    assert [(tier.min_quantity, tier.percent) for tier in rows["TIER"].tiers] == [
        (Decimal("3"), Decimal("10")),
        (Decimal("6"), Decimal("15")),
    ]
    assert [row.code for row in run("pricing.rule.list", {"status": "inactive"}).rows] == ["OFF"]


def test_the_rules_are_searched_filtered_and_sorted():
    make_rule("A", name="Alpha", priority=5)
    make_rule("B", "fixed", amount=10, name="Beta", priority=1)
    make_rule("C", "buy_x_get_y", buy_quantity=2, get_quantity=1, name="Gamma", applies_to="services")
    make_rule("OFF", name="Omega", is_active=False)

    def codes(**params):
        return [row.code for row in run("pricing.rule.list", params).rows]

    # The active ones unless asked otherwise (PRICING-F09: «Activas» at opening, «Inactivas», or every one).
    assert codes() == ["A", "B", "C"]
    assert codes(status="inactive") == ["OFF"]
    assert codes(status="all") == ["A", "B", "C", "OFF"]
    assert codes(search="bet") == ["B"]
    assert codes(rule_type="buy_x_get_y") == ["C"]
    assert codes(applies_to="services") == ["C"]
    assert codes(sort="priority") == ["B", "A", "C"]


def test_tied_rules_follow_the_list_s_direction():
    """hub#2355: rules tied on the sorted column come by code in the list's own direction."""
    from apps.pricing.models import DiscountRule

    for code in ("A1", "B2", "C3"):
        make_rule(code, name="Same name")
    # Postgres writes a touched row's new version after the others: without a tie-break, A1 would come last.
    DiscountRule.objects.filter(code="A1").update(name="Same name")

    def codes(sort, direction, **page):
        return [row.code for row in run("pricing.rule.list", {"sort": sort, "dir": direction, **page}).rows]

    for column in ("name", "rule_type", "priority"):
        assert codes(column, "asc") == ["A1", "B2", "C3"], column
        assert codes(column, "desc") == ["C3", "B2", "A1"], column
    assert [code for offset in (0, 2) for code in codes("name", "desc", limit=2, offset=offset)] == ["C3", "B2", "A1"]


# The price of a line (F13): the lists


def test_without_lists_nor_rules_the_line_takes_the_catalog_s_price():
    product = make_product("Shampoo", "SH-1", price=1250)
    line = resolve(product_id=str(product.id), quantity="3")
    assert (line.kind, line.name, line.base_price, line.unit_price, line.price_list_id) == (
        "product",
        "Shampoo",
        1250,
        1250,
        None,
    )
    assert (line.line_amount, line.discount, line.total, line.rule_id, line.currency) == (3750, 0, 3750, None, "EUR")
    assert line.date == TODAY


def test_the_general_list_prices_a_sale_without_customer():
    product = make_product("Shampoo", "SH-1", price=1250)
    general = make_list("GEN", is_default=True, tax_included=True)
    make_item(general, product, price=1100)
    line = resolve(product="sh-1")
    assert (line.unit_price, line.price_list_id, line.price_list_code, line.tax_included) == (1100, general.id, "GEN", True)


def test_a_group_list_prices_only_its_members_and_the_lowest_price_wins():
    product = make_product("Shampoo", "SH-1", price=1250)
    vip, staff = make_group("VIP"), make_group("Staff")
    make_item(make_list("GEN", is_default=True), product, price=1100)
    make_item(make_list("VIP", customer_group_id=vip.id), product, price=1000)
    make_item(make_list("STAFF", customer_group_id=staff.id), product, price=900)
    make_item(make_list("MANUAL"), product, price=100)  # nobody's group and not general: only by name
    lucia = make_customer("Lucía Pérez", groups=[vip])
    both = make_customer("Ana Ruiz", groups=[vip, staff])
    nobody = make_customer("Bea Gil")
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).price_list_code == "VIP"
    assert resolve(product_id=str(product.id), customer_id=str(both.id)).price_list_code == "STAFF"
    assert resolve(product_id=str(product.id), customer_id=str(nobody.id)).price_list_code == "GEN"
    assert resolve(product_id=str(product.id), customer="Lucía Pérez").unit_price == 1000


def test_the_general_list_beats_a_group_list_when_it_is_lower():
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP")
    make_item(make_list("GEN", is_default=True), product, price=950)
    make_item(make_list("VIP", customer_group_id=vip.id), product, price=1000)
    lucia = make_customer(groups=[vip])
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).price_list_code == "GEN"


def test_an_inactive_group_or_list_gives_no_price():
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP", is_active=False)
    make_item(make_list("VIP", customer_group_id=vip.id), product, price=1000)
    make_item(make_list("OFF", is_active=False), product, price=500)
    lucia = make_customer(groups=[vip])
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).unit_price == 1250


def test_a_list_applies_between_its_days_read_in_the_business_s_zone():
    product = make_product("Shampoo", "SH-1", price=1250)
    summer = make_list("SUMMER", is_default=True, valid_from=dt.date(2026, 7, 15), valid_until=dt.date(2026, 8, 31))
    make_item(summer, product, price=999)
    # 23:30 UTC on the 14th is already the 15th in Madrid.
    assert resolve(product_id=str(product.id), when="2026-07-14T23:30:00+00:00").unit_price == 999
    assert resolve(product_id=str(product.id), when="2026-07-14T21:30:00+00:00").unit_price == 1250
    assert resolve(product_id=str(product.id), when="2026-08-31T21:59:00+00:00").unit_price == 999
    assert resolve(product_id=str(product.id), when="2026-08-31T22:00:00+00:00").unit_price == 1250


def test_without_a_moment_the_line_is_priced_on_the_business_s_today():
    product = make_product("Shampoo", "SH-1", price=1250)
    make_item(make_list("TODAY", is_default=True, valid_from=TODAY, valid_until=TODAY), product, price=777)
    line = run("pricing.price.resolve", {"product_id": str(product.id)})
    assert (line.unit_price, line.date) == (777, TODAY)


def test_the_highest_quantity_break_reached_wins_inside_a_list():
    product = make_product("Shampoo", "SH-1", price=1250)
    general = make_list("GEN", is_default=True)
    make_item(general, product, price=1100)
    make_item(general, product, price=900, min_quantity="10")
    make_item(general, product, price=800, min_quantity="50")
    assert resolve(product_id=str(product.id), quantity="9").unit_price == 1100
    assert resolve(product_id=str(product.id), quantity="10").unit_price == 900
    assert resolve(product_id=str(product.id), quantity="49").unit_price == 900
    assert resolve(product_id=str(product.id), quantity="50").unit_price == 800


def test_an_exact_tie_between_lists_goes_to_the_lower_code():
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_item(make_list("ZETA", is_default=True), product, price=1000)
    make_item(make_list("ALPHA", customer_group_id=vip.id), product, price=1000)
    make_item(make_list("beta", customer_group_id=vip.id), product, price=1000)
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).price_list_code == "ALPHA"


def test_breaks_of_two_lists_compete_only_once_reached():
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_item(make_list("GEN", is_default=True), product, price=1000)
    make_item(make_list("VIP", customer_group_id=vip.id), product, price=900, min_quantity="10")
    make_item(make_list("DEAR", customer_group_id=vip.id), product, price=1100, min_quantity="5")
    customer = str(lucia.id)
    assert resolve(product_id=str(product.id), customer_id=customer, quantity="9").price_list_code == "GEN"
    assert resolve(product_id=str(product.id), customer_id=customer, quantity="10").price_list_code == "VIP"
    # From 5 the dear list competes, and loses against the general one.
    assert resolve(product_id=str(product.id), customer_id=customer, quantity="5").price_list_code == "GEN"


def test_a_list_in_another_currency_applies_only_when_asked_for():
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_item(make_list("USD", currency="USD", customer_group_id=vip.id), product, price=100)
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).unit_price == 1250
    line = resolve(product_id=str(product.id), price_list="USD")
    assert (line.unit_price, line.currency) == (100, "USD")


def test_only_lists_of_the_sale_s_tax_basis_compete():
    # A general list with the tax in at 10.00 € must not lose against a B2B list without it at 9.00 €
    # (10.89 € with VAT): prices of different bases are never compared.
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_item(make_list("GEN", is_default=True, tax_included=True), product, price=1000)
    make_item(make_list("B2B", customer_group_id=vip.id, tax_included=False), product, price=900)
    make_item(make_list("ANY", customer_group_id=vip.id), product, price=1100)
    # A sale says whether its prices carry the tax; without saying it, they do (a till's prices do).
    included = resolve(product_id=str(product.id), customer_id=str(lucia.id))
    assert (included.price_list_code, included.unit_price, included.tax_included) == ("GEN", 1000, True)
    excluded = resolve(product_id=str(product.id), customer_id=str(lucia.id), tax_included=False)
    assert (excluded.price_list_code, excluded.unit_price, excluded.tax_included) == ("B2B", 900, False)
    # A list that follows the business competes in both.
    make_item(make_list("CHEAP", customer_group_id=vip.id), product, price=800)
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id), tax_included=False).price_list_code == "CHEAP"
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).price_list_code == "CHEAP"


def test_a_list_asked_for_by_name_is_the_only_one_and_must_apply_that_day():
    product = make_product("Shampoo", "SH-1", price=1250)
    make_item(make_list("GEN", is_default=True), product, price=900)
    make_item(make_list("MANUAL", "Trade fair"), product, price=1000)
    assert resolve(product_id=str(product.id), price_list="trade fair").unit_price == 1000
    make_list("EMPTY")
    assert resolve(product_id=str(product.id), price_list="EMPTY").unit_price == 1250
    make_list("LATER", valid_from=dt.date(2026, 9, 1))
    make_list("CLOSED", is_active=False)
    for code in ("LATER", "CLOSED"):
        with pytest.raises(Conflict) as caught:
            resolve(product_id=str(product.id), price_list=code)
        assert caught.value.code == "pricing.price_list_unavailable", code


def test_the_amount_follows_the_unit_the_price_is_for():
    by_weight = make_product("Coffee", "CF", price=2000, unit="g", pricing_unit="kg")
    by_hundred = make_product("Screws", "SC", price=37, price_quantity=Decimal("100"))
    assert resolve(product_id=str(by_weight.id), quantity="250").line_amount == 500
    assert resolve(product_id=str(by_hundred.id), quantity="150").line_amount == 56  # 55.5 → 56, half up


def test_a_deleted_or_unknown_product_is_not_priced():
    gone = make_product("Wax", "WX", is_deleted=True)
    with pytest.raises(NotFound):
        resolve(product_id=str(gone.id))
    with pytest.raises(NotFound):
        resolve(product="nothing like it")


# The price of a line (F13): the rules


def test_a_percent_rule_comes_off_the_list_s_price():
    product = make_product("Shampoo", "SH-1", price=1250)
    make_item(make_list("GEN", is_default=True), product, price=1000)
    rule = make_rule("TEN", percent=Decimal("12.5"))
    line = resolve(product_id=str(product.id), quantity="3")
    assert (line.line_amount, line.discount, line.total) == (3000, 375, 2625)
    assert (line.rule_id, line.rule_code, line.rule_name, line.rule_type) == (rule.id, "TEN", "Rule TEN", "percent")


def test_each_type_of_rule_and_the_best_single_one_wins():
    product = make_product("Shampoo", "SH-1", price=1000)
    make_rule("PCT", percent=Decimal("10"))  # 10 % of 5000 = 500
    make_rule("FIX", "fixed", amount=150)  # 150 × 5 = 750
    make_rule("BOGO", "buy_x_get_y", buy_quantity=2, get_quantity=1)  # 1 free of 5 = 1000
    make_rule("VOL", "tiered", tiers=[{"min_quantity": "3", "percent": "5"}, {"min_quantity": "5", "percent": "25"}])  # 1250
    line = resolve(product_id=str(product.id), quantity="5")
    assert (line.rule_code, line.discount, line.total) == ("VOL", 1250, 3750)
    assert resolve(product_id=str(product.id), quantity="2").rule_code == "FIX"  # 300 > 200 (10 %), 100 (5 %)


def test_rules_count_a_product_sold_by_weight_in_the_unit_of_its_price():
    # Coffee at 20 €/kg, sold in grams (market-decision 2026-10-15: Odoo, Business Central, Dynamics 365
    # Commerce): an amount per unit is per kg, buy 2 get 1 gives 1 kg of every 3 kg, a tier or a minimum
    # of 3 needs 3 kg. Never grams: 0,50 € off each of 250 grams would give the coffee away.
    coffee = make_product("Coffee", "CF", price=2000, unit="g", pricing_unit="kg")
    fixed = make_rule("FIX", "fixed", amount=50)
    line = resolve(product_id=str(coffee.id), quantity="250")
    assert (line.line_amount, line.discount, line.total) == (500, 13, 487)  # 0.25 kg × 0.50 € = 0.125 €
    fixed.is_active = False
    fixed.save()
    make_rule("BOGO", "buy_x_get_y", buy_quantity=2, get_quantity=1)
    assert resolve(product_id=str(coffee.id), quantity="3").rule_id is None
    line = resolve(product_id=str(coffee.id), quantity="3000")
    assert (line.rule_code, line.line_amount, line.discount) == ("BOGO", 6000, 2000)
    make_rule("VOL", "tiered", tiers=[{"min_quantity": "3", "percent": "40"}])
    assert resolve(product_id=str(coffee.id), quantity="2999").rule_code is None
    assert resolve(product_id=str(coffee.id), quantity="3000").rule_code == "VOL"  # 40 % = 2400 > 2000
    make_rule("MIN", percent=Decimal("50"), min_quantity=Decimal("3"))
    assert resolve(product_id=str(coffee.id), quantity="3").rule_id is None
    assert resolve(product_id=str(coffee.id), quantity="3000").rule_code == "MIN"


def test_rules_count_a_product_priced_per_hundred_in_its_own_units():
    # «0,37 € per 100 ud»: the unit of the price is still the unit, not the hundred.
    screws = make_product("Screws", "SC", price=37, price_quantity=Decimal("100"))
    make_rule("BOGO", "buy_x_get_y", buy_quantity=2, get_quantity=1)
    line = resolve(product_id=str(screws.id), quantity="300")
    assert (line.line_amount, line.discount) == (111, 37)  # 100 of 300 free


def test_a_tie_goes_to_the_lower_priority_then_the_lower_code():
    product = make_product("Shampoo", "SH-1", price=1000)
    make_rule("B", percent=Decimal("10"), priority=50)
    make_rule("A", percent=Decimal("10"), priority=50)
    make_rule("C", percent=Decimal("10"), priority=10)
    assert resolve(product_id=str(product.id)).rule_code == "C"


def test_a_discount_never_goes_below_zero():
    product = make_product("Gum", "GU", price=100)
    make_rule("BIG", "fixed", amount=500)
    line = resolve(product_id=str(product.id), quantity="2")
    assert (line.discount, line.total) == (200, 0)


def test_the_rules_obey_their_scope_group_quantity_and_days():
    category = make_category("Colour")
    product = make_product("Dye", "DY", price=1000)
    other = make_product("Gel", "GE", price=1000)
    categorize(product, category)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_rule("SERV", percent=Decimal("50"), applies_to="services")
    make_rule("OTHER", percent=Decimal("40"), applies_to="product", product=other)
    make_rule("CAT", percent=Decimal("5"), applies_to="category", category=category)
    make_rule("VIP", percent=Decimal("30"), customer_group_id=vip.id)
    make_rule("BULK", percent=Decimal("20"), min_quantity=Decimal("10"))
    make_rule("SOON", percent=Decimal("60"), valid_from=dt.date(2026, 8, 1))
    make_rule("OFF", percent=Decimal("70"), is_active=False)
    assert resolve(product_id=str(product.id)).rule_code == "CAT"
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).rule_code == "VIP"
    assert resolve(product_id=str(product.id), quantity="10").rule_code == "BULK"
    assert resolve(product_id=str(other.id)).rule_code == "OTHER"


def test_a_rule_applies_between_its_days_read_in_the_business_s_zone():
    product = make_product("Dye", "DY", price=1000)
    make_rule("JULY", percent=Decimal("10"), valid_from=dt.date(2026, 7, 15), valid_until=dt.date(2026, 7, 31))
    # 23:30 UTC on the 14th is already the 15th in Madrid (UTC+2 in summer); 21:59 UTC on the 31st is
    # still the 31st, 22:00 UTC is already the 1st of August.
    assert resolve(product_id=str(product.id), when="2026-07-14T21:59:59+00:00").rule_code is None
    assert resolve(product_id=str(product.id), when="2026-07-14T22:00:00+00:00").rule_code == "JULY"
    assert resolve(product_id=str(product.id), when="2026-07-31T21:59:59+00:00").rule_code == "JULY"
    assert resolve(product_id=str(product.id), when="2026-07-31T22:00:00+00:00").rule_code is None


def test_a_deleted_group_gives_its_rules_to_nobody():
    product = make_product("Dye", "DY", price=1000)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_rule("VIP", percent=Decimal("30"), customer_group_id=vip.id)
    vip.delete()
    assert resolve(product_id=str(product.id), customer_id=str(lucia.id)).rule_id is None


# The price of a line (F13): services, read through Services' own operation


def test_a_service_takes_its_list_price_and_the_rules_of_services():
    haircut = make_service("Haircut", price=1800)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_item(make_list("VIP", customer_group_id=vip.id), None, price=1500, service_id=haircut.id, service_name="Haircut")
    make_rule("PRODUCTS", percent=Decimal("50"), applies_to="products")
    make_rule("SALON", percent=Decimal("10"), applies_to="service", service_id=haircut.id, service_name="Haircut")
    line = resolve(service="Haircut", customer_id=str(lucia.id))
    assert (line.kind, line.service_id, line.name, line.base_price, line.unit_price) == (
        "service",
        haircut.id,
        "Haircut",
        1800,
        1500,
    )
    assert (line.rule_code, line.discount, line.total) == ("SALON", 150, 1350)
    assert resolve(service_id=str(haircut.id)).unit_price == 1800


def test_the_employee_asks_for_prices_and_a_caller_without_the_permission_does_not():
    product = make_product("Shampoo", "SH-1", price=1250)
    op = get("pricing.price.resolve")
    data = op.input.model_validate({"product_id": str(product.id), "when": "2026-07-15T10:00:00+02:00"})
    assert op(ctx_for("hub_employee"), data).unit_price == 1250
    from live.errors import PermissionDenied

    with pytest.raises(PermissionDenied):
        op(ctx_for(permissions=set()), data)
