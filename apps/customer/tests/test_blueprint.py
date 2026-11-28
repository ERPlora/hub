"""What of Customers travels in an export of the business (BASE-F35) besides the customers: its active groups, tags
and custom fields, read with Customers' own lists and written with its own creates, so that loading the file brings
them back as they were; and, in a backup only, what each card keeps in those custom fields, which comes back with the
card.

Every test runs against the real apps, in business A's own database, as production does.
"""

import base64

from apps.customer.tests.conftest import HUB_DB, in_business_a
from base import blueprint
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

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


def cards_with_values(ctx):
    a_catalogue(ctx)
    call(ctx, "customer.field.create", name="Allergies", field_type="text")
    fields = {row.name: str(row.id) for row in call(ctx, "customer.field.list", limit=100).rows}
    lucia = call(ctx, "customer.customer.create", name="Lucía Pérez", phone="+34600111222")
    call(ctx, "customer.customer.update", id=lucia.id, field_values=[
        {"field_id": fields["Shoe size"], "value": "38"}, {"field_id": fields["Allergies"], "value": "Nuts"},
    ])  # fmt: skip
    ana = call(ctx, "customer.customer.create", name="Ana García", email="ana@example.com")
    call(ctx, "customer.customer.update", id=ana.id, field_values=[{"field_id": fields["Allergies"], "value": "None"}])


def the_values(ctx) -> list[tuple[str, str, str]]:
    """What each card keeps in its custom fields, as its card reads it."""
    return sorted(
        (card.name, field.name, field.value)
        for row in call(ctx, "customer.customer.list", limit=100).rows
        for card in [call(ctx, "customer.customer.detail", id=row.id)]
        for field in card.custom_fields
        if field.value
    )


def no_cards_nor_fields(ctx) -> None:
    for row in call(ctx, "customer.customer.list", limit=100).rows:
        call(ctx, "customer.customer.delete", id=row.id)
    for row in call(ctx, "customer.field.list", limit=100).rows:
        call(ctx, "customer.field.delete", id=row.id)


def values_part(report: dict) -> dict:
    return next(part for part in app_report(report, "customer")["datasets"] if part["key"] == "customer.field_value")


def test_a_backup_brings_what_each_card_keeps_in_its_custom_fields_back_with_the_card(ctx):
    cards_with_values(ctx)
    before = the_values(ctx)
    file = exported(ctx, ["customer"])
    no_cards_nor_fields(ctx)

    report = loaded_back(ctx, file)

    assert the_values(ctx) == before
    assert (values_part(report)["created"], values_part(report)["already"]) == (3, 0)


def test_loading_the_backup_again_duplicates_no_value(ctx):
    cards_with_values(ctx)

    report = loaded_back(ctx, exported(ctx, ["customer"]))

    assert (values_part(report)["created"], values_part(report)["already"]) == (0, 3)


def test_the_cards_values_never_travel_in_a_template(ctx):
    cards_with_values(ctx)

    assert "customer.field_value" in data_of(ctx, ["customer"])
    assert "customer.field_value" not in data_of(ctx, ["customer"], purpose="template")


def test_a_value_of_a_field_the_business_does_not_have_is_told_and_the_others_load(ctx):
    cards_with_values(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx, ["customer"]))
    shoe = next(row for row in bundle.data["customer.field_value"] if row["field"] == "Shoe size")
    shoe["field"] = "Hat size"
    no_cards_nor_fields(ctx)

    report = loaded_back(ctx, base64.b64encode(blueprint.archive.write_zip(bundle)).decode())

    assert (values_part(report)["created"], values_part(report)["failed"]) == (2, 1)
    assert values_part(report)["problems"][0].startswith("«Lucía Pérez»: ")
    assert the_values(ctx) == [("Ana García", "Allergies", "None"), ("Lucía Pérez", "Allergies", "Nuts")]
