"""What of Customers travels in an export of the business (BASE-F35) besides the customers: its active groups, tags
and custom fields, read with Customers' own lists and written with its own creates, so that loading the file brings
them back as they were.

Every test runs against the real apps, in business A's own database, as production does.
"""

from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

from apps.customer.tests.conftest import HUB_DB, in_business_a

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

GROUP = {"name": "VIP", "description": "Our best", "color": "#AA0000", "sort_order": 1}
TAG = {"name": "Allergic", "color": "#00AA00"}
FIELD = {"name": "Shoe size", "field_type": "select", "options": ["38", "39"], "is_required": False, "sort_order": 2}
LISTS = {"customer.group": ("customer.group.list", GROUP), "customer.tag": ("customer.tag.list", TAG),
         "customer.field": ("customer.field.list", FIELD)}  # fmt: skip


def a_catalogue(ctx):
    call(ctx, "customer.group.create", **GROUP)
    call(ctx, "customer.tag.create", **TAG)
    call(ctx, "customer.field.create", **FIELD)


def the_catalogue(ctx) -> dict:
    return {
        key: sorted(tuple(str(getattr(row, name)) for name in shape) for row in call(ctx, operation, limit=100).rows)
        for key, (operation, shape) in LISTS.items()
    }


def test_a_backup_brings_the_groups_tags_and_custom_fields_back(ctx):
    a_catalogue(ctx)
    before = the_catalogue(ctx)
    file = exported(ctx, ["customer"])
    for key, (operation, _) in LISTS.items():
        for row in call(ctx, operation, limit=100).rows:
            call(ctx, f"{key}.delete", id=row.id)

    report = loaded_back(ctx, file)

    assert the_catalogue(ctx) == before
    created = {part["key"]: part["created"] for part in app_report(report, "customer")["datasets"]}
    assert {key: created[key] for key in LISTS} == {"customer.group": 1, "customer.tag": 1, "customer.field": 1}


def test_loading_the_file_again_duplicates_nothing(ctx):
    a_catalogue(ctx)

    report = loaded_back(ctx, exported(ctx, ["customer"]))

    assert {part["key"]: part["already"] for part in app_report(report, "customer")["datasets"] if part["key"] in LISTS} == {
        "customer.group": 1, "customer.tag": 1, "customer.field": 1,
    }  # fmt: skip


def test_the_catalogue_travels_in_a_template_too(ctx):
    a_catalogue(ctx)

    assert set(LISTS) <= set(data_of(ctx, ["customer"], purpose="template"))
