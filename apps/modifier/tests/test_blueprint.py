"""What of Modifiers travels in an export of the business, a backup or a template (BASE-F35): every group with its
options and the products and categories it applies to, read with Modifiers' own lists and written with its own
creates, so that loading the file brings the groups back as they were.

Every test runs against the real apps (Modifiers, Inventory, Taxes), in business A's own database, as production does.
"""

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext
from live.operations import get

from apps.modifier.tests.conftest import FOOD, GENERIC, HUB_DB, in_business_a
from base import blueprint
from base.models import Membership
from base.permissions import access_for
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B

__all__ = ["in_business_a"]
pytestmark = HUB_DB

DONENESS = {
    "name": "Doneness",
    "kitchen_name": "POINT",
    "min_choices": 1,
    "max_choices": 1,
    "allow_repeat": False,
    "sort_order": 1,
}
EXTRAS = {"name": "Extras", "kitchen_name": "", "min_choices": 0, "max_choices": 3, "allow_repeat": True, "sort_order": 2}


def owner_of(scope, username):
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host=scope.key, role=Membership.Role.OWNER)
    return OperationContext(scope=scope, actor=user, permissions=access_for(user, scope), language="en")


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def call(ctx, operation, /, **data):
    op = get(operation)
    return op(ctx, op.input(**data))


def a_menu(ctx):
    """A burger with its doneness asked, and extras for every burger of the category."""
    call(ctx, "inventory.category.create", name="Burgers")
    call(ctx, "inventory.product.create", name="Smash", sku="SMA", price=900, tax_category_key=FOOD)
    call(ctx, "modifier.group.create", **DONENESS)
    call(ctx, "modifier.option.create", group="Doneness", name="Rare", kitchen_name="RARE", price_delta=0,
         is_default=True, sort_order=1)
    call(ctx, "modifier.option.create", group="Doneness", name="Well done", price_delta=0, sort_order=2)
    call(ctx, "modifier.group.create", **EXTRAS)
    call(ctx, "modifier.option.create", group="Extras", name="Cheese", price_delta=150, allergens=["milk"],
         tax_category_key=GENERIC)
    call(ctx, "modifier.link.attach", group="Doneness", product="SMA")
    call(ctx, "modifier.link.attach", group="Extras", category="Burgers")


def the_groups(ctx) -> dict:
    """Every group as the business reads it: its rule, its options and what it applies to, without ids or dates."""
    groups = {}
    for row in call(ctx, "modifier.group.list", limit=100).rows:
        groups[row.name] = {name: getattr(row, name) for name in DONENESS} | {"options": [], "applies_to": []}
    for row in call(ctx, "modifier.option.list", limit=100).rows:
        groups[row.group_name]["options"].append(
            (row.name, row.kitchen_name, row.price_delta, row.tax_category_key, row.allergens, row.is_default,
             row.sort_order)
        )
    for row in call(ctx, "modifier.link.list", limit=100).rows:
        groups[row.group_name]["applies_to"].append(row.product_sku or row.category_name)
    return groups


def exported(ctx, *, purpose="backup") -> str:
    """The file Settings › Data › Export gives with Inventory and Modifiers marked with their data, in base64."""
    return call(ctx, "base.blueprint.export", name="Bar Olga", language="en", purpose=purpose,
                apps=["inventory", "modifier"], data=["inventory", "modifier"]).content_base64


def report_of(report: dict, app: str) -> dict:
    return next(row for row in report["apps"] if row["id"] == app)


def test_a_backup_brings_the_groups_back_with_their_options_and_what_they_apply_to(ctx):
    a_menu(ctx)
    before = the_groups(ctx)
    file = exported(ctx)
    for name in before:
        call(ctx, "modifier.group.delete", group=name)

    load = call(ctx, "base.blueprint.import", file_base64=file)

    assert the_groups(ctx) == before
    modifiers = report_of(load.model_dump()["report"], "modifier")
    assert modifiers["status"] == "applied"
    assert [(part["key"], part["created"]) for part in modifiers["datasets"]] == [("modifier.group", 2)]


def test_the_file_carries_each_group_with_its_options_and_the_products_by_their_code(ctx):
    a_menu(ctx)

    data = blueprint.archive.read_base64(exported(ctx)).data

    doneness, extras = data["modifier.group"]
    assert {name: doneness[name] for name in DONENESS} == DONENESS
    assert [option["name"] for option in doneness["options"]] == ["Rare", "Well done"]
    assert (doneness["products"], doneness["categories"]) == (["SMA"], [])
    assert (extras["products"], extras["categories"]) == ([], ["Burgers"])
    [cheese] = extras["options"]
    assert (cheese["price_delta"], cheese["allergens"], cheese["tax_category_key"]) == (150, ["milk"], GENERIC)


def test_a_template_carries_the_groups_too_they_are_no_personal_data(ctx):
    a_menu(ctx)

    data = blueprint.archive.read_base64(exported(ctx, purpose="template")).data

    assert [group["name"] for group in data["modifier.group"]] == ["Doneness", "Extras"]


def test_loading_the_backup_again_duplicates_nothing_and_says_it_was_already_there(ctx):
    a_menu(ctx)
    before = the_groups(ctx)

    load = call(ctx, "base.blueprint.import", file_base64=exported(ctx))

    assert the_groups(ctx) == before
    [groups] = report_of(load.model_dump()["report"], "modifier")["datasets"]
    assert (groups["status"], groups["already"], groups["created"]) == ("already", 2, 0)


def test_a_group_whose_product_is_not_in_the_business_loads_without_it_and_says_so(ctx):
    rows = [{**EXTRAS, "options": [], "products": ["GONE-1"], "categories": []}]
    bundle = blueprint.archive.Bundle(
        manifest=blueprint.archive.manifest(name="Bar", language="en", country="ES", purpose="backup",
                                            created_at="2026-11-26T10:00:00+00:00", vertical="", apps=["modifier"]),
        data={"modifier.group": rows},
    )

    result = blueprint.loading.apply(ctx, bundle, apps=None)

    assert list(the_groups(ctx)) == ["Extras"]
    assert the_groups(ctx)["Extras"]["applies_to"] == []
    [groups] = report_of(result.report, "modifier")["datasets"]
    assert groups["status"] == "partial"
    assert any("GONE-1" in problem for problem in groups["problems"])


def test_undoing_the_load_removes_the_groups_it_made_with_their_options(ctx):
    a_menu(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx))
    for name in the_groups(ctx):
        call(ctx, "modifier.group.delete", group=name)
    result = blueprint.loading.apply(ctx, bundle, apps=None)
    assert len(result.created["modifier.group"]) == 2

    blueprint.removal.undo(ctx, result.created)

    assert the_groups(ctx) == {}
    assert call(ctx, "modifier.option.list", limit=1).total == 0


def test_settings_data_lists_the_groups_as_what_modifiers_lets_travel(ctx):
    a_menu(ctx)

    apps = {app.id: app for app in call(ctx, "base.dataset.list").apps}

    [groups] = apps["modifier"].datasets
    assert (groups.key, groups.label, groups.rows, groups.personal) == ("modifier.group", "Modifier groups", 2, False)


def test_the_groups_load_after_the_products_and_categories_they_name(ctx):
    order = [dataset.key for dataset in blueprint.datasets.every_dataset()]

    assert order.index("inventory.category") < order.index("modifier.group")
    assert order.index("inventory.product") < order.index("modifier.group")


def test_resetting_modifiers_removes_every_group_and_nothing_of_inventory(ctx):
    a_menu(ctx)

    [section] = [app for app in blueprint.removal.reset_plan(ctx) if app["id"] == "modifier"]
    blueprint.removal.reset(ctx, ["modifier"])

    assert section["rows"] == 2
    assert the_groups(ctx) == {}
    assert call(ctx, "inventory.product.list", limit=1).total == 1


def test_a_backup_of_business_b_carries_its_groups_and_none_of_business_a_s(ctx, hub_b):
    a_menu(ctx)
    with use_hub(hub_b):
        theirs = owner_of(B, "bea")
        call(theirs, "modifier.group.create", name="Salsas")

        data = blueprint.archive.read_base64(exported(theirs)).data

    assert [group["name"] for group in data["modifier.group"]] == ["Salsas"]
