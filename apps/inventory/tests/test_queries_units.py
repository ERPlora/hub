"""The units of measure (``apps/inventory/queries/units.py``): each with its step and its exact factor."""

from decimal import Decimal

from django.utils import translation

from apps.inventory.schemas.units import UnitListIn

from .conftest import HUB_DB, run

pytestmark = HUB_DB


def test_the_units_with_their_step_and_exact_factor():
    page = run("inventory.unit.list", UnitListIn(), role="hub_employee")
    assert [row.code for row in page.rows] == [
        "ud",
        "kg",
        "g",
        "t",
        "l",
        "ml",
        "min",
        "h",
    ]
    hour = page.rows[-1]
    assert (
        str(hour.name),
        hour.category,
        hour.factor_num,
        hour.factor_den,
        hour.increment,
        hour.is_reference,
    ) == (
        "Hour (h)",
        "time",
        60,
        1,
        Decimal("0.25"),
        False,
    )
    with translation.override("es"):
        assert run("inventory.unit.list", UnitListIn()).rows[0].name == "Unidad (ud)"
