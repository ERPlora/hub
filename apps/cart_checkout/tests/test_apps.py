"""The cart_checkout app declares its module metadata, its menu, its permissions, what each role gets,
its scheduled task and what the assistant sees of each operation."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "cart_checkout.view_cart",
    "cart_checkout.manage_cart",
    "cart_checkout.checkout",
]

COMMANDS = {
    "cart_checkout.cart.create",
    "cart_checkout.cart.mark_abandoned",
    "cart_checkout.cart.delete",
    "cart_checkout.cart.clear",
    "cart_checkout.cart.cleanup_expired",
    "cart_checkout.item.add",
    "cart_checkout.item.update",
    "cart_checkout.item.remove",
    "cart_checkout.checkout.initiate",
    "cart_checkout.order.mark_paid",
    "cart_checkout.order.fail",
    "cart_checkout.order.complete",
    "cart_checkout.customer.erase",
}
QUERIES = {
    "cart_checkout.cart.list",
    "cart_checkout.cart.get",
    "cart_checkout.item.list",
    "cart_checkout.item.get",
    "cart_checkout.order.list",
    "cart_checkout.order.get",
}
#: Marking paid, failing, deleting and erasing a customer's data: the assistant asks for a reinforced
#: confirmation first.
HIGH_RISK = {
    "cart_checkout.order.mark_paid",
    "cart_checkout.order.fail",
    "cart_checkout.cart.delete",
    "cart_checkout.customer.erase",
}
VIEW = "cart_checkout.view_cart"
MANAGE = "cart_checkout.manage_cart"
CHECKOUT = "cart_checkout.checkout"
PERMISSION_OF = {
    **{name: VIEW for name in QUERIES},
    "cart_checkout.cart.create": MANAGE,
    "cart_checkout.cart.mark_abandoned": MANAGE,
    "cart_checkout.cart.delete": MANAGE,
    "cart_checkout.cart.clear": MANAGE,
    "cart_checkout.cart.cleanup_expired": MANAGE,
    "cart_checkout.item.add": MANAGE,
    "cart_checkout.item.update": MANAGE,
    "cart_checkout.item.remove": MANAGE,
    "cart_checkout.checkout.initiate": CHECKOUT,
    "cart_checkout.order.mark_paid": CHECKOUT,
    "cart_checkout.order.fail": CHECKOUT,
    "cart_checkout.order.complete": CHECKOUT,
    "cart_checkout.customer.erase": MANAGE,
}


def cart_checkout():
    return apps.get_app_config("cart_checkout")


def operations():
    from live.operations import registry

    return {
        name: op for name, op in registry.items() if name.startswith("cart_checkout.")
    }


def test_cart_checkout_is_a_live_app():
    config = cart_checkout()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.cart_checkout"
    assert config.label == "cart_checkout"


def test_it_is_a_free_module_of_the_sales_group_with_a_registered_icon():
    config = cart_checkout()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.SALES
    assert config.premium is False
    # The old module's bag (`bag-check-outline` is not in the shell yet: UI-REQUESTS.md).
    assert config.icon == "lucide:shopping-bag"
    assert str(config.verbose_name) == "Cart & Checkout"


def test_it_requires_nothing():
    # Products, SKU and price are free text and the customer an email and a name, as in the old
    # module: no foreign key to inventory or customer (WORKBOOK «Decisión»).
    assert cart_checkout().requires == []


def test_it_is_in_the_store_but_in_no_template():
    # Out of the MVP: a business turns it on from the store; no vertical brings it at sign-up.
    config = cart_checkout()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert "not the till" in str(config.description).lower()
    assert config.verticals == []
    assert config.listed is True


def test_permissions_are_the_old_module_ones():
    assert cart_checkout().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(cart_checkout().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = cart_checkout()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == {VIEW}


def test_navigation_is_carts_and_orders_with_registered_icons():
    entries = cart_checkout().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("carts", "Carts", "lucide:shopping-bag", "/cart_checkout/carts"),
        ("orders", "Orders", "ion:receipt-outline", "/cart_checkout/orders"),
    ]


def test_the_overdue_carts_expire_every_quarter_of_an_hour():
    # CART_CHECKOUT-F07: the phase-2 worker runs it on every hub as the system (cron in UTC).
    assert cart_checkout().scheduled_tasks == [
        {
            "name": "expire_overdue_carts",
            "operation": "cart_checkout.cart.cleanup_expired",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]
    assert cart_checkout().scheduled_tasks[0]["operation"] in operations()


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: every operation
    # says what it does and its risk.
    ops = operations()
    assert set(ops) == COMMANDS | QUERIES
    for name, op in ops.items():
        assert op.kind == ("command" if name in COMMANDS else "query"), name
        assert op.permission == PERMISSION_OF[name], name
        assert set(op.ai) == {"description", "risk"}, name
        assert op.ai["description"], name
        assert op.ai["risk"] == ("high" if name in HIGH_RISK else "normal"), name
        assert op.expose_api is True, name


def test_the_assistant_hears_it_is_not_the_till():
    # The old module described itself as «mark payments»: the assistant could pick it to charge.
    ops = operations()
    for name in ("cart_checkout.order.mark_paid", "cart_checkout.checkout.initiate"):
        assert "not the till" in ops[name].ai["description"].lower(), name


def test_every_input_field_says_what_it_is():
    # The assistant reads the JSON Schema of each input: a field without a description is a guess.
    for name, op in operations().items():
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}: {field}"
