"""The burger the till and the kitchen tests sell, dressed by Modifiers' own operations: its «Extras» (cheese
+1,00 € «+CHEESE», no onion free «-ONION», a soda of +2,00 € taxed at 21 % on a line of its own; up to four, repeats
allowed) and its «Doneness», required, one of rare and well done (no kitchen name: the cook reads its name)."""

GENERIC = "product.generic"

OPTIONS = {
    "cheese": {"group": "Extras", "name": "Cheese", "kitchen_name": "+CHEESE", "price_delta": 100},
    "onion": {"group": "Extras", "name": "No onion", "kitchen_name": "-ONION", "price_delta": 0},
    "soda": {"group": "Extras", "name": "Soda", "price_delta": 200, "tax_category_key": GENERIC},
    "rare": {"group": "Doneness", "name": "Rare", "price_delta": 0},
    "done": {"group": "Doneness", "name": "Well done", "price_delta": 0},
}


def dress(setup, dish) -> dict[str, str]:
    """Hangs both groups from ``dish``, each operation run by ``setup(name, data)``; the id of each option by its key."""
    setup("modifier.group.create", {"name": "Extras", "max_choices": 4, "allow_repeat": True})
    setup("modifier.group.create", {"name": "Doneness", "min_choices": 1, "max_choices": 1})
    options = {key: str(setup("modifier.option.create", data).id) for key, data in OPTIONS.items()}
    for group in ("Extras", "Doneness"):
        setup("modifier.link.attach", {"group": group, "product_id": str(dish.id)})
    return options
