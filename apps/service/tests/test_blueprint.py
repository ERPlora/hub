"""What of Services travels in an export of the business (BASE-F35) besides its categories and services: the vouchers
of its catalogue, each with its terms and its services by name, read with Services' own list and written with its own
create, so that loading the file brings them back as they were. The vouchers sold are what already happened: they never
travel.

Every test runs against the real apps, in business A's own database, as production does.
"""

import base64

from apps.service.tests.conftest import HUB_DB, in_business_a
from base import blueprint
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

TAX = "service.generic"

FIVE_CUTS = {"name": "Five cuts", "description": "For regulars", "discount_type": "fixed", "discount_amount": 500,
             "fixed_price": 9000, "validity_days": 365, "max_uses": 5, "is_featured": True, "sort_order": 1,
             "items": [{"service": "Haircut", "sessions": 5}]}  # fmt: skip
COLOUR_PACK = {"name": "Colour pack", "discount_type": "percentage", "discount_percent_bp": 1050,
               "items": [{"service": "Colour", "sessions": 2}, {"service": "Haircut", "sessions": 1}]}  # fmt: skip
TERMS = ("name", "description", "discount_type", "discount_percent_bp", "discount_amount", "fixed_price",
         "validity_days", "max_uses", "is_active", "is_featured", "sort_order")  # fmt: skip


def a_catalogue(ctx):
    call(ctx, "service.service.create", name="Haircut", price=2000, duration_minutes=30, tax_category_key=TAX)
    call(ctx, "service.service.create", name="Colour", price=4500, duration_minutes=60, tax_category_key=TAX)
    for voucher in (FIVE_CUTS, COLOUR_PACK):
        call(ctx, "service.package.create", **voucher)


def the_vouchers(ctx) -> list[tuple]:
    """The vouchers as the business reads them: their terms and their services by name, without ids."""
    return sorted(
        (*(getattr(row, name) for name in TERMS), tuple((item.service_name, item.sessions) for item in row.items))
        for row in call(ctx, "service.package.list", limit=100).rows
    )


def emptied(ctx) -> None:
    for row in call(ctx, "service.package.list", limit=100).rows:
        call(ctx, "service.package.delete", id=row.id)


def parts(report: dict) -> dict:
    return {part["key"]: (part["created"], part["already"], part["failed"]) for part in app_report(report, "service")["datasets"]}


def test_a_backup_brings_the_vouchers_back_with_their_terms_and_services(ctx):
    a_catalogue(ctx)
    before = the_vouchers(ctx)
    file = exported(ctx, ["service"])
    emptied(ctx)

    report = loaded_back(ctx, file)

    assert the_vouchers(ctx) == before
    assert parts(report)["service.package"] == (2, 0, 0)


def test_loading_the_file_again_duplicates_nothing(ctx):
    a_catalogue(ctx)
    file = exported(ctx, ["service"])

    report = loaded_back(ctx, file)

    assert parts(report)["service.package"] == (0, 2, 0)


def test_a_voucher_names_its_services_by_name_never_by_an_id_of_the_business_that_made_the_file(ctx):
    a_catalogue(ctx)

    vouchers = {row["name"]: row for row in data_of(ctx, ["service"])["service.package"]}

    assert vouchers["Colour pack"]["items"] == COLOUR_PACK["items"]


def test_a_voucher_of_a_service_the_business_does_not_have_is_told_and_the_others_load(ctx):
    a_catalogue(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx, ["service"]))
    colour_pack = next(row for row in bundle.data["service.package"] if row["name"] == "Colour pack")
    colour_pack["items"][0]["service"] = "Massage"
    emptied(ctx)

    report = loaded_back(ctx, base64.b64encode(blueprint.archive.write_zip(bundle)).decode())

    voucher = next(part for part in app_report(report, "service")["datasets"] if part["key"] == "service.package")
    assert (voucher["created"], voucher["failed"]) == (1, 1)
    assert voucher["problems"][0].startswith("«Colour pack»: ")
    assert [row[0] for row in the_vouchers(ctx)] == ["Five cuts"]
