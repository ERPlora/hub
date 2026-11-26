"""Whether the floor plan is set up: how many tables are in use and how many zones there are, both counts."""

import pytest
from pydantic import ValidationError

from apps.table.schemas.floor_plan import FloorStatusOut


def test_the_floor_status_counts_the_tables_in_use_and_the_zones():
    status = FloorStatusOut.model_validate({"usable_tables": 3, "zones": 1})
    assert (status.usable_tables, status.zones) == (3, 1)
    with pytest.raises(ValidationError):
        FloorStatusOut.model_validate({"usable_tables": 3})
