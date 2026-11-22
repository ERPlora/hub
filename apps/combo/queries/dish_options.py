"""What the options of Modifiers chosen for a dish of a menu do to the menu's line (SALE-F42).

Sales hands each dish's options already valued by Modifiers, and Menus does not ask Modifiers again. Their price adds to
the menu's amount once per pick of their dish. To take away (COMBO-F09) an option of its dish's category goes with the
dish and weighs with it; one of another category weighs its own price and gets its own part of the amount, at the
category its line is billed at. Eaten in, the menu is one line and the options go inside it.
"""

from dataclasses import dataclass

from apps.combo.schemas.dish_options import DishOptionIn

#: To take away, the category of what is served on the premises becomes the one of a sale of goods: a
#: beer drunk at the table is a hospitality service at 10 % (art. 91.Uno.2.2 LIVA), the same beer to take
#: away a sale of goods at 21 % (art. 90). Explicit on purpose: only Taxes' factory pair is mapped; a
#: category of the business's own is billed as it is.
TAKEAWAY_CATEGORY = {"restaurant.alcohol": "retail.alcohol"}


def takeaway_key(key: str | None, targets: frozenset[str]) -> str | None:
    """The category ``key`` is billed at to take away, while Taxes has it active; ``None`` when it has none."""
    if key in TAKEAWAY_CATEGORY:
        target = TAKEAWAY_CATEGORY[key]
        return target if target in targets else None
    return key


@dataclass(frozen=True)
class Dish:
    """A dish picked in a menu as the split reads it: the category it is billed at, its catalogue price, its picks in one
    menu and its options, each with the category its own line is billed at (``None`` for one that goes with the dish)."""

    key: str | None
    catalog_price: int
    quantity: int
    options: list[DishOptionIn]
    option_keys: list[str | None]


def _own(dish: Dish) -> list[tuple[DishOptionIn, str | None]]:
    return [(option, key) for option, key in zip(dish.options, dish.option_keys, strict=True) if option.own_line]


def options_amount(picks: dict, options: dict) -> int:
    """What the options add to one menu, in cents: those of each dish (``options`` by choice), once per pick of it."""
    return sum(quantity * sum(option.price_delta for option in options.get(choice, [])) for choice, quantity in picks.items())


def categories(dishes: list[Dish]) -> set[str | None]:
    """The categories the lines of a split would go to: each dish's, and each option's of a line of its own."""
    return {dish.key for dish in dishes} | {key for dish in dishes for _option, key in _own(dish)}


def weights(dishes: list[Dish]) -> list[int]:
    """The weights of the split: per dish, its catalogue price plus the options that go with it and, right after it, the
    price of each option of a line of its own; each by the dish's picks in one menu."""
    shares = []
    for dish in dishes:
        folded = sum(option.price_delta for option in dish.options if not option.own_line)
        shares.append((dish.catalog_price + folded) * dish.quantity)
        shares += [option.price_delta * dish.quantity for option, _key in _own(dish)]
    return shares


def priced(dishes: list[Dish], shares: list[int] | None) -> list[dict]:
    """Per dish, its category, its part of the amount and its options, the parts read in the order of ``weights``; no
    part without a split, and the options then go inside their dish's line."""
    parts = iter(shares or [])
    rows = []
    for dish in dishes:
        amount = next(parts) if shares else None
        options = []
        for option, key in zip(dish.options, dish.option_keys, strict=True):
            own = bool(shares) and option.own_line
            row = {"line_tax_category_key": key if own else None, "amount": next(parts) if own else None}
            options.append(option.model_dump() | row)
        rows.append({"tax_category_key": dish.key, "amount": amount, "options": options})
    return rows
