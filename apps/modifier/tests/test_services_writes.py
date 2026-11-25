"""What the writes of groups, options and links share."""

import pytest
from live.errors import InvalidPayload

from apps.modifier.models import ModifierGroup, ModifierOption
from apps.modifier.services.writes import _save
from apps.tax.models import TaxCategory

from .conftest import GENERIC, HUB_DB, group

pytestmark = HUB_DB


def test_a_save_the_database_refuses_for_an_own_line_worth_nothing_is_a_422_on_the_supplement():
    # Two saves at once may pass the check before writing; the database's constraint says the same.
    group("Drinks")
    soda = ModifierOption(group=ModifierGroup.objects.get(name="Drinks"), name="Soda", price_delta=0, tax_category=TaxCategory.objects.get(key=GENERIC))
    with pytest.raises(InvalidPayload) as error:
        _save(soda)
    assert error.value.fields == {
        "price_delta": "An option with its own tax category is billed on a line of its own: its supplement must be more than zero."
    }
