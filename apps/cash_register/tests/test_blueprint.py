"""What of Cash register travels in an export of the business (BASE-F35): its active drawers, by name, read with its
own list and written with its own create. The sessions, their movements and counts never travel. A drawer is
retired, never deleted: like the business's settings, one a load brought stays.

Every test runs against the real apps, in business A's own database, as production does.
"""

import pytest

from base.tenancy.tests.business import A
from base.tests.blueprint_round_trip import app_report, call, data_of, loaded_back, owner_of
from base.tests.blueprint_round_trip import exported as exported_apps

from apps.cash_register.tests.conftest import HUB_DB, in_business_a

__all__ = ["in_business_a"]
pytestmark = HUB_DB


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def test_a_backup_brings_back_the_drawers_the_business_no_longer_has(ctx):
    call(ctx, "cash_register.register.create", name="Terrace")
    file = exported_apps(ctx, ["cash_register"])
    terrace = next(row for row in call(ctx, "cash_register.register.list", limit=100).rows if row.name == "Terrace")
    call(ctx, "cash_register.register.update", register_id=terrace.id, name="Old terrace")

    report = loaded_back(ctx, file)

    names = {row.name for row in call(ctx, "cash_register.register.list", limit=100).rows}
    assert {"Terrace", "Old terrace"} <= names
    assert [part["created"] for part in app_report(report, "cash_register")["datasets"]] == [1]


def test_only_the_drawers_travel(ctx):
    call(ctx, "cash_register.register.create", name="Terrace")

    assert set(data_of(ctx, ["cash_register"])) == {"cash_register.register"}
