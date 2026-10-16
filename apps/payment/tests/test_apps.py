"""The payment app declares its module metadata, its menu, its permissions and what each role gets."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "payment.view_payment",
    "payment.add_payment",
    "payment.approve_payment",
]

COMMANDS = {
    "payment.method.create",
    "payment.method.update",
    "payment.method.deactivate",
    "payment.method.activate",
    "payment.payment.create",
    "payment.payment.approve",
    "payment.payment.mark_sent",
    "payment.payment.mark_completed",
    "payment.payment.cancel",
}
QUERIES = {
    "payment.payment.list",
    "payment.payment.get",
    "payment.method.list",
    "payment.method.get",
}
#: Approving, sending, completing and cancelling move a payment along: the assistant asks first.
HIGH_RISK = {
    "payment.payment.approve",
    "payment.payment.mark_sent",
    "payment.payment.mark_completed",
    "payment.payment.cancel",
}


def payment():
    return apps.get_app_config("payment")


def test_payment_is_a_live_app():
    config = payment()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.payment"
    assert config.label == "payment"


def test_payment_is_a_free_module_of_the_sales_group_with_a_registered_icon():
    config = payment()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.SALES
    assert config.premium is False
    # The old module's paper plane (`send`), registered in the shell as lucide:send.
    assert config.icon == "lucide:send"
    assert str(config.verbose_name) == "Payments"


def test_payment_requires_nothing():
    # Outgoing payments have nothing to do with the till's tenders (WORKBOOK «Decisión»).
    assert payment().requires == []


def test_payment_is_in_the_store_but_in_no_template():
    # The old catalogue retired it from the MVP: a business turns it on from the store; no vertical
    # brings it at sign-up (WORKBOOK «Antes de empezar»).
    config = payment()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == []
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert payment().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(payment().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = payment()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == {"payment.view_payment"}


def test_navigation_is_payments_and_methods_with_registered_icons():
    entries = payment().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("payments", "Payments", "lucide:send", "/payment/payments"),
        ("methods", "Methods", "ion:wallet-outline", "/payment/methods"),
    ]


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: every operation
    # says what it does and its risk.
    from live.operations import registry

    operations = {
        name: op for name, op in registry.items() if name.startswith("payment.")
    }
    assert set(operations) == COMMANDS | QUERIES
    for name, op in operations.items():
        assert op.kind == ("command" if name in COMMANDS else "query"), name
        assert set(op.ai) == {"description", "risk"}, name
        assert op.ai["description"], name
        assert op.ai["risk"] == ("high" if name in HIGH_RISK else "normal"), name
        assert op.expose_api is True, name


def test_every_input_field_says_what_it_is():
    # The assistant reads the JSON Schema of each input: a field without a description is a guess.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("payment."):
            continue
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}: {field}"
