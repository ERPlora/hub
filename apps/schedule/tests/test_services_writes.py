"""What the writes of the hours share: a correction sets only the sent values that change the row, and the
settings row is held until the end of the command, so two temporary changes saved at the same instant wait for
each other and the second sees the first."""

from types import SimpleNamespace

import pytest
from live.errors import Conflict

from apps.schedule.models import Override
from apps.schedule.schemas.overrides import OverrideIn
from apps.schedule.services.writes import _apply_sent

from apps.staff.tests.conftest import _race

from .conftest import HUB_DB, HUB_DB_COMMITTED
from .test_services import run

pytestmark = HUB_DB


def test_a_correction_sets_only_the_sent_values_that_change_the_row():
    row = SimpleNamespace(name="Christmas", notes="Family", is_closed=True)
    assert _apply_sent(row, {"name": "Christmas", "notes": None, "is_closed": False}) is True
    assert (row.name, row.notes, row.is_closed) == ("Christmas", "Family", False)
    assert _apply_sent(row, {"name": "Christmas", "notes": None, "is_closed": False}) is False
    assert (row.name, row.notes, row.is_closed) == ("Christmas", "Family", False)


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_two_overlapping_temporary_changes_at_once_keep_one():
    def create(start, end, reason):
        return lambda: run(
            "schedule.override.create",
            OverrideIn(start_date=start, end_date=end, reason=reason),
        )

    outcome = _race(
        create("2026-08-01", "2026-08-15", "First"),
        create("2026-08-10", "2026-08-20", "Second"),
    )
    assert (
        isinstance(outcome.get("error"), Conflict)
        and outcome["error"].code == "schedule.override_overlaps"
    )
    assert list(Override.objects.values_list("reason", flat=True)) == ["First"]
