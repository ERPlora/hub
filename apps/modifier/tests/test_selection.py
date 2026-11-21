"""The valuation of the options chosen for a product gives each pick with its allergens (MODIFIER-F11), the ones that
go on a line of their own included: what the till adds up on the line (MODIFIER-F12). The rest of the valuation, its
prices, lines and refusals (MODIFIER-F07, F08), is tested in ``test_queries.py``."""

from .conftest import GENERIC, HUB_DB, make_product, run

pytestmark = HUB_DB


def test_the_valuation_of_the_picks_gives_each_ones_allergens_own_line_included():
    run("modifier.group.create", {"name": "Extras"})
    burger = make_product()
    run("modifier.link.attach", {"group": "Extras", "product_id": str(burger.id)})
    chosen = [
        run("modifier.option.create", {"group": "Extras", "name": name, **fields}).id
        for name, fields in (
            ("Cheese", {"allergens": ["milk"]}),
            ("Wine sauce", {"price_delta": 150, "tax_category_key": GENERIC, "allergens": ["sulphites"]}),
            ("Rare", {}),
        )
    ]

    valued = run(
        "modifier.selection.resolve",
        {"product_id": str(burger.id), "option_ids": [str(one) for one in chosen]},
        role="hub_employee",
    )

    assert [(pick.name, pick.own_line, pick.allergens) for pick in valued.picks] == [
        ("Cheese", False, ["milk"]), ("Wine sauce", True, ["sulphites"]), ("Rare", False, [])
    ]
