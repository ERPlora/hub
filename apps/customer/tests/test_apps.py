"""The customer app declares its module metadata, its menu, its permissions, what each role gets and
its operations, every one usable by the assistant (``ai``)."""

from django.apps import apps
from django.utils import translation
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import registry

PERMISSIONS = [
    "customer.view",
    "customer.manage",
    "customer.configure",
    "customer.merge",
    "customer.export",
    "customer.delete",
    "customer.erase",
    "customer.record_activity",
]

#: Every operation of the app, with its permission. The two purchase commands are the system's only:
#: their permission is declared by no app, so only the system context (``*``) holds it, as the
#: product's ``internal`` commands.
OPERATIONS = {
    # queries
    "customer.customer.list": "customer.view",
    "customer.customer.detail": "customer.view",
    "customer.customer.stats": "customer.view",
    "customer.customer.by_phone": "customer.view",
    "customer.customer.export": "customer.export",
    "customer.group.list": "customer.view",
    "customer.tag.list": "customer.view",
    "customer.field.list": "customer.view",
    "customer.activity.list": "customer.view",
    "customer.purchase.list": "customer.view",
    "customer.purchase.divergences": "customer.view",
    "customer.consent.state": "customer.view",
    "customer.consent.history": "customer.view",
    "customer.order.customer": "customer.view",
    "customer.order.list": "customer.view",
    # commands
    "customer.customer.create": "customer.manage",
    "customer.customer.update": "customer.manage",
    "customer.customer.import": "customer.manage",
    "customer.customer.set_groups": "customer.manage",
    "customer.customer.set_tags": "customer.manage",
    "customer.customer.delete": "customer.delete",
    "customer.customer.merge": "customer.merge",
    "customer.customer.erase": "customer.erase",
    "customer.note.add": "customer.manage",
    "customer.activity.add": "customer.record_activity",
    "customer.consent.grant": "customer.manage",
    "customer.consent.withdraw": "customer.manage",
    "customer.order.link": "customer.manage",
    # health data (CUSTOMER-F32)
    "customer.health.detail": "customer.view",
    "customer.health.grant": "customer.manage",
    "customer.health.withdraw": "customer.manage",
    "customer.health.update": "customer.manage",
    "customer.group.create": "customer.configure",
    "customer.group.update": "customer.configure",
    "customer.group.delete": "customer.delete",
    "customer.tag.create": "customer.configure",
    "customer.tag.update": "customer.configure",
    "customer.tag.delete": "customer.delete",
    "customer.field.create": "customer.configure",
    "customer.field.update": "customer.configure",
    "customer.field.delete": "customer.configure",
    "customer.purchase.record": "customer.record_purchase",
    "customer.purchase.void": "customer.record_purchase",
    "customer.purchase.refund": "customer.record_purchase",
}
#: Commands the assistant confirms before running: erasing, deleting, merging, bulk and money.
HIGH_RISK = {
    "customer.customer.import",
    "customer.customer.delete",
    "customer.customer.merge",
    "customer.customer.erase",
    "customer.group.delete",
    "customer.tag.delete",
    "customer.field.delete",
    "customer.purchase.record",
    "customer.purchase.void",
    "customer.purchase.refund",
}
#: Open to API keys, as in the product's module.json.
EXPOSED = {"customer.order.list", "customer.consent.state"}
#: Health data (CUSTOMER-F32, GDPR art. 9): for the screen only, never a tool of the assistant.
SCREEN_ONLY = {
    "customer.health.detail",
    "customer.health.grant",
    "customer.health.withdraw",
    "customer.health.update",
}


def customer():
    return apps.get_app_config("customer")


def customer_operations():
    return {name: op for name, op in registry.items() if name.startswith("customer.")}


def test_customer_is_a_live_app_that_requires_nothing():
    config = customer()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.customer"
    assert config.requires == []


def test_customer_is_a_free_module_of_the_people_group():
    config = customer()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    assert config.icon == "ion:people-outline"
    with translation.override("en"):
        assert str(config.verbose_name) == "Customers"


def test_customer_is_listed_in_the_store_for_both_verticals():
    # Round 16 (PLAN §21): one line for the store, one paragraph, and the verticals it ships with.
    config = customer()
    with translation.override("en"):
        assert 0 < len(str(config.summary)) <= 120
        assert "\n" not in str(config.summary)
        assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert customer().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(customer().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_owner_and_admin_may_do_everything():
    config = customer()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS)


def test_the_manager_keeps_the_products_manager_rights():
    # Everything but deleting cards, groups and tags and erasing personal data (admin only).
    assert permissions_for_role([customer()], "hub_manager") == {
        "customer.view",
        "customer.manage",
        "customer.configure",
        "customer.merge",
        "customer.export",
        "customer.record_activity",
    }


def test_the_employee_works_the_counter_with_the_old_cashier_rights():
    # The old «cashier» role (view, add, change, link_order, add_note) is the employee's now:
    # search, attach, quick add, edit the sheet and record consent at the counter.
    assert permissions_for_role([customer()], "hub_employee") == {
        "customer.view",
        "customer.manage",
    }


def test_navigation_is_the_products_four_tabs_with_registered_icons():
    # The product's tabs: Customers, Groups, Tags and Fields, with the product's icons where the
    # shell registers them. Tags waits for its own (pricetags: UI-REQUESTS.md); until then, a
    # registered one.
    entries = customer().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    with translation.override("en"):
        assert [
            (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
        ] == [
            ("customers", "Customers", "/customer/customers", "ion:people-outline"),
            ("groups", "Groups", "/customer/groups", "ion:people-outline"),
            ("tags", "Tags", "/customer/tags", "ion:list-outline"),
            ("fields", "Fields", "/customer/fields", "ion:layers-outline"),
        ]


# Operations: the whole inventory, each with its permission and the assistant's contract


def test_every_operation_and_its_permission():
    assert {
        name: op.permission for name, op in customer_operations().items()
    } == OPERATIONS


def test_the_system_only_permission_is_declared_by_no_app():
    # Owner and admin get every declared permission: declaring it would let them record purchases.
    declared = {
        permission
        for config in apps.get_app_configs()
        for permission in getattr(config, "permissions", [])
    }
    assert "customer.record_purchase" not in declared


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in customer_operations().items():
        if name in SCREEN_ONLY:
            assert op.ai is None, name
            continue
        assert isinstance(op.ai, dict), name
        assert (
            isinstance(op.ai.get("description"), str) and len(op.ai["description"]) > 20
        ), name


def test_commands_declare_their_risk_and_queries_do_not():
    for name, op in customer_operations().items():
        if name in SCREEN_ONLY:
            continue
        if op.kind == "command":
            expected = "high" if name in HIGH_RISK else "normal"
            assert op.ai.get("risk") == expected, name
        elif name == "customer.customer.export":
            # The one query the assistant confirms: it hands out the whole directory's personal data.
            assert op.ai.get("risk") == "high"
        else:
            assert "risk" not in op.ai, name


def test_api_keys_reach_what_the_product_exposed():
    assert {
        name for name, op in customer_operations().items() if op.expose_api
    } == EXPOSED
