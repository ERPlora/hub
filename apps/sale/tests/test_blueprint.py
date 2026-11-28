"""What of Sales travels in an export of the business (BASE-F35): the departments of the open price with the tax
category each charges at and the quick notes of a line, read with Sales' own lists and written with its own creates.
The checks, the sales, the refunds, the day's numbers and the payment methods, which are the till's settings, never
travel.

Every test runs against the real apps (Sales, Taxes, Customers), in business A's own database, as production does.
"""

import pytest

from apps.sale.tests.conftest import HUB_DB, in_business_a
from base.tenancy.tests.business import A
from base.tests.blueprint_round_trip import app_report, call, data_of, loaded_back, owner_of
from base.tests.blueprint_round_trip import exported as exported_apps

__all__ = ["in_business_a"]
pytestmark = HUB_DB

FRUIT = {"name": "Fruit", "tax_category_key": "restaurant.food", "sort_order": 1}
NO_SALT = {"text": "No salt", "sort_order": 1}
BIZUM = {"name": "Bizum", "type": "transfer", "sort_order": 40}


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def a_till(ctx):
    call(ctx, "sale.department.create", **FRUIT)
    call(ctx, "sale.quick_note.create", **NO_SALT)
    call(ctx, "sale.payment_method.create", **BIZUM)


def the_till(ctx) -> dict:
    return {
        "departments": sorted((row.name, row.tax_category_key, row.sort_order) for row in call(ctx, "sale.department.list", limit=100).rows),
        "notes": sorted((row.text, row.sort_order) for row in call(ctx, "sale.quick_note.list", limit=100).rows),
        "methods": sorted((row.name, row.type, row.sort_order) for row in call(ctx, "sale.payment_method.list", limit=100).rows),
    }  # fmt: skip


def created(report: dict) -> dict:
    return {part["key"]: (part["created"], part["already"]) for part in app_report(report, "sale")["datasets"]}


def test_a_backup_brings_the_departments_and_quick_notes_back(ctx):
    a_till(ctx)
    before = the_till(ctx)
    file = exported_apps(ctx, ["sale"])
    for row in call(ctx, "sale.department.list", limit=100).rows:
        call(ctx, "sale.department.delete", id=row.id)
    for row in call(ctx, "sale.quick_note.list", limit=100).rows:
        call(ctx, "sale.quick_note.delete", id=row.id)

    report = loaded_back(ctx, file)

    assert the_till(ctx) == before
    assert created(report) == {"sale.department": (1, 0), "sale.quick_note": (1, 0)}


def test_loading_the_file_again_duplicates_nothing_and_the_payment_methods_never_travel(ctx):
    a_till(ctx)

    report = loaded_back(ctx, exported_apps(ctx, ["sale"]))

    assert created(report) == {"sale.department": (0, 1), "sale.quick_note": (0, 1)}
    assert set(data_of(ctx, ["sale"])) == {"sale.department", "sale.quick_note"}
